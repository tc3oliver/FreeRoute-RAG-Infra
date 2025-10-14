# FreeRoute RAG Infra

<div align="right">
  <sup>Languages:</sup>
  <a href="README.md"><b>English</b></a> |
  <a href="README.zh-TW.md">繁體中文</a>
</div>

**Zero-Cost GraphRAG Infrastructure — Production-Ready & LangChain-Compatible**

End-to-end **Document → Vector Index → Knowledge Graph → Hybrid Retrieval** pipeline with automated ingestion, graph extraction, and cost-aware multi-provider routing.

<!-- Badges -->

[![CI](https://github.com/tc3oliver/FreeRoute-RAG-Infra/actions/workflows/ci.yml/badge.svg)](https://github.com/tc3oliver/FreeRoute-RAG-Infra/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED?logo=docker\&logoColor=white)

---

## Overview

FreeRoute RAG Infra is a locally deployable RAG/GraphRAG stack designed to help you **build and test at (near) zero cost**. It prefers free/low-cost providers, automatically falls back when quotas are hit, and ships local components for embeddings and reranking.

**Highlights**

* One-command local bring-up (Docker Compose)
* OpenAI-compatible proxy (LiteLLM) for LangChain & SDKs
* Hybrid retrieval: vector + knowledge graph (+ optional rerank)
* TokenCap: daily OpenAI token caps with usage-aware fallbacks
* Local inference for embeddings (Ollama bge-m3) and reranking (BAAI bge-reranker-v2-m3)
* Observability: health checks, metrics (optional), and a dashboard

---

## Quick Start (Local)

1. Create a `.env` file:

```bash
# .env (example)
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
GROQ_API_KEY=...
# Optional:
API_GATEWAY_KEYS=dev-key,another-key
NEO4J_PASSWORD=neo4j123
POSTGRES_PASSWORD=postgres123
```

2. Start everything:

```bash
docker compose up -d --build
```

3. Health checks:

```bash
# LiteLLM proxy
curl -s http://localhost:9400/health | jq || \
curl -s http://localhost:9400/health/readiness | jq

# Gateway / Ingestor
curl -s http://localhost:9800/health | jq
curl -s http://localhost:9900/health | jq
```

4. Dashboard (LiteLLM UI)

* URL: [http://localhost:9400/ui](http://localhost:9400/ui)
* Default credentials: `admin` / `admin123` → **change ASAP**

**Notes**

* Ollama pulls **`bge-m3`** automatically.
* The reranker downloads **`BAAI/bge-reranker-v2-m3`** on first run (may take a few minutes).
* Compose persists models in `ollama_models` and `reranker_models`.

---

## Developer Quick Start

```bash
# Create and activate venv
python -m venv .venv
source .venv/bin/activate

# Install runtime + dev deps
pip install -r services/gateway/requirements.txt
pip install -r requirements-dev.txt
```

Run the **Gateway** locally:

```bash
uvicorn services.gateway.app:app --host 0.0.0.0 --port 9800 --reload
```

Run the **Reranker** (optional):

```bash
uvicorn services.reranker.server:app --host 0.0.0.0 --port 9080 --reload
```

---

## Architecture

```mermaid
flowchart LR
  classDef grp fill:#ffffff,stroke:#2b6cb0,stroke-width:1px,color:#1a202c;
  classDef box fill:#f8fafc,stroke:#64748b,stroke-width:1px,color:#0f172a;
  classDef entry fill:#ecfeff,stroke:#0891b2,stroke-width:1px,color:#0e7490;
  classDef core fill:#f1f5f9,stroke:#334155,stroke-width:1px,color:#0f172a;
  classDef store fill:#fefce8,stroke:#ca8a04,stroke-width:1px,color:#713f12;
  classDef provider fill:#fdf2f8,stroke:#db2777,stroke-width:1px,color:#9d174d;
  classDef local fill:#eef2ff,stroke:#4f46e5,stroke-width:1px,color:#312e81;
  classDef edgeNote stroke-dasharray: 4 3;

  subgraph CLIENT["① Clients / SDK"]
    U["👤 Web Client<br/>— REST / X-API-Key —"]:::entry
    LC["🧰 LangChain / SDK<br/>(OpenAI-Compatible)"]:::entry
  end
  class CLIENT grp

  subgraph APIGW["② API Gateway (9800)<br/>— Auth / Routing / Orchestration —"]
    GW_CHAT["/chat"]:::box
    GW_RETRIEVE["/retrieve  /search"]:::box
    GW_INDEX["/index/chunks"]:::box
    GW_GRAPH["/graph/*"]:::box
    GW_EMBED["/embed"]:::box
    GW_RERANK["/rerank"]:::box
  end
  class APIGW grp

  subgraph ING["③ Ingestor (9900)<br/>— Document Ingest / Chunking —"]
    ING_RUN["ingest/directory<br/>CLI / API"]:::box
  end
  class ING grp

  subgraph LLMCORE["④ LiteLLM Proxy (9400)<br/>— Model Routing / TokenCap / UI —"]
    LC_TC["🧱 TokenCap / Routing Policies"]:::core
    LC_UI["📊 Dashboard UI"]:::core
    LLM_BUS["🔀 OpenAI-Compatible Router"]:::core
    REDIS["🧮 Redis 6379<br/>Cache / Token Counters"]:::store
  end
  class LLMCORE grp

  subgraph LOCAL["⑤ Local Inference"]
    OLLAMA["🧩 Ollama (bge-m3)<br/>Embeddings"]:::local
    RERANK["↕️ bge-reranker-v2-m3<br/>Reranker"]:::local
  end
  class LOCAL grp

  subgraph STORAGE["⑥ Storage / Databases"]
    QDRANT["🗂 Qdrant 6333<br/>Vector Index"]:::store
    NEO4J["🕸 Neo4j 7474/7687<br/>Knowledge Graph"]:::store
    PG["📇 Postgres 5432<br/>Metadata / Logs"]:::store
  end
  class STORAGE grp

  subgraph PROVIDERS["⑦ Cloud Model Providers"]
    OAI["OpenAI"]:::provider
    GGM["Google Gemini"]:::provider
    OPR["OpenRouter"]:::provider
    GRQ["Groq"]:::provider
  end
  class PROVIDERS grp

  U -->|"REST (X-API-Key)"| APIGW
  LC -->|"OpenAI-Compatible"| LLMCORE

  ING_RUN -->|"call /index/chunks"| GW_INDEX
  ING_RUN -.->|"bulk"| QDRANT:::edgeNote

  GW_CHAT -->|"chat / tools"| LLM_BUS
  GW_RETRIEVE -->|"retrieve"| QDRANT
  GW_RETRIEVE -->|"graph query"| NEO4J
  GW_INDEX -->|"chunk → embed"| GW_EMBED
  GW_EMBED -->|"local embeddings"| OLLAMA
  GW_INDEX -->|"write vectors/meta"| QDRANT
  GW_INDEX -->|"write metadata"| PG
  GW_RERANK -->|"rerank request"| RERANK
  GW_GRAPH -->|"upsert / query"| NEO4J
  APIGW -->|"ops logs"| PG

  LLM_BUS --> OLLAMA
  LLM_BUS --> LC_TC
  LLM_BUS --> LC_UI
  LLM_BUS --> OAI
  LLM_BUS --> GGM
  LLM_BUS --> OPR
  LLM_BUS --> GRQ
  LLMCORE --> REDIS

  QDRANT -.->|"retrieved docs"| RERANK:::edgeNote
  RERANK -.->|"Top-K ranked"| LLM_BUS:::edgeNote
  LLM_BUS -.->|"final answer"| APIGW:::edgeNote
  APIGW -.->|"response"| U:::edgeNote
```

> Tip: connect **LangChain** directly to LiteLLM (port **9400**). End-user app flows go through the **API Gateway** (port **9800**).

---

## Features

* **OpenAI-compatible API** (LiteLLM proxy + dashboard)
* **API Gateway**: `/chat`, `/embed`, `/rerank`, `/graph/*`
* **Local embeddings**: Ollama **bge-m3**
* **Local reranker**: **BAAI/bge-reranker-v2-m3** (GPU optional)
* **TokenCap**: daily OpenAI token cap with usage-aware routing
* **Observability**: health endpoints and optional Prometheus metrics

## Requirements

* Docker 24+ (Compose v2)
* Optional GPU: NVIDIA driver + Container Toolkit (Linux w/ CUDA 12.x recommended)

---

## ✨ GraphRAG Capabilities

**Document → Answer, end-to-end:**

* 📄 **Ingestion**: Auto-scan directories, chunk & index (Markdown/HTML/TXT)
* 🔍 **Vector search**: Local embeddings via Ollama (bge-m3)
* 🕸 **Knowledge graph**: Auto-extract entities/relations to Neo4j
* 🔀 **Hybrid retrieval**: Vector + graph (+ BM25 if configured)
* 🤖 **Query planning**: Provider routing and answer generation with citations
* 📈 **Observability**: metrics, tracing, rate limiting, health checks

**Infra components:**

* 🚀 **API Gateway** (9800): Unified endpoints with auth & orchestration
* 🧠 **LiteLLM Proxy** (9400): Multi-provider router with TokenCap & fallbacks
* 📚 **Ingestor** (9900): Batch document processing & graph extraction
* 🗄️ **Storage**: Qdrant (vectors) + Neo4j (graph) + Redis (counters/cache) + Postgres (metadata)

---

## End-to-End Usage (CLI & cURL)

### Step 1 — Ingest Documents

```bash
mkdir -p data
echo "Alice Johnson is a Senior Software Engineer at Acme Corporation in Taipei. She specializes in Python, GraphRAG, and AI systems." > data/alice.md

curl -X POST http://localhost:9900/ingest/directory \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/data",
    "collection": "knowledge_base",
    "file_patterns": ["*.md", "*.txt"],
    "chunk_size": 800,
    "extract_graph": true,
    "force_reprocess": true
  }' | jq
```

### Step 2 — Hybrid Retrieval

```bash
# Vector search
curl -X POST http://localhost:9800/search \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"Python engineer skills","top_k":3,"collection":"knowledge_base"}' | jq

# GraphRAG retrieval (vector + subgraph)
curl -X POST http://localhost:9800/retrieve \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"Who works at Acme Corporation and what are their skills?","top_k":5,"include_subgraph":true,"max_hops":2}' | jq
```

### Step 3 — Knowledge Graph Queries

```bash
# Cypher (read-only)
curl -X POST http://localhost:9800/graph/query \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"MATCH (p:Person)-[r]-(c:Company) RETURN p.id, type(r), c.id LIMIT 10"}' | jq

# Manual upsert
curl -X POST http://localhost:9800/graph/upsert \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{
    "data": {
      "nodes": [{"id":"Bob","type":"Person","props":[{"key":"role","value":"Manager"}]}],
      "edges": [{"src":"Bob","dst":"Acme Corporation","type":"MANAGES","props":[]}]
    }
  }' | jq
```

### Step 4 — Ingestor CLI (alternative)

```bash
cd services/ingestor
pip install -r requirements.txt

python cli.py ../../data \
  --collection mydata \
  --chunk-size 1000 \
  --ingestor-url http://localhost:9900
```

---

## Complete API Reference

The **canonical** API reference (endpoints, request/response shapes, models) lives in:

* `docs/en/api_usage.md` (English)
* `docs/zh/api_usage.md` (Traditional Chinese)

> The code is authoritative. If a doc looks out of sync, diff your branch vs `main`, or hit live `/health` & `/whoami`.

---

## Configuration (.env)

> Keep secrets in `.env`. **Do not** commit this file.

| Variable              | Example                          | Description                                    |
| --------------------- | -------------------------------- | ---------------------------------------------- |
| `LITELLM_MASTER_KEY`  | `sk-admin`                       | Unified API key for LiteLLM (LangChain/SDK)    |
| `LITELLM_KEY`         | `sk-admin`                       | Internal key used by Gateway to call LiteLLM   |
| `OPENAI_API_KEY`      | `sk-...`                         | OpenAI API key (subject to daily token caps)   |
| `GOOGLE_API_KEY`      | `AIza...`                        | Google Gemini API key                          |
| `OPENROUTER_API_KEY`  | `sk-or-...`                      | OpenRouter API key                             |
| `GROQ_API_KEY`        | `gsk_...`                        | Groq API key                                   |
| `OPENAI_TPD_LIMIT`    | `10000000`                       | Daily OpenAI token cap (e.g., 10M)             |
| `OPENAI_REROUTE_REAL` | `true`                           | Reroute even when calling raw OpenAI models    |
| `GRAPH_SCHEMA_PATH`   | `/app/schemas/graph_schema.json` | Graph schema path (shared w/ TokenCap/Gateway) |
| `TZ`                  | `Asia/Taipei`                    | Timezone                                       |
| `TZ_OFFSET_HOURS`     | `8`                              | Offset used for Redis daily counters           |
| `API_GATEWAY_KEYS`    | `dev-key,another-key`            | Allowed X-API-Key list for Gateway             |
| `NEO4J_PASSWORD`      | `neo4j123`                       | Neo4j password                                 |
| `POSTGRES_PASSWORD`   | `postgres123`                    | Postgres password                              |
| `CHUNK_SIZE`          | `1000`                           | Default text chunk size                        |
| `CHUNK_OVERLAP`       | `200`                            | Overlap between chunks                         |

**GraphRAG-specific**

* `QDRANT_URL` (default `http://qdrant:6333`) — Vector DB
* `NEO4J_URI` (default `bolt://neo4j:7687`) — Graph DB
* `GATEWAY_BASE` (default `http://apigw:8000`) — Ingestor → Gateway
* `GATEWAY_API_KEY` (default `dev-key`) — Ingestor’s Gateway key
* `GRAPH_MIN_NODES` / `GRAPH_MIN_EDGES` (default `1/1`)
* `GRAPH_PROVIDER_CHAIN` — LLM fallback order for graph extraction

**Cost protection**

* `litellm.config.yaml` sets `general_settings.max_budget_per_day: 0.0` (avoid surprise spend).
* TokenCap enforces `OPENAI_TPD_LIMIT`; Compose uses a high default to leave headroom for system use.

---

## Model Entrypoints & Routing

**Aliases (concise)**

**Chat / Inference**

| Alias                   | Backend                                          | Purpose                | Fallback order |
| ----------------------- | ------------------------------------------------ | ---------------------- | -------------- |
| `rag-answer`            | `openai/gpt-5-mini-2025-08-07`                   | Primary chat/RAG       | 1              |
| `rag-answer-gemini`     | `gemini/2.5-flash`                               | Free/low-cost fallback | 2              |
| `rag-answer-openrouter` | `openrouter/mistral-small-3.2-24b-instruct:free` | Community/free path    | 3              |
| `rag-answer-groq`       | `groq/llama-3.1-8b-instant`                      | Low-latency path       | 4              |

**Graph Extraction**

| Alias                    | Backend                        | Notes                       |
| ------------------------ | ------------------------------ | --------------------------- |
| `graph-extractor`        | `openai/gpt-5-mini-2025-08-07` | Injects JSON schema, temp=0 |
| `graph-extractor-o1mini` | `openai/o1-mini-2024-09-12`    | Mid-chain retry             |
| `graph-extractor-gemini` | `gemini/2.5-flash`             | Tail fallback               |

**Embeddings / Rerank**

| Alias                    | Backend              | Notes              |
| ------------------------ | -------------------- | ------------------ |
| `local-embed`            | `ollama/bge-m3`      | Local embeddings   |
| `reranker` (via Gateway) | `bge-reranker-v2-m3` | Self-hosted rerank |

**Routing highlights**

* Strategy: `usage_aware_fallback` + **TokenCap** (daily OpenAI cap)
* Daily usage counter key (Redis): `tpd:openai:YYYY-MM-DD`
* Fallback chains:

  * `rag-answer` → `rag-answer-gemini` → `rag-answer-openrouter` → `rag-answer-groq`
  * `graph-extractor` → `graph-extractor-o1mini` → `graph-extractor-o1mini` → `graph-extractor-gemini`
* `OPENAI_REROUTE_REAL=true` also reroutes raw OpenAI models if over cap.
* Use `LITELLM_MASTER_KEY` for clients; Gateway uses `LITELLM_KEY` internally.

---

## API (Quick Examples)

**LiteLLM (OpenAI-compatible) — Base `http://localhost:9400/v1`**

Python (LangChain):

```python
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

llm = ChatOpenAI(base_url="http://localhost:9400/v1", api_key="sk-admin",
                 model="rag-answer", temperature=0.2)
emb = OpenAIEmbeddings(base_url="http://localhost:9400/v1", api_key="sk-admin",
                       model="local-embed")

print(llm.invoke("Explain RAG in three lines").content)
print(len(emb.embed_query("Key differences between GraphRAG and RAG")))
```

cURL:

```bash
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" -H "Content-Type: application/json" \
  -d '{"model":"rag-answer","messages":[{"role":"user","content":"List three advantages of RAG"}]}'
```

**API Gateway — Base `http://localhost:9800` (X-API-Key)**

```bash
# /chat (JSON mode)
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Reply in JSON with two bullet points"}],"json_mode":true,"temperature":0.2}' \
  http://localhost:9800/chat | jq

# /embed
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"texts":["What is RAG?","What is GraphRAG?"]}' \
  http://localhost:9800/embed | jq

# /rerank
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"What is generative AI?","documents":["AI is artificial intelligence","Generative AI can create content"],"top_n":2}' \
  http://localhost:9800/rerank | jq

# /graph/probe (strict JSON)
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"model":"graph-extractor","strict_json":true}' \
  http://localhost:9800/graph/probe | jq
```

---

## Graph Schema

* **Repo**: `schemas/graph_schema.json`
* **Container**: `/app/schemas/graph_schema.json` (mounted via Compose)

Top-level shape:

```json
{
  "nodes": [
    {"id": "string", "type": "string", "props": [{"key": "...", "value": "..."}]}
  ],
  "edges": [
    {"src": "string", "dst": "string", "type": "string", "props": [{"key": "...", "value": "..."}]}
  ]
}
```

* `props[].value` supports string/number/boolean/null.
* Gateway and TokenCap validate schema at startup (fail fast if invalid).

Graph extraction (via Gateway):

```bash
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"context":"Alice joined Acme in 2022 as an engineer; Acme HQ is in Taipei, founded by Bob."}' \
  http://localhost:9800/graph/extract | jq
```

---

## Reranker & Embeddings

* **Embeddings**: LiteLLM alias `local-embed` → Ollama **bge-m3**
* **Reranker**: BAAI **bge-reranker-v2-m3**

  * Direct: `POST http://localhost:9080/rerank`
  * Gateway: `POST http://localhost:9800/rerank`
  * Response shape: `{"ok": true, "results": [{"index": 1, "score": 0.83, "text": "..."}]}`

---

## Testing & Validation

**Quick validation**

```bash
# Ingestion
curl -X POST http://localhost:9900/ingest/directory \
  -H "Content-Type: application/json" \
  -d '{"path":"/data","extract_graph":true}' | jq

# Hybrid retrieval
curl -X POST http://localhost:9800/retrieve \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"engineer skills","include_subgraph":true}' | jq

# Verify graph
curl -X POST http://localhost:9800/graph/query \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"MATCH (n) RETURN count(n) as total_nodes"}' | jq
```

**Unit tests** (fast, no external services):

```bash
PYTHONPATH=$(pwd) .venv/bin/pytest -q tests/unit
```

**Integration tests** (services running):

```bash
docker compose up -d --build
PYTHONPATH=$(pwd) .venv/bin/pytest -q tests/integration
```

**Benchmarks**

```bash
# Bulk ingestion
python services/ingestor/cli.py ./data --chunk-size 500 --no-graph

# Query latency
for i in {1..10}; do
  curl -w "@curl-format.txt" -X POST http://localhost:9800/retrieve \
    -H "X-API-Key: dev-key" -d '{"query":"test query"}'
done
```

---

## Metrics (Prometheus)

The Gateway exposes `/metrics` **only** when `prometheus-client` is installed.

```bash
pip install prometheus-client
```

* With the lib present: `/metrics` returns Prometheus metrics (per-endpoint counters & durations).
* Without it: `/metrics` returns **204** to keep probes harmless.

Prometheus scrape snippet:

```yaml
- job_name: 'free-rag-gateway'
  static_configs:
    - targets: ['host.docker.internal:9800']
      labels:
        service: gateway
```

---

## Troubleshooting

**Services won’t start**

```bash
docker compose ps
docker compose logs <service>
# M1/ARM
export PLATFORM=linux/amd64
docker compose up -d --build
```

**Graph extraction timeouts**

```bash
curl http://localhost:9400/health
curl -X POST http://localhost:9900/ingest/directory \
  -d '{"path":"/data","chunk_size":500,"extract_graph":false}'
```

**Empty search results**

```bash
curl http://localhost:9143/api/ps         # Ollama
curl http://localhost:6333/collections    # Qdrant
# Re-index
curl -X POST http://localhost:9900/ingest/directory \
  -d '{"path":"/data","force_reprocess":true}'
```

**Graph query errors**

```bash
curl http://localhost:7474/
curl -X POST http://localhost:9800/graph/query \
  -H "X-API-Key: dev-key" \
  -d '{"query":"MATCH (n) RETURN count(n)"}'
```

**Performance tips**

* Slow ingestion → reduce `chunk_size`, disable `extract_graph` for huge docs
* High memory → limit concurrency, raise Docker memory
* GPU not used → install NVIDIA Container Toolkit; verify with `nvidia-smi` inside containers

**Rate limit / fallback triggers**

Symptoms: HTTP 429, model alias changes mid-response (fallback), brief latency spike after cap.

Checklist:

```bash
docker compose logs litellm | grep -i reroute | tail -20
grep OPENAI_TPD_LIMIT docker-compose.yml .env || echo "not set"
docker exec -it redis redis-cli KEYS tpd:openai:* | head
grep -n "fallbacks:" configs/litellm.config.yaml
```

Actions:

* Raise `OPENAI_TPD_LIMIT` or reduce traffic
* Add more free/low-cost fallbacks (e.g., OpenRouter)
* Ensure Redis is healthy (counters drive TokenCap)
* `OPENAI_REROUTE_REAL=false` to fail fast on raw OpenAI calls
* Monitor via LiteLLM Dashboard (`/ui`)

---

## Project Structure

```
.
├─ services/
│  ├─ gateway/               # API Gateway (FastAPI)
│  │  ├─ app.py
│  │  └─ requirements.txt
│  └─ reranker/              # PyTorch Reranker (FastAPI)
│     └─ server.py
├─ integrations/
│  └─ litellm/
│     └─ plugins/
│        └─ token_cap.py     # TokenCap: TPD + reroute + schema injection
├─ containers/
│  ├─ gateway/Dockerfile
│  └─ litellm/Dockerfile
├─ schemas/
│  └─ graph_schema.json
├─ configs/
│  └─ litellm.config.yaml
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  └─ reranker/
├─ docker-compose.yml
├─ pyproject.toml
├─ README.md / README.zh-TW.md
└─ ...
```

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md).

Quick dev setup:

```bash
pip install -r requirements-dev.txt
pre-commit install
PYTHONPATH=$(pwd) pytest tests/unit/
```

## Support

* 📖 Docs: README + `docs/en/api_usage.md`
* 🐛 Issues: GitHub Issues
* 💬 Discussions: GitHub Discussions
* 🔄 Updates: Star & watch the repo

## License

MIT — see [LICENSE](LICENSE).

**Free & Open Source** — Build production GraphRAG infra at zero cost 🚀
