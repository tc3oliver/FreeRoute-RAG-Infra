# FreeRoute RAG Infra

<div align="right">
  <sup>Languages:</sup>
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a>

</div>

**Zero-Cost GraphRAG Infrastructure — Production-Ready & LangChain Compatible**

Complete **Document → Vector Index → Knowledge Graph → Hybrid Retrieval** pipeline with automated ingestion, graph extraction, and intelligent query planning.

<!-- Badges -->
[![CI](https://github.com/tc3oliver/FreeRoute-RAG-Infra/actions/workflows/ci.yml/badge.svg)](https://github.com/tc3oliver/FreeRoute-RAG-Infra/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)

## Overview

FreeRoute RAG Infra is a locally deployable RAG/GraphRAG infrastructure designed to help developers build and test with zero cost whenever possible (Free-first). It prioritizes free or low-cost providers, falls back when quotas are hit, and includes local components.

Highlights:
Quick start (local)

1) Create a `.env` file (example):

```bash
# .env (example)
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
GROQ_API_KEY=...
# Optional: API_GATEWAY_KEYS=dev-key,another-key
```

2) Start with Docker Compose (recommended):

```bash
docker compose up -d --build
```

3) Health checks:

```bash
curl -s http://localhost:9400/health || curl -s http://localhost:9400/health/readiness | jq
curl -s http://localhost:9800/health | jq
```

4) Dashboard (LiteLLM UI):

- URL: http://localhost:9400/ui
- Default credentials: admin / admin123 (change ASAP)

Notes:

- Ollama will pull the `bge-m3` model automatically. The reranker downloads `BAAI/bge-reranker-v2-m3` on first run; this can take several minutes.
- Persistent volumes used by the compose setup include `ollama_models` and `reranker_models`.

Developer quick start (using the repo `.venv`):

```bash
# create venv (if not present)
python -m venv .venv
source .venv/bin/activate
# install runtime + dev requirements
pip install -r services/gateway/requirements.txt
pip install -r requirements-dev.txt
```

Run the gateway locally (for development):

```bash
    FE["Web / API Client"]
  end
```

  subgraph GATEWAY["API Gateway (9800)"]
    G1["/chat"]
    G2["/graph/extract"]
    G3["/embed"]
    G4["/rerank"]
  end

  subgraph CORE["FreeRoute RAG Infra Core"]
  subgraph LITELLM["LiteLLM Proxy (9400)"]
      TOK["TokenCap"]
      LDB[("Dashboard UI")]
    end
  end

  subgraph LOCAL["Local Services"]
    OLLAMA[("Ollama<br/>bge-m3")]
    RERANK["bge-reranker-v2-m3"]
    REDIS["Redis"]
    PG["Postgres"]
  end

  subgraph PROVIDERS["Cloud Providers"]
    OAI["OpenAI"]
    GGM["Gemini"]
    OPR["OpenRouter"]
    GRQ["Groq"]
  end

  LC --|OpenAI-compatible API|--> LITELLM
  FE --|REST / X-API-Key|--> GATEWAY

  GATEWAY --> LITELLM
  LITELLM --> OLLAMA
  GATEWAY --> OLLAMA
  GATEWAY --> RERANK

  LITELLM --> REDIS
  LITELLM --> LDB

  LITELLM --> OAI
  LITELLM --> GGM
  LITELLM --> OPR
  LITELLM --> GRQ
```

Note: LangChain is recommended to connect directly to LiteLLM (9400). Application flows for end users can go through the API Gateway (9800).

## Features

- OpenAI-compatible API (LiteLLM proxy)
- API Gateway: /chat, /embed, /rerank, /graph/extract
- Local embeddings: Ollama bge-m3
- Local reranker: BAAI/bge-reranker-v2-m3 (GPU optional)
- TokenCap: Daily OpenAI token caps and cost-aware rerouting
- Dashboard UI: Requests, errors, and usage

## Requirements

- Docker 24+ (Compose v2)
- Optional GPU: NVIDIA driver + Container Toolkit (Linux recommended CUDA 12.x)

## ✨ GraphRAG Features

**Complete Document-to-Answer Pipeline:**
- 📄 **Document Ingestion**: Auto-scan directories, chunk & index (Markdown, HTML, TXT)
- 🔍 **Vector Search**: Semantic similarity with local embeddings (Ollama bge-m3)
- 📊 **Knowledge Graph**: Auto-extract entities & relationships, store in Neo4j
- 🔀 **Hybrid Retrieval**: Combine vector + graph + BM25 for comprehensive results
- 🤖 **Query Planning**: Intelligent routing & answer generation with citations
- 📈 **Observability**: Metrics, tracing, rate limiting, health checks

**Infrastructure Components:**
- 🚀 **API Gateway** (9800): Unified GraphRAG endpoints with auth & rate limiting
- 🧠 **LiteLLM Proxy** (9400): Multi-provider LLM routing with TokenCap & fallbacks
- 📚 **Ingestor Service** (9900): Batch document processing & knowledge extraction
- 🗄️ **Storage Layer**: Qdrant (vectors) + Neo4j (graph) + Redis (cache) + Postgres (metadata)

## Quick Start

### 1. Environment Setup

Create `.env` file:
```bash
# .env (required)
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
OPENROUTER_API_KEY=sk-or-...
GROQ_API_KEY=gsk_...

# Optional: customize settings
API_GATEWAY_KEYS=dev-key,prod-key
NEO4J_PASSWORD=neo4j123
POSTGRES_PASSWORD=postgres123
CHUNK_SIZE=1000
```

### 2. Start All Services

```bash
docker compose up -d --build
```

This starts:
- **LiteLLM Proxy** (9400) + Dashboard UI
- **API Gateway** (9800) with GraphRAG endpoints
- **Ingestor Service** (9900) for document processing
- **Qdrant** (6333), **Neo4j** (7474/7687), **Redis** (6379)
- **Ollama** (9143) for local embeddings
- **Reranker** (9080) for result re-ranking

### 3. Health Checks

```bash
curl -s http://localhost:9800/health | jq     # Gateway
curl -s http://localhost:9900/health | jq     # Ingestor
curl -s http://localhost:9400/health | jq     # LiteLLM
curl -s http://localhost:6333/ | jq           # Qdrant
```

### 4. Dashboard Access

**LiteLLM Dashboard**: http://localhost:9400/ui
- Username: `admin` / Password: `admin123` (change ASAP)
- Monitor API usage, costs, and provider health

**Neo4j Browser**: http://localhost:7474/
- Username: `neo4j` / Password: `neo4j123` (or your `NEO4J_PASSWORD`)
- Explore knowledge graph visually

## 🚀 End-to-End GraphRAG Usage

### Step 1: Document Ingestion

```bash
# Create sample documents
mkdir -p data
echo "Alice Johnson is a Senior Software Engineer at Acme Corporation in Taipei. She specializes in Python, GraphRAG, and AI systems." > data/alice.md

# Ingest documents (auto-chunks + embeds + extracts graph)
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

### Step 2: Hybrid Search & Retrieval

```bash
# Semantic vector search
curl -X POST http://localhost:9800/search \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Python engineer skills",
    "top_k": 3,
    "collection": "knowledge_base"
  }' | jq

# GraphRAG hybrid retrieval (vector + knowledge graph)
curl -X POST http://localhost:9800/retrieve \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Who works at Acme Corporation and what are their skills?",
    "top_k": 5,
    "include_subgraph": true,
    "max_hops": 2
  }' | jq
```

### Step 3: Knowledge Graph Queries

```bash
# Direct graph queries (Cypher)
curl -X POST http://localhost:9800/graph/query \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (p:Person)-[r]-(c:Company) RETURN p.id, type(r), c.id LIMIT 10"
  }' | jq

# Manual graph updates
curl -X POST http://localhost:9800/graph/upsert \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "nodes": [{"id": "Bob", "type": "Person", "props": [{"key": "role", "value": "Manager"}]}],
      "edges": [{"src": "Bob", "dst": "Acme Corporation", "type": "MANAGES", "props": []}]
    }
  }' | jq
```

### Step 4: CLI Tools (Alternative)

```bash
# Use ingestor CLI for batch processing
cd services/ingestor
pip install -r requirements.txt

python cli.py ../../data \
  --collection mydata \
  --chunk-size 1000 \
  --ingestor-url http://localhost:9900
```

## 📖 Complete API Reference

### Ingestor Service (Port 9900)

#### `POST /ingest/directory`
Batch document ingestion with auto-chunking and graph extraction.

**Request:**
```json
{
  "path": "/data",
  "collection": "chunks",
  "file_patterns": ["*.md", "*.txt", "*.html"],
  "chunk_size": 1000,
  "chunk_overlap": 200,
  "extract_graph": true,
  "force_reprocess": false
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Processed 3/3 files",
  "stats": {
    "files_found": 3,
    "files_processed": 3,
    "chunks_created": 12,
    "graphs_extracted": 3,
    "processing_time_sec": 45.2
  },
  "processed_files": ["doc1.md", "doc2.md"],
  "errors": []
}
```

### API Gateway (Port 9800)

#### `POST /index/chunks`
Index text chunks into vector database.

**Request:**
```json
{
  "collection": "chunks",
  "chunks": [
    {
      "doc_id": "doc1",
      "text": "Alice works at Acme Corp...",
      "metadata": {"source": "document", "section": "bio"}
    }
  ]
}
```

#### `POST /search`
Semantic vector search.

**Request:**
```json
{
  "query": "Python engineer skills",
  "top_k": 5,
  "collection": "chunks",
  "filters": {"metadata.source": "resume"}
}
```

#### `POST /retrieve` ⭐
**GraphRAG Hybrid Retrieval** - Core endpoint combining vector + graph search.

**Request:**
```json
{
  "query": "Who works at Acme and what skills do they have?",
  "top_k": 5,
  "collection": "chunks",
  "include_subgraph": true,
  "max_hops": 2,
  "filters": null
}
```

**Response:**
```json
{
  "ok": true,
  "hits": [
    {
      "text": "Alice Johnson is a Senior Software Engineer...",
      "metadata": {"doc_id": "alice.md"},
      "citations": [{"source": "vector", "doc_id": "alice.md", "score": 0.89}],
      "score": 0.89
    }
  ],
  "subgraph": {
    "nodes": [
      {"id": "Alice Johnson", "type": "Person", "props": {"role": "Engineer"}},
      {"id": "Acme Corporation", "type": "Company", "props": {"location": "Taipei"}}
    ],
    "edges": [
      {"src": "Alice Johnson", "dst": "Acme Corporation", "type": "WORKS_AT", "props": {}}
    ]
  },
  "query_time_ms": 150
}
```

#### `POST /graph/upsert`
Insert/update knowledge graph data.

**Request:**
```json
{
  "data": {
    "nodes": [
      {"id": "Alice", "type": "Person", "props": [{"key": "role", "value": "Engineer"}]}
    ],
    "edges": [
      {"src": "Alice", "dst": "Acme", "type": "WORKS_AT", "props": []}
    ]
  }
}
```

#### `POST /graph/query`
Execute Cypher queries on knowledge graph.

**Request:**
```json
{
  "query": "MATCH (p:Person)-[r]->(c:Company) RETURN p.id, type(r), c.id",
  "params": {"limit": 10}
}
```

#### Legacy Endpoints
- `POST /chat` - Chat completions with JSON mode support
- `POST /embed` - Text embeddings via local-embed model
- `POST /rerank` - Text reranking via local bge-reranker
- `POST /graph/extract` - Extract knowledge graph from text context

First run notes:

- Ollama will pull the bge-m3 model automatically. The reranker downloads BAAI/bge-reranker-v2-m3 on first run; this can take a few minutes.
- Persistent volumes: `ollama_models`, `reranker_models`.

## Configuration

Put configuration in .env. Do not commit .env to version control.

| Variable | Example | Description |
| --- | --- | --- |
| LITELLM_MASTER_KEY | sk-admin | Unified API key for LiteLLM (for LangChain/SDK) |
| OPENAI_API_KEY | sk-... | OpenAI API key (subject to daily token caps) |
| GOOGLE_API_KEY | AIza... | Google Gemini API key |
| OPENROUTER_API_KEY | sk-or-... | OpenRouter API key |
| GROQ_API_KEY | gsk_... | Groq API key |
| OPENAI_TPD_LIMIT | 10000000 | Daily OpenAI token cap (e.g., 10M) |
| OPENAI_REROUTE_REAL | true | Allow rerouting even when calling real OpenAI models directly |
| GRAPH_SCHEMA_PATH | /app/schemas/graph_schema.json | Graph Schema path (shared by TokenCap/Gateway) |
| TZ | Asia/Taipei | Time zone |
| TZ_OFFSET_HOURS | 8 | Time zone offset used for daily counters in Redis |
| API_GATEWAY_KEYS | dev-key,another-key | Allowed X-API-Key list for the Gateway |
| NEO4J_PASSWORD | neo4j123 | Neo4j database password |
| POSTGRES_PASSWORD | postgres123 | PostgreSQL database password |
| CHUNK_SIZE | 1000 | Default text chunk size for document processing |
| CHUNK_OVERLAP | 200 | Overlap between text chunks |

**GraphRAG-Specific Variables:**
- `QDRANT_URL` (default http://qdrant:6333): Vector database connection
- `NEO4J_URI` (default bolt://neo4j:7687): Graph database connection
- `GATEWAY_BASE` (default http://apigw:8000): Ingestor → Gateway communication
- `GATEWAY_API_KEY` (default dev-key): API key for ingestor service
- `GRAPH_SCHEMA_PATH` (default /app/schemas/graph_schema.json): Knowledge graph schema
- `GRAPH_MIN_NODES/GRAPH_MIN_EDGES` (default 1/1): Graph extraction thresholds
- `GRAPH_PROVIDER_CHAIN`: LLM fallback order for graph extraction

Cost protection:

- `litellm.config.yaml` sets `general_settings.max_budget_per_day: 0.0` to avoid unexpected costs.
- TokenCap enforces the daily OpenAI token limit via `OPENAI_TPD_LIMIT`; compose defaults to 9M (reserve ~1M for system).

## 🏗️ Architecture & Services

### Service Overview

| Service | Port | Description | Key Features |
|---------|------|-------------|--------------|
| **API Gateway** | 9800 | GraphRAG unified API | `/retrieve`, `/search`, `/index/chunks`, `/graph/*` |
| **Ingestor** | 9900 | Document processing | Batch ingestion, chunking, graph extraction |
| **LiteLLM Proxy** | 9400 | Multi-LLM router + UI | TokenCap, fallbacks, OpenAI-compatible |
| **Qdrant** | 6333 | Vector database | Semantic search, embeddings storage |
| **Neo4j** | 7474/7687 | Graph database | Knowledge graph, Cypher queries |
| **Ollama** | 9143 | Local embeddings | bge-m3 model, GPU-accelerated |
| **Reranker** | 9080 | Result reranking | bge-reranker-v2-m3, precision boost |
| **Redis** | 6379 | Cache & counters | Token limits, session storage |
| **Postgres** | 5432 | Metadata storage | LiteLLM configuration, user data |

### Data Flow

```
Documents → [Ingestor] → Chunks → [Qdrant] ← [API Gateway] ← User Query
              ↓                     ↑
         Graph Extract → [Neo4j] ────┘
              ↓
          [LiteLLM] → Multiple LLM Providers
```

## Free tiers and sources

Provider policies and quotas change. Always verify with official pages.

- OpenAI (API)
  - No official “free daily token for data sharing” program. API calls are not used to train by default (you may opt-in for improvement).
  - Free credits depend on promotions, region, and time.
  - References:
    - https://platform.openai.com/docs/billing/overview
    - https://platform.openai.com/docs/guides/rate-limits/usage-tiers

- Google Gemini
  - Free/trial quotas via AI Studio/Developers; varies by model and region.
  - Reference: https://ai.google.dev/pricing

- Groq
  - Free inference API for certain models (e.g., Llama/Mixtral variants), with rate and quota limits.
  - Reference: https://groq.com/pricing

- OpenRouter
  - Aggregates many models; some are tagged free with queue/rate limits.
  - References:
    - https://openrouter.ai/pricing
    - https://openrouter.ai/models?tag=free

- Ollama (local)
  - Local inference, no cloud cost; performance depends on hardware.
  - Reference: https://ollama.com/

Default policy: Prefer free or low-cost providers. When OpenAI hits daily token caps (TPD) or errors occur, automatically reroute to Gemini/Groq/OpenRouter. Local embeddings via Ollama.

## Model entrypoints and routing

Defined in `configs/litellm.config.yaml`.

Chat / inference:

| Entry | Backend | Notes |
| --- | --- | --- |
| rag-answer | OpenAI gpt-5-mini | Default; reroute when capped |
| rag-answer-gemini | Gemini 2.5 Flash | Free fallback |
| rag-answer-openrouter | Mistral Small 24B (free) | OpenRouter fallback |
| rag-answer-groq | Groq Llama/Mixtral | Low-latency fallback |

Graph extraction:

| Entry | Backend | Notes |
| --- | --- | --- |
| graph-extractor | OpenAI mini | Default; TokenCap injects JSON Schema |
| graph-extractor-o1mini | OpenAI o1-mini | Fallback |
| graph-extractor-gemini | Gemini 2.5 Flash | Preferred fallback when capped/failing |

Embeddings / Rerank:

| Entry | Backend | Notes |
| --- | --- | --- |
| local-embed | Ollama bge-m3 | Local, free |
| reranker (Gateway) | bge-reranker-v2-m3 | Self-hosted API; best with GPU |

Routing strategy (TokenCap):

- Daily counter key: `tpd:openai:YYYY-MM-DD`
- Multi-hop fallback:
  - graph-extractor → graph-extractor-gemini
  - rag-answer → rag-answer-gemini → rag-answer-openrouter → rag-answer-groq
- OPENAI_REROUTE_REAL=true: reroute even for real OpenAI model names

## API

LiteLLM (unified API)

- Base URL: `http://localhost:9400/v1`
- Auth: `Authorization: Bearer <LITELLM_MASTER_KEY>`

Example (Python / LangChain):

```python
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

llm = ChatOpenAI(base_url="http://localhost:9400/v1", api_key="sk-admin", model="rag-answer", temperature=0.2)
emb = OpenAIEmbeddings(base_url="http://localhost:9400/v1", api_key="sk-admin", model="local-embed")

print(llm.invoke("Explain RAG in three lines").content)
print(len(emb.embed_query("Key differences between GraphRAG and RAG")))
```

OpenAI-compatible REST:

```bash
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{"model":"rag-answer","messages":[{"role":"user","content":"List three advantages of RAG"}]}'
```

API Gateway (app layer)

- Base: `http://localhost:9800`
- Auth: `X-API-Key: <key>` (default dev-key; set via `API_GATEWAY_KEYS`)

Endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /health | Health check |
| GET | /whoami | Config summary (requires key) |
| POST | /chat | Chat / JSON mode (auto system hint) |
| POST | /embed | Embeddings (local-embed) |
| POST | /rerank | Text reranking (bge-reranker-v2-m3) |
| POST | /graph/extract | Graph extraction with Schema validation |

Examples:

```bash
# /chat
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Reply in JSON with two bullet points of benefits"}],"json_mode":true,"temperature":0.2}' \
  http://localhost:9800/chat | jq

# /embed
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"texts":["What is RAG?","What is GraphRAG?"]}' \
  http://localhost:9800/embed | jq

# /rerank
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"What is generative AI?","documents":["AI is artificial intelligence","Generative AI can create content"],"top_n":2}' \
  http://localhost:9800/rerank | jq

# /graph/probe (lightweight probe, no schema validation)
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"model":"graph-extractor","strict_json":true}' \
  http://localhost:9800/graph/probe | jq
```

## Graph Schema

- Repo path: `schemas/graph_schema.json`
- Container path: `/app/schemas/graph_schema.json` (mounted via docker-compose)
- Top-level shape:

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

Notes: `props[].value` supports string/number/boolean/null.

The Gateway and TokenCap read this file and validate on startup (fail-fast if invalid).

Graph extraction (recommended via Gateway):

```bash
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"context":"Alice joined Acme in 2022 as an engineer; Acme HQ is in Taipei, founded by Bob."}' \
  http://localhost:9800/graph/extract | jq
```

Common parameters:

- context (required)
- min_nodes / min_edges (default 1 / 1)
- allow_empty (default false)
- max_attempts (default 2; each provider: strict then nudged)
- provider_chain (optional; override defaults)

## Reranker and embeddings

Embeddings (Ollama bge-m3)

- LiteLLM model name: `local-embed`
- In LangChain, use `OpenAIEmbeddings` pointing to the LiteLLM base URL

Reranker (bge-reranker-v2-m3)

-- Direct endpoint: `POST http://localhost:9080/rerank`
-- Via Gateway: `POST http://localhost:9800/rerank`
- Response: `{"ok": true, "results": [{"index": 1, "score": 0.83, "text": "..."}]}`

## 🧪 Testing & Validation

### Quick Validation

```bash
# Test document ingestion pipeline
curl -X POST http://localhost:9900/ingest/directory \
  -H "Content-Type: application/json" \
  -d '{"path": "/data", "extract_graph": true}' | jq

# Test GraphRAG hybrid retrieval
curl -X POST http://localhost:9800/retrieve \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "engineer skills", "include_subgraph": true}' | jq

# Verify knowledge graph
curl -X POST http://localhost:9800/graph/query \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "MATCH (n) RETURN count(n) as total_nodes"}' | jq
```

### Comprehensive Testing

**Unit Tests** (fast, no external services):
```bash
PYTHONPATH=$(pwd) .venv/bin/pytest -q tests/unit
```

**Integration Tests** (requires running services):
```bash
docker compose up -d --build
PYTHONPATH=$(pwd) .venv/bin/pytest -q tests/integration
```

**Performance Benchmarks:**
```bash
# Bulk ingestion test
python services/ingestor/cli.py ./data --chunk-size 500 --no-graph

# Query latency test
for i in {1..10}; do
  curl -w "@curl-format.txt" -X POST http://localhost:9800/retrieve \
    -H "X-API-Key: dev-key" -d '{"query": "test query"}'
done
```

### Metrics (Prometheus)
The API Gateway exposes an optional `/metrics` endpoint when the `prometheus-client` package is installed.

Install locally or in CI to enable scraping:

```bash
pip install prometheus-client
```

Behavior:
- When `prometheus-client` is installed, `/metrics` returns Prometheus-formatted metrics. The gateway collects per-endpoint request counts and request duration.
- When not installed, `/metrics` returns HTTP 204 so probes remain safe in minimal deployments.

Quick example for Prometheus scraping (Prometheus `scrape_configs`):

```yaml
- job_name: 'free-rag-gateway'
  static_configs:
    - targets: ['host.docker.internal:9800']
      labels:
        service: gateway
```

Notes:
- The gateway uses a module-local CollectorRegistry to avoid duplicated registration when reloading in tests or during interpreter restarts.
- You can enable metrics in CI by installing `prometheus-client` in the test step.

## Developer setup & pre-commit (short)

We recommend installing development and test dependencies locally to speed up development and avoid the pre-commit hooks downloading many packages on first run:

```bash
# Install development dependencies (run once on your dev machine)
pip install -r requirements-dev.txt

# Install pre-commit hooks (registers hooks in .git/hooks)
pip install pre-commit
pre-commit install
```

Note: On the first run on a machine, the pre-commit hook's isolated venv may download the packages listed in `requirements-dev.txt`, which can make that commit slower. To skip hooks temporarily, use `git commit --no-verify` (use sparingly).

If running the full test suite on every commit is too slow for your workflow, consider running tests at push time or configuring the pre-commit hook to run a smaller subset of checks.

## 🔧 Troubleshooting

### Common Issues

**Services won't start:**
```bash
# Check service status
docker compose ps
docker compose logs <service_name>

# Fix: Platform compatibility (M1 Mac / ARM)
export PLATFORM=linux/amd64
docker compose up -d --build
```

**Graph extraction timeouts:**
```bash
# Check LiteLLM API health
curl http://localhost:9400/health

# Reduce document size for graph extraction
curl -X POST http://localhost:9900/ingest/directory \
  -d '{"path": "/data", "chunk_size": 500, "extract_graph": false}'
```

**Empty search results:**
```bash
# Verify embeddings model is ready
curl http://localhost:9143/api/ps

# Check vector database
curl http://localhost:6333/collections

# Re-index if needed
curl -X POST http://localhost:9900/ingest/directory \
  -d '{"path": "/data", "force_reprocess": true}'
```

**Graph queries fail:**
```bash
# Check Neo4j connectivity
curl http://localhost:7474/
# Browser: http://localhost:7474/ (neo4j/neo4j123)

# Verify graph data exists
curl -X POST http://localhost:9800/graph/query \
  -H "X-API-Key: dev-key" \
  -d '{"query": "MATCH (n) RETURN count(n)"}'
```

**Performance Issues:**
- **Slow ingestion**: Reduce `chunk_size`, disable `extract_graph` for large documents
- **High memory usage**: Limit concurrent processing, increase Docker memory allocation
- **GPU not used**: Install NVIDIA Container Toolkit, verify `nvidia-smi` in containers

### Log Analysis

```bash
# Check all service logs
docker compose logs --tail=50

# Focus on specific services
docker compose logs ingestor apigw litellm qdrant neo4j

# Real-time monitoring
docker compose logs -f ingestor
```

## Project structure

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
│  ├─ gateway/Dockerfile     # Gateway container
│  └─ litellm/Dockerfile     # LiteLLM container
├─ schemas/
│  └─ graph_schema.json      # Graph JSON Schema (mounted to /app/schemas)
├─ configs/
│  └─ litellm.config.yaml    # LiteLLM models and routing strategy
├─ tests/
│  ├─ unit/                      # Fast unit tests (CI default)
│  │  ├─ test_gateway_handlers.py
│  │  └─ test_tokencap.py
│  ├─ integration/               # E2E smoke against running services
│  │  └─ test_gateway_smoke.py
│  └─ reranker/
│     └─ test_reranker.py
├─ docker-compose.yml        # One-command deploy
├─ pyproject.toml
├─ README.md / README.zh-TW.md
└─ ...
```

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Clone and setup
git clone https://github.com/tc3oliver/FreeRoute-RAG-Infra.git
cd FreeRoute-RAG-Infra

# Install dev dependencies
pip install -r requirements-dev.txt
pre-commit install

# Run tests
PYTHONPATH=$(pwd) pytest tests/unit/
```

### 🆘 Support

- 📖 **Documentation**: This README provides complete usage guide
- 🐛 **Issues**: [GitHub Issues](https://github.com/tc3oliver/FreeRoute-RAG-Infra/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/tc3oliver/FreeRoute-RAG-Infra/discussions)
- 🔄 **Updates**: Star & watch the repo for latest features

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

**Free & Open Source** - Build production GraphRAG infrastructure at zero cost! 🚀
