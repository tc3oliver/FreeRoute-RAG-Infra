# FreeRoute RAG Infra – API 參考（繁中）

> **以原始碼為準**：若本文與實際行為有出入，請直接比對你目前分支與 `main` 的差異，或打實際服務的 `/health`、`/whoami`。
> 關鍵檔案：`services/gateway/app.py`、`services/ingestor/app.py`、`services/reranker/server.py`、`configs/litellm.config.yaml`。

---

## 快速開始

```bash
docker compose up -d --build
```

**預設服務與連接埠**

* **LiteLLM Proxy（OpenAI 相容 /v1 + 儀表板）**：`9400`
* **API Gateway**：`9800`
* **Ingestor**：`9900`
* **Reranker**：`9080`（容器內聆聽 `8080`，Compose 對外映射 `9080`）
* **Qdrant**：`6333`
* **Neo4j**：`7474`（HTTP） / `7687`（Bolt）

---

## 認證（Authentication）

* **Gateway**：`X-API-Key: <key>`（或 `Authorization: Bearer <key>`）
  開發預設金鑰：`dev-key`（正式環境請設定 `API_GATEWAY_KEYS`）。
* **LiteLLM Proxy**：`Authorization: Bearer <LITELLM_MASTER_KEY>`
  建議使用 `LITELLM_MASTER_KEY`；相容 `LITELLM_KEY`（舊版）。
* **Reranker**：預設開發環境不啟用驗證。

---

## 健康檢查與服務資訊

```bash
# Gateway 健康檢查
curl -s http://localhost:9800/health | jq

# 組態/連線快照（需 API Key）
curl -s -H "X-API-Key: dev-key" http://localhost:9800/whoami | jq
```

---

## 端點總覽（除另註明皆屬 Gateway）

| 方法   | 路徑               | 目的            | 備註                               |
| ---- | ---------------- | ------------- | -------------------------------- |
| GET  | `/health`        | 存活/健康         | 行程健康即回 200                       |
| GET  | `/whoami`        | 組態快照          | 需 API Key                        |
| GET  | `/version`       | 版本            | 輕量查詢                             |
| GET  | `/metrics`       | Prometheus 度量 | 未安裝時回 204                        |
| POST | `/index/chunks`  | 上傳分段向量        | `local-embed` → Qdrant           |
| POST | `/search`        | 向量相似度搜尋       | 單一查詢嵌入 + Qdrant                  |
| POST | `/retrieve`      | 混合檢索          | 向量 +（可選）子圖 `include_subgraph`    |
| POST | `/chat`          | 對話補全          | `json_mode=true` 注入 JSON-only 提示 |
| POST | `/embed`         | 產生 Embeddings | 使用 `local-embed`（Ollama）         |
| POST | `/v1/chat/completions` | OpenAI 風格的對話補全 | OpenAI 相容端點 — 將 SDK 指向 Gateway `http://localhost:9800/v1` 並使用 Gateway API key |
| POST | `/v1/embeddings`  | OpenAI 風格的 Embeddings | OpenAI 相容的 embeddings 端點 — 使用 Gateway `http://localhost:9800/v1` |
| POST | `/rerank`        | 文本重排序         | 轉發至 Reranker（`RERANKER_URL`）     |
| POST | `/graph/extract` | 圖譜抽取          | Provider chain + Schema 驗證       |
| POST | `/graph/upsert`  | 寫入 Neo4j      | MERGE 節點/邊                       |
| POST | `/graph/query`   | Cypher 唯讀查詢   | 阻擋變更關鍵字                          |
| POST | `/graph/probe`   | Provider 探測   | 可強制嚴格 JSON 模式                    |

**Reranker（直接呼叫）**：`POST http://localhost:9080/rerank`

**Ingestor**

| 方法   | 路徑                  | 目的                        |
| ---- | ------------------- | ------------------------- |
| GET  | `/health`           | Ingestor + Gateway 可達性    |
| POST | `/ingest/directory` | 掃描 → 切分 → 嵌入 → 索引（可選圖譜抽取） |

> **尚未實作（Planned）**：`/ingest/file`、`/ingest/status/{job_id}`。

---

## 模型別名（取自 `configs/litellm.config.yaml`）

| 別名                       | 後端模型                                                       | 類別            | 回退鏈（Fallback）                |
| ------------------------ | ---------------------------------------------------------- | ------------- | ---------------------------- |
| `rag-answer`             | `openai/gpt-5-mini-2025-08-07`                             | chat          | → gemini → openrouter → groq |
| `rag-answer-gemini`      | `gemini/gemini-2.5-flash`                                  | chat          | 第二層                          |
| `rag-answer-openrouter`  | `openrouter/mistralai/mistral-small-3.2-24b-instruct:free` | chat          | 第三層                          |
| `rag-answer-groq`        | `groq/llama-3.1-8b-instant`                                | chat          | 第四層                          |
| `graph-extractor`        | `openai/gpt-5-mini-2025-08-07`                             | graph extract | → o1-mini → o1-mini → gemini |
| `graph-extractor-o1mini` | `openai/o1-mini-2024-09-12`                                | graph extract | 中繼重試                         |
| `graph-extractor-gemini` | `gemini/gemini-2.5-flash`                                  | graph extract | 末段後備                         |
| `local-embed`            | `ollama/bge-m3`                                            | embedding     | 本地                           |

**路由策略**：`usage_aware_fallback` + **TokenCap**（每日 OpenAI token 上限）+ **JSON guard**（結構化輸出）。

---

## API Gateway（Base：`http://localhost:9800`）

**Auth**：`X-API-Key: <key>`（或 Bearer）

### 使用 OpenAI SDK 指向 Gateway 的 /v1（OpenAI 風格）

如果你想直接用官方 OpenAI SDK（或相容的實作）呼叫 Gateway 的 OpenAI 風格 API（例如 `/v1/chat/completions`、`/v1/embeddings`），只要把 SDK 的 base URL 指向 `http://localhost:9800/v1`，並以 Gateway 的 API Key 當作 Bearer token（或使用 `X-API-Key` header）。這樣絕大多數現有程式碼不需要修改，只需更改 client 初始化的 endpoint 與金鑰。

範例（Python，使用 openai 的新版 client）

```python
from openai import OpenAI

# 指向 Gateway 的 OpenAI 兼容端點
client = OpenAI(base_url="http://localhost:9800/v1", api_key="dev-key")

# Chat
resp = client.chat.completions.create(
  model="rag-answer",
  messages=[{"role": "user", "content": "Summarize RAG in two sentences"}],
)
print(resp)

# Embeddings
emb = client.embeddings.create(model="local-embed", input=["What is RAG?"])
print(emb)
```

備註：Gateway 會驗證 `X-API-Key` 或 `Authorization: Bearer <key>`。開發預設金鑰為 `dev-key`。

### `POST /index/chunks` — 上傳分段向量至 Qdrant

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

### `POST /search` — 向量相似度搜尋

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

### `POST /retrieve` — 混合檢索（向量 + 可選子圖擴展）

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

**Response（形狀）**

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

### `POST /chat` — 對話補全（支援 JSON-only 模式）

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

### `POST /embed` — 取得 Embeddings（透過 LiteLLM `local-embed`/Ollama）

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

**Response（形狀）**

```json
{ "vectors": [[0.01, 0.02, "..."]], "dim": 1024 }
```

---

### `POST /rerank` — 文本重排序（Gateway 轉發至 Reranker）

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

**Response（形狀）**

```json
{ "results": [ { "index": 1, "score": 0.92, "text": "…" } ] }
```

---

### `POST /graph/extract` — 以 LLM 抽取圖譜，並做 Schema 驗證

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

**Response（形狀）**

```json
{
  "data": { "nodes": [/*…*/], "edges": [/*…*/] },
  "provider": "openai/gpt-5-mini-2025-08-07",
  "schema_hash": "…"
}
```

---

### `POST /graph/upsert` — 將節點/邊 Upsert 至 Neo4j（MERGE）

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

### `POST /graph/query` — 執行唯讀 Cypher

阻擋包含 `CREATE`、`MERGE`、`DELETE`、`DROP` 等變更關鍵字的請求。

**Example**

```bash
curl -X POST http://localhost:9800/graph/query \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"MATCH (p:Person)-[r]->(c:Company) RETURN p.id, type(r), c.id LIMIT 10"}' | jq
```

---

### `POST /graph/probe` — Provider 輕量探測（可強制嚴格 JSON）

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

## LiteLLM Proxy（Base：`http://localhost:9400/v1`）

**Auth**：`Authorization: Bearer <LITELLM_MASTER_KEY>`（預設 `sk-admin`）

提供 OpenAI 相容 API。`model` 直接使用**別名**。

**Chat 範例**

```bash
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{"model":"rag-answer","messages":[{"role":"user","content":"Summarize RAG in two sentences"}],"temperature":0.2}' | jq
```

**Embeddings 範例**

```bash
curl -s http://localhost:9400/v1/embeddings \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{"model":"local-embed","input":["What is GraphRAG?","Describe RAG."]}' | jq
```

### TokenCap（用量感知回退）

* 以 Redis key `tpd:openai:<YYYY-MM-DD>` 追蹤每日 OpenAI token 用量。
* 強制 `OPENAI_TPD_LIMIT`；超限時套用回退鏈（而非硬性失敗）。
* `graph-extractor*` 會注入 JSON Schema 並強制低溫（提升結構化機率）。
* 若 Redis 不可用 → **優雅降級**（不因限流而中斷）。
* `OPENAI_REROUTE_REAL=true`：超額時，**連真實 OpenAI 模型**也跟著改走回退鏈。

---

## 知識圖譜 Schema 位置

* **Repo**：`schemas/graph_schema.json`
* **Container**：`/app/schemas/graph_schema.json`（Compose 掛載）
* Gateway 啟動時會讀取並驗證；缺失/不合法會丟出明確錯誤。

---

## Ingestor 服務（Base：`http://localhost:9900`）

**已提供端點**

* `GET /health`：健康檢查 + Gateway 可達性
* `POST /ingest/directory`：資料夾掃描 → 切分 → 嵌入 → 索引（可選 `extract_graph`）

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

**錯誤碼與重試建議**

* `400` 參數/目錄錯誤
* `401/403` 與 Gateway 驗證不一致
* `429` 上游限流（建議退避重試）
* `5xx` 網路/Provider 異常

> **尚未實作（Planned）**：`POST /ingest/file`、`GET /ingest/status/{job_id}`。
> 未來可能提供 `MAX_PARALLEL_WORKERS` 調整併發度。

---

## Reranker（直接存取）

* 容器內聆聽 `8080`；Compose 對外 `9080`。
* **端點**：`POST /rerank`

**Example**

```bash
curl -X POST http://localhost:9080/rerank \
  -H "Content-Type: application/json" \
  -d '{"query":"What is AI?","documents":["d1","d2"],"top_n":2}' | jq
```

**Response（形狀）**

```json
{ "results": [ { "index": 0, "score": 0.88, "text": "…" } ] }
```

---

## 環境變數（常用）

**API / 驗證**

* `API_GATEWAY_KEYS`：Gateway 可用 Key（逗號分隔）
* `GATEWAY_BASE`、`GATEWAY_API_KEY`：Ingestor 呼叫 Gateway 使用
* `LITELLM_KEY`、`LITELLM_MASTER_KEY`：LiteLLM 驗證

**向量 / 圖譜**

* `QDRANT_URL`
* `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`

**Reranker**

* `RERANKER_URL`

**TokenCap / 預算**

* `OPENAI_TPD_LIMIT`：每日 OpenAI token 上限（整數）
* `OPENAI_REROUTE_REAL`：超額時是否連真實 OpenAI 模型也 reroute
* `max_budget_per_day`：LiteLLM `general_settings` 的每日 token 預算上限

**圖譜抽取**

* `GRAPH_MIN_NODES`、`GRAPH_MIN_EDGES`
* `GRAPH_MAX_ATTEMPTS`
* `GRAPH_ALLOW_EMPTY`
* `GRAPH_PROVIDER_CHAIN`
* `GRAPH_SCHEMA_PATH`

**切分（Chunking）**

* `CHUNK_SIZE`、`CHUNK_OVERLAP`

> 完整環境變數與容器對應，請以 `docker-compose.yml` 為準。

---

## 端到端示例流程

1. 將檔案放入 `data/`（如：`data/alice.md`）。
2. 進行索引：

   ```bash
   # 使用 Ingestor API
   curl -X POST http://localhost:9900/ingest/directory \
     -H "Content-Type: application/json" \
     -d '{"path":"/data","collection":"knowledge_base","extract_graph":true}' | jq
   ```

   或使用 CLI（見上文）。
3. 混合檢索：

   ```bash
   curl -X POST http://localhost:9800/retrieve \
     -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
     -d '{"query":"Who works at Acme Corporation?","include_subgraph":true}' | jq
   ```

---

## 疑難排解

* **搜尋結果為空**：檢查 embeddings 是否成功（LiteLLM/Ollama），以及 Qdrant collection 是否存在。
* **圖譜抽取不穩**：先試 `strict=false`、提高 `GRAPH_MAX_ATTEMPTS`、或調整 provider chain 以提升穩定/結構化。
* **GPU 容器**：安裝 NVIDIA Container Toolkit，並確認需要 GPU 的容器已配置裝置資源。
* **超過 Token 預算**：確認 `OPENAI_TPD_LIMIT` 與 `litellm.config.yaml` 的回退鏈；可加上 `max_budget_per_day` 作為額外保護。

---

## 後續工具／產物（Future / Tooling）

計畫性附加產物（可選）：

* 針對 **Gateway / Ingestor / Reranker** 自動輸出 **OpenAPI**（FastAPI）
* 由本文生成的 **Postman / Insomnia** 集合
* 依 Pydantic 回應模型導出 **JSON Schema**

---

**版本說明**：本文反映撰寫當下的分支狀態。實際行為以執行中的容器與 `/whoami` 為準。
