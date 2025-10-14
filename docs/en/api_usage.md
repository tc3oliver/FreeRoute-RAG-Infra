# FreeRoute RAG Infra – API Reference (EN)

> **Source of truth**: the code. If anything here looks off, diff your current branch with `main`, or inspect live endpoints via `/health` and `/whoami`.
> Code files: `services/gateway/app.py`, `services/ingestor/app.py`, `services/reranker/server.py`, `configs/litellm.config.yaml`.

---

## Quick Start

```bash
docker compose up -d --build
```

**Default services & ports**

* **LiteLLM Proxy (OpenAI-compatible /v1 + dashboard)**: `9400`
* **API Gateway**: `9800`
* **Ingestor**: `9900`
* **Reranker**: `9080` (container listens on `8080`, Compose maps to `9080`)
* **Qdrant**: `6333`
* **Neo4j**: `7474` (HTTP) / `7687` (Bolt)

---

## Authentication

* **Gateway**: `X-API-Key: <key>` (or `Authorization: Bearer <key>`)
  Dev key: `dev-key` (set `API_GATEWAY_KEYS` for prod).
* **LiteLLM Proxy**: `Authorization: Bearer <LITELLM_MASTER_KEY>`
  (`LITELLM_MASTER_KEY` preferred; `LITELLM_KEY` supported for legacy).
* **Reranker**: no auth in the default dev setup.

---

## Health & Service Info

```bash
# Gateway
curl -s http://localhost:9800/health | jq

# Snapshot of config / wiring (requires API key)
curl -s -H "X-API-Key: dev-key" http://localhost:9800/whoami | jq
```

---

## Endpoint Summary (Gateway unless noted)

| Method | Path             | Purpose                    | Notes                                           |
| ------ | ---------------- | -------------------------- | ----------------------------------------------- |
| GET    | `/health`        | Liveness/health            | 200 when process healthy                        |
| GET    | `/whoami`        | Config snapshot            | Requires API key                                |
| GET    | `/version`       | App version                | Lightweight                                     |
| GET    | `/metrics`       | Prometheus metrics         | 204 if metrics lib not installed                |
| POST   | `/index/chunks`  | Upsert chunk vectors       | `local-embed` → Qdrant                          |
| POST   | `/search`        | Vector similarity search   | Single-query embedding + Qdrant                 |
| POST   | `/retrieve`      | Hybrid retrieval           | Vector + optional subgraph (`include_subgraph`) |
| POST   | `/chat`          | Chat completions           | `json_mode=true` injects JSON-only hint         |
| POST   | `/embed`         | Embeddings                 | Uses `local-embed` (Ollama)                     |
| POST   | `/rerank`        | Rerank docs                | Forwards to Reranker (`RERANKER_URL`)           |
| POST   | `/graph/extract` | LLM graph extraction       | Provider chain + schema validation              |
| POST   | `/graph/upsert`  | Write nodes/edges to Neo4j | MERGE nodes/edges                               |
| POST   | `/graph/query`   | Cypher read-only           | Mutating keywords blocked                       |
| POST   | `/graph/probe`   | Provider conformance probe | Optional strict JSON mode                       |

**Reranker (direct)**: `POST http://localhost:9080/rerank`
**Ingestor**

| Method | Path                | Purpose                                       |
| ------ | ------------------- | --------------------------------------------- |
| GET    | `/health`           | Ingestor + Gateway reachability               |
| POST   | `/ingest/directory` | Scan → chunk → index (optional graph extract) |

> **Planned (not implemented)**: `/ingest/file`, `/ingest/status/{job_id}`.

---

## Model Aliases (via `configs/litellm.config.yaml`)

| Alias                    | Backend Model                                              | Category      | Fallback Chain               |
| ------------------------ | ---------------------------------------------------------- | ------------- | ---------------------------- |
| `rag-answer`             | `openai/gpt-5-mini-2025-08-07`                             | chat          | → gemini → openrouter → groq |
| `rag-answer-gemini`      | `gemini/gemini-2.5-flash`                                  | chat          | secondary                    |
| `rag-answer-openrouter`  | `openrouter/mistralai/mistral-small-3.2-24b-instruct:free` | chat          | tertiary                     |
| `rag-answer-groq`        | `groq/llama-3.1-8b-instant`                                | chat          | quaternary                   |
| `graph-extractor`        | `openai/gpt-5-mini-2025-08-07`                             | graph extract | → o1-mini → o1-mini → gemini |
| `graph-extractor-o1mini` | `openai/o1-mini-2024-09-12`                                | graph extract | mid-chain retry              |
| `graph-extractor-gemini` | `gemini/gemini-2.5-flash`                                  | graph extract | tail fallback                |
| `local-embed`            | `ollama/bge-m3`                                            | embedding     | local                        |

**Routing strategy**: `usage_aware_fallback` + **TokenCap** (daily OpenAI token cap) + **JSON guard** for schema’d calls.

---

## API Gateway (Base: `http://localhost:9800`)

**Auth**: `X-API-Key: <key>` (or Bearer)

### `POST /index/chunks`

Upsert chunk vectors to Qdrant.

**Request**

```json
{
  "collection": "chunks",
  "chunks": [
    { "doc_id": "doc1", "text": "…", "metadata": { "file_path": "/data/doc1.md" } }
  ]
}
```

**Example**

```bash
curl -X POST http://localhost:9800/index/chunks \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"collection":"kb","chunks":[{"doc_id":"alice","text":"Alice...","metadata":{}}]}' | jq
```

---

### `POST /search`

Vector similarity search.

**Request**

```json
{ "query": "Python engineer skills", "top_k": 5, "collection": "chunks" }
```

**Example**

```bash
curl -X POST http://localhost:9800/search \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"Python engineer skills","top_k":3,"collection":"knowledge_base"}' | jq
```

---

### `POST /retrieve`

Hybrid retrieval (vector + optional knowledge-graph expansion).

**Request**

```json
{
  "query": "Who works at Acme Corporation and what skills do they have?",
  "top_k": 5,
  "collection": "knowledge_base",
  "include_subgraph": true,
  "max_hops": 2
}
```

**Example**

```bash
curl -X POST http://localhost:9800/retrieve \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"Who works at Acme and what skills?","top_k":5,"include_subgraph":true}' | jq
```

**Response (shape)**

```json
{
  "hits": [
    { "id": "…", "score": 0.73, "text": "…", "metadata": { "…" : "…" } }
  ],
  "subgraph": { "nodes": [/*…*/], "edges": [/*…*/] },
  "query_time_ms": 123
}
```

---

### `POST /chat`

Chat completions; supports `json_mode` to request JSON-only responses (Gateway injects a JSON-only hint).

**Request**

```json
{
  "messages": [{ "role": "user", "content": "Reply in JSON with two bullets" }],
  "json_mode": true,
  "temperature": 0.2
}
```

**Example**

```bash
curl -X POST http://localhost:9800/chat \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"List two benefits of RAG in JSON"}],"json_mode":true}' | jq
```

---

### `POST /embed`

Raw embeddings via LiteLLM `local-embed` (Ollama).

**Request**

```json
{ "texts": ["What is RAG?", "What is GraphRAG?"] }
```

**Example**

```bash
curl -X POST http://localhost:9800/embed \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"texts":["What is RAG?","GraphRAG?"]}' | jq
```

**Response (shape)**

```json
{ "vectors": [[0.01, 0.02, "..."]], "dim": 1024 }
```

---

### `POST /rerank`

Rerank an array of documents. The Gateway forwards to the Reranker service at `RERANKER_URL`.

**Request**

```json
{ "query": "What is generative AI?", "documents": ["doc1","doc2"], "top_n": 3 }
```

**Example**

```bash
curl -X POST http://localhost:9800/rerank \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"What is AI","documents":["A","B"],"top_n":2}' | jq
```

**Response (shape)**

```json
{ "results": [ { "index": 1, "score": 0.92, "text": "…" } ] }
```

---

### `POST /graph/extract`

LLM-based graph extraction with JSON schema validation.

**Request**

```json
{ "context": "Alice joined Acme in 2022 as an engineer located in Taipei.", "strict": false }
```

**Example**

```bash
curl -X POST http://localhost:9800/graph/extract \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"context":"Alice joined Acme in 2022...","strict":false}' | jq
```

**Response (shape)**

```json
{
  "data": { "nodes": [/*…*/], "edges": [/*…*/] },
  "provider": "openai/gpt-5-mini-2025-08-07",
  "schema_hash": "…"
}
```

---

### `POST /graph/upsert`

Upsert graph nodes/edges to Neo4j (MERGE semantics).

**Request**

```json
{
  "data": {
    "nodes": [
      { "id": "Alice", "type": "Person", "props": [ { "key": "role", "value": "Engineer" } ] }
    ],
    "edges": [
      { "src": "Alice", "dst": "Acme", "type": "WORKS_AT", "props": [] }
    ]
  }
}
```

---

### `POST /graph/query`

Run read-only Cypher queries. Requests containing mutating keywords (e.g., `CREATE`, `MERGE`, `DELETE`, `DROP`) are blocked.

**Example**

```bash
curl -X POST http://localhost:9800/graph/query \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"MATCH (p:Person)-[r]->(c:Company) RETURN p.id, type(r), c.id LIMIT 10"}' | jq
```

---

### `POST /graph/probe`

Lightweight provider probe for JSON adherence and text fallback.

**Request**

```json
{ "model": "graph-extractor", "strict_json": true }
```

**Example**

```bash
curl -X POST http://localhost:9800/graph/probe \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"model":"graph-extractor","strict_json":true}' | jq
```

**Response**

```json
{
  "ok": true,
  "mode": "json",
  "data": { "sample": true },
  "provider": "openai/gpt-5-mini-2025-08-07"
}
```

---

## LiteLLM Proxy (Base: `http://localhost:9400/v1`)

**Auth**: `Authorization: Bearer <LITELLM_MASTER_KEY>` (default `sk-admin`)

OpenAI-compatible API. Use *alias names* directly in `model`.

**Chat example**

```bash
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{"model":"rag-answer","messages":[{"role":"user","content":"Summarize RAG in two sentences"}],"temperature":0.2}' | jq
```

**Embeddings example**

```bash
curl -s http://localhost:9400/v1/embeddings \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{"model":"local-embed","input":["What is GraphRAG?","Describe RAG."]}' | jq
```

### TokenCap (usage-aware fallback)

* Tracks daily OpenAI token usage in Redis key `tpd:openai:<YYYY-MM-DD>`.
* Enforces `OPENAI_TPD_LIMIT`. Upon exceed, applies the configured fallback chain (vs. failing hard).
* Graph-extraction entries inject JSON schema and force low temperature for structured output.
* Graceful degradation if Redis is unreachable (no hard fail).
* `OPENAI_REROUTE_REAL=true` will also reroute real OpenAI models when over the cap.

---

## Knowledge Graph – Schema Location

* **Repo**: `schemas/graph_schema.json`
* **Container**: `/app/schemas/graph_schema.json` (mounted via Compose)
* Gateway loads and validates schema on startup (a missing/invalid schema will raise an explicit error).

---

## Ingestor Service (Base: `http://localhost:9900`)

**Implemented**

* `GET /health` – health + gateway reachability
* `POST /ingest/directory` – directory scan → chunk → embed → index (optional graph extract)

**Request**

```json
{
  "path": "/data",
  "collection": "knowledge_base",
  "file_patterns": ["*.md", "*.txt"],
  "chunk_size": 800,
  "overlap": 50,
  "extract_graph": true,
  "force_reprocess": false,
  "parallelism": 4
}
```

**CLI**

```bash
python services/ingestor/cli.py ./data \
  --ingestor-url http://localhost:9900 \
  --collection knowledge_base \
  --extract-graph
```

**Error codes & retry**

* `400` invalid directory / bad request
* `401/403` auth mismatch with Gateway
* `429` upstream rate-limit (retry with backoff)
* `5xx` network / provider issues

> **Planned (not implemented)**: `POST /ingest/file`, `GET /ingest/status/{job_id}`.
> Future versions may introduce `MAX_PARALLEL_WORKERS` to cap ingestion parallelism.

---

## Reranker (Direct Access)

* Container listens on `8080`; Compose exposes `9080`.
* **Endpoint**: `POST /rerank`

**Example**

```bash
curl -X POST http://localhost:9080/rerank \
  -H "Content-Type: application/json" \
  -d '{"query":"What is AI?","documents":["d1","d2"],"top_n":2}' | jq
```

**Response (shape)**

```json
{ "results": [ { "index": 0, "score": 0.88, "text": "…" } ] }
```

---

## Environment Variables (selected)

**API / Auth**

* `API_GATEWAY_KEYS` — comma-separated list of allowed Gateway keys
* `GATEWAY_BASE`, `GATEWAY_API_KEY` — used by Ingestor to call Gateway
* `LITELLM_KEY`, `LITELLM_MASTER_KEY` — LiteLLM auth

**Vector / Graph**

* `QDRANT_URL`
* `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`

**Reranker**

* `RERANKER_URL`

**TokenCap / Budget**

* `OPENAI_TPD_LIMIT` — daily OpenAI token cap (integer)
* `OPENAI_REROUTE_REAL` — whether to reroute real OpenAI models when over cap
* `max_budget_per_day` — LiteLLM `general_settings` daily token budget ceiling

**Graph Extraction**

* `GRAPH_MIN_NODES`, `GRAPH_MIN_EDGES`
* `GRAPH_MAX_ATTEMPTS`
* `GRAPH_ALLOW_EMPTY`
* `GRAPH_PROVIDER_CHAIN`
* `GRAPH_SCHEMA_PATH`

**Chunking**

* `CHUNK_SIZE`, `CHUNK_OVERLAP`

> See `docker-compose.yml` for the full set and per-container wiring.

---

## Example End-to-End Flow

1. Put your files under `data/` (e.g., `data/alice.md`).
2. Ingest:

   ```bash
   curl -X POST http://localhost:9900/ingest/directory \
     -H "Content-Type: application/json" \
     -d '{"path":"/data","collection":"knowledge_base","extract_graph":true}' | jq
   ```

   or use the CLI (see Ingestor section).
3. Query (hybrid retrieval):

   ```bash
   curl -X POST http://localhost:9800/retrieve \
     -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
     -d '{"query":"Who works at Acme Corporation?","include_subgraph":true}' | jq
   ```

---

## Troubleshooting

* **Empty search results**: verify embeddings (LiteLLM/Ollama) generated successfully and target Qdrant collection exists.
* **Graph extraction flaky**: try `strict=false`, raise `GRAPH_MAX_ATTEMPTS`, or adjust the provider chain to a more deterministic model first.
* **GPU**: ensure NVIDIA Container Toolkit is installed and devices are available to the containers that need them.
* **Token budget exceeded**: confirm `OPENAI_TPD_LIMIT` and fallbacks in `litellm.config.yaml`; consider `max_budget_per_day` for an extra guard.

---

## Future / Tooling

Planned optional artifacts:

* Auto-generated **OpenAPI** exports (FastAPI) for **Gateway**, **Ingestor**, and **Reranker**
* **Postman / Insomnia** collection produced from this doc
* JSON Schemas derived from Pydantic response models

---

**Version**: reflects the current branch at the time of editing. For exact behavior, prefer: running containers + hitting `/whoami`.
