# Gateway Service

Language: [中文](README.zh.md) | [English](README.en.md)

The API Gateway for FreeRoute RAG Infra. It provides a unified RESTful API that integrates LLM chat, vector search, graph extraction/management, and reranking.

## 📁 Directory Structure

```
services/gateway/
├── app.py                          # FastAPI application entry point
├── config.py                       # Configuration and environment variables
├── deps.py                         # Dependency injection (API key auth)
├── middleware.py                   # Request tracing, logging, Prometheus metrics
├── models.py                       # Pydantic data models (Request/Response)
├── utils.py                        # Utilities (JSON parsing, graph normalization)
│
├── repositories/                   # External integrations
│   ├── litellm_client.py          # LiteLLM/OpenAI client wrapper
│   ├── qdrant_client.py           # Qdrant vector DB client wrapper
│   ├── neo4j_client.py            # Neo4j graph DB client wrapper
│   └── reranker_client.py         # Reranker HTTP client
│
├── services/                       # Business logic layer
│   ├── chat_service.py            # Chat and embedding services
│   ├── vector_service.py          # Vector indexing and retrieval
│   └── graph_service.py           # Graph extraction and query
│
└── routers/                        # API routers
    ├── meta.py                    # /health, /version, /whoami, /metrics
    ├── chat.py                    # /chat, /embed, /rerank
    ├── vector.py                  # /index/chunks, /search, /retrieve
    └── graph.py                   # /graph/extract, /graph/probe, /graph/upsert, /graph/query
```

---

## 🏗️ Architecture

### Layered Design

```
┌─────────────────────────────────────────┐
│         FastAPI Application             │  ← app.py
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│         Routers (API Layer)             │  ← routers/
│  - Route definitions and validation     │
│  - HTTP status and error handling       │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│       Services (Business Logic)         │  ← services/
│  - Orchestration and policies           │
│  - Multi-provider fallback & retries    │
│  - Data transformation & validation     │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│    Repositories (Data Access)           │  ← repositories/
│  - External API/DB wrappers             │
│  - Connection and error handling        │
└─────────────────────────────────────────┘
```

### Design Principles

- Single Responsibility Principle (SRP)
- Dependency Inversion Principle (DIP)
- Open/Closed Principle (OCP)
- Interface Segregation Principle (ISP)

---

## 🚀 Getting Started

### Environment Variables

```bash
# LiteLLM
export LITELLM_BASE="http://litellm:4000/v1"
export LITELLM_KEY="sk-admin"

# Vector DB (Qdrant)
export QDRANT_URL="http://qdrant:6333"

# Graph DB (Neo4j)
export NEO4J_URI="bolt://neo4j:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_password"

# Reranker service
export RERANKER_URL="http://reranker:8080"

# Graph Schema
export GRAPH_SCHEMA_PATH="/app/schemas/graph_schema.json"

# API Auth
export API_GATEWAY_KEYS="dev-key,prod-key-123"

# Optional
export APP_VERSION="v0.2.0"
export LOG_LEVEL="INFO"
export GRAPH_MIN_NODES="1"
export GRAPH_MIN_EDGES="1"
export GRAPH_MAX_ATTEMPTS="2"
export GRAPH_PROVIDER_CHAIN="graph-extractor,graph-extractor-o1mini,graph-extractor-gemini"
```

### Run the Service

```bash
# Development
uvicorn services.gateway.app:app --host 0.0.0.0 --port 9800 --reload

# Production
uvicorn services.gateway.app:app --host 0.0.0.0 --port 9800 --workers 4
```

### Docker

```bash
docker-compose up gateway
```

---

## 📡 API Endpoints

### Meta

| Path | Method | Description | Auth |
|------|--------|-------------|------|
| `/health` | GET | Health check | ❌ |
| `/version` | GET | Version info | ❌ |
| `/whoami` | GET | Config info | ✅ |
| `/metrics` | GET | Prometheus metrics | ❌ |

### Chat

| Path | Method | Description | Auth |
|------|--------|-------------|------|
| `/chat` | POST | Chat completion | ✅ |
| `/embed` | POST | Text embedding | ✅ |
| `/rerank` | POST | Rerank documents | ✅ |

### Vector

| Path | Method | Description | Auth |
|------|--------|-------------|------|
| `/index/chunks` | POST | Index text chunks | ✅ |
| `/search` | POST | Vector similarity search | ✅ |
| `/retrieve` | POST | Hybrid retrieval (vector + graph) | ✅ |

### Graph

| Path | Method | Description | Auth |
|------|--------|-------------|------|
| `/graph/extract` | POST | Extract graph from text | ✅ |
| `/graph/probe` | POST | Test provider JSON output | ✅ |
| `/graph/upsert` | POST | Upsert nodes/edges to Neo4j | ✅ |
| `/graph/query` | POST | Execute Cypher query | ✅ |

---

## 🔐 Authentication

Two auth methods are supported:

### 1. X-API-Key Header

```bash
curl -X POST http://localhost:9800/chat \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### 2. Bearer Token

```bash
curl -X POST http://localhost:9800/chat \
  -H "Authorization: Bearer dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

---

## 🧪 Testing

### Unit Tests

```bash
pytest tests/unit/test_gateway_*.py -v
```

### Integration Tests

```bash
# Service must be running
pytest tests/integration/test_gateway_smoke.py -v

# Or specify base and key via env vars
API_GATEWAY_BASE=http://localhost:9800 \
API_GATEWAY_KEY=dev-key \
pytest tests/integration/test_gateway_smoke.py -v
```

---

## 📦 Modules

### Repositories
- `litellm_client.py`: LiteLLM/OpenAI client
- `qdrant_client.py`: Qdrant client helpers
- `neo4j_client.py`: Neo4j driver
- `reranker_client.py`: Reranker HTTP client

### Services
- `chat_service.py`: Chat and embeddings
- `vector_service.py`: Vector indexing/search/retrieval
- `graph_service.py`: Graph extraction/probe/upsert/query

---

## 🔧 Configuration

### Graph Extraction Settings

```python
GRAPH_MIN_NODES = 1
GRAPH_MIN_EDGES = 1
GRAPH_ALLOW_EMPTY = False
GRAPH_MAX_ATTEMPTS = 2
PROVIDER_CHAIN = [
    "graph-extractor",
    "graph-extractor-o1mini",
    "graph-extractor-gemini",
]
```

### Middleware

- Request ID injection via `X-Request-ID`
- Structured logging: `request_id`, `client_ip`, `event`, `duration_ms`
- Prometheus metrics:
  - `gateway_requests_total`
  - `gateway_request_duration_seconds`

---

## 🐛 Troubleshooting

### Enable verbose logs

```bash
export LOG_LEVEL="DEBUG"
export DEBUG_GRAPH="true"
```

### Common issues

- `graph_schema.json not found`: Set `GRAPH_SCHEMA_PATH` correctly
- `qdrant_unavailable` / `neo4j_unavailable`: Ensure services are up and env vars are set
- `missing or invalid API key`: Check `API_GATEWAY_KEYS`

---

## 📈 Performance tips

```bash
uvicorn services.gateway.app:app \
  --host 0.0.0.0 \
  --port 9800 \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --timeout-keep-alive 75
```

---

## 🤝 Contributing

- Add a new integration: put a client in `repositories/`
- Add a new business feature: create a service in `services/`
- Add new endpoints: create a router in `routers/` and include it in `app.py`
- Code style: `black`, `isort`, and optional `mypy`

---

## 📚 Related Docs

- [API Usage](../../docs/en/api_usage.md)
- [Docker Compose](../../docker-compose.yml)
- [Graph Schema](../../schemas/graph_schema.json)
- [Roadmap](../../ROADMAP.md)

---

## 📄 License

MIT — see [LICENSE](../../LICENSE).
