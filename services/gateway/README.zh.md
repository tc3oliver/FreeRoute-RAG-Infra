# Gateway Service

語言: [中文](READM.zh.md) | [English](README.en.md)

FreeRoute RAG Infra 的 API Gateway 服務，提供統一的 RESTful API 入口，整合 LLM、向量檢索、圖譜管理與重排序功能。

## 📁 目錄結構

```
services/gateway/
├── app.py                          # FastAPI 應用入口
├── config.py                       # 配置管理與環境變數
├── deps.py                         # 依賴注入（API Key 驗證）
├── middleware.py                   # 請求追蹤、日誌與 Prometheus 指標
├── models.py                       # Pydantic 資料模型（Request/Response）
├── utils.py                        # 工具函式（JSON 解析、圖譜正規化）
│
├── repositories/                   # 外部系統整合層
│   ├── litellm_client.py          # LiteLLM/OpenAI 客戶端封裝
│   ├── qdrant_client.py           # Qdrant 向量資料庫客戶端
│   ├── neo4j_client.py            # Neo4j 圖資料庫客戶端
│   └── reranker_client.py         # Reranker HTTP 客戶端
│
├── services/                       # 業務邏輯層
│   ├── chat_service.py            # 對話與嵌入服務
│   ├── vector_service.py          # 向量索引與檢索服務
│   └── graph_service.py           # 圖譜抽取與查詢服務
│
└── routers/                        # API 路由層
    ├── meta.py                    # 元資料端點（/health, /version, /whoami, /metrics）
    ├── chat.py                    # 對話端點（/chat, /embed, /rerank）
    ├── vector.py                  # 向量端點（/index/chunks, /search, /retrieve）
    └── graph.py                   # 圖譜端點（/graph/extract, /graph/probe, /graph/upsert, /graph/query）
```

---

## 🏗️ 架構設計

### 分層架構（Layered Architecture）

```
┌─────────────────────────────────────────┐
│         FastAPI Application             │  ← app.py
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│         Routers (API Layer)             │  ← routers/
│  - 路由定義與請求驗證                    │
│  - HTTP 狀態碼與錯誤處理                 │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│       Services (Business Logic)         │  ← services/
│  - 業務邏輯編排                          │
│  - 多 Provider 容錯與重試                │
│  - 資料轉換與驗證                        │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│    Repositories (Data Access)           │  ← repositories/
│  - 外部 API/資料庫封裝                   │
│  - 連線管理與錯誤處理                    │
└─────────────────────────────────────────┘
```

### 設計原則

- **單一職責原則（SRP）**：每個模組只負責一項功能
- **依賴反轉原則（DIP）**：高層模組不依賴低層模組，透過介面注入
- **開放封閉原則（OCP）**：對擴展開放，對修改封閉
- **介面隔離原則（ISP）**：使用小型、專用的介面

---

## 🚀 快速開始

### 環境變數

```bash
# LiteLLM 設定
export LITELLM_BASE="http://litellm:4000/v1"
export LITELLM_KEY="sk-admin"

# 向量資料庫（Qdrant）
export QDRANT_URL="http://qdrant:6333"

# 圖資料庫（Neo4j）
export NEO4J_URI="bolt://neo4j:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_password"

# Reranker 服務
export RERANKER_URL="http://reranker:8080"

# Graph Schema
export GRAPH_SCHEMA_PATH="/app/schemas/graph_schema.json"

# API 認證
export API_GATEWAY_KEYS="dev-key,prod-key-123"

# 可選配置
export APP_VERSION="v0.2.0"
export LOG_LEVEL="INFO"
export GRAPH_MIN_NODES="1"
export GRAPH_MIN_EDGES="1"
export GRAPH_MAX_ATTEMPTS="2"
export GRAPH_PROVIDER_CHAIN="graph-extractor,graph-extractor-o1mini,graph-extractor-gemini"
```

### 啟動服務

```bash
# 開發模式
uvicorn services.gateway.app:app --host 0.0.0.0 --port 9800 --reload

# 生產模式
uvicorn services.gateway.app:app --host 0.0.0.0 --port 9800 --workers 4
```

### Docker 啟動

```bash
docker-compose up gateway
```

---

## 📡 API 端點

### 元資料 Endpoints

| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/health` | GET | 健康檢查 | ❌ |
| `/version` | GET | 版本資訊 | ❌ |
| `/whoami` | GET | 配置資訊 | ✅ |
| `/metrics` | GET | Prometheus 指標 | ❌ |

### 對話 Endpoints

| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/chat` | POST | 對話生成 | ✅ |
| `/embed` | POST | 文本嵌入 | ✅ |
| `/rerank` | POST | 文檔重排序 | ✅ |

### 向量 Endpoints

| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/index/chunks` | POST | 索引文本塊 | ✅ |
| `/search` | POST | 向量相似度搜尋 | ✅ |
| `/retrieve` | POST | 混合檢索（向量+圖譜） | ✅ |

### 圖譜 Endpoints

| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/graph/extract` | POST | 從文本抽取圖譜 | ✅ |
| `/graph/probe` | POST | 測試 Provider JSON 能力 | ✅ |
| `/graph/upsert` | POST | 插入/更新圖譜節點與邊 | ✅ |
| `/graph/query` | POST | 執行 Cypher 查詢 | ✅ |

---

## 🔐 認證

所有需要認證的端點支援兩種方式：

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

## 🧪 測試

### 執行單元測試

```bash
# 執行所有 gateway 測試
pytest tests/unit/test_gateway_*.py -v

# 執行特定測試
pytest tests/unit/test_gateway_graph_extract.py -v

# 產生覆蓋率報告
pytest tests/unit/test_gateway_*.py --cov=services.gateway --cov-report=html
```

### 執行整合測試

```bash
# 需要先啟動服務
pytest tests/integration/test_gateway_smoke.py -v

# 或使用環境變數指定服務位址
API_GATEWAY_BASE=http://localhost:9800 \
API_GATEWAY_KEY=dev-key \
pytest tests/integration/test_gateway_smoke.py -v
```

---

## 📦 模組說明

### Repositories 層

#### `litellm_client.py`
- **職責**：封裝 LiteLLM/OpenAI API 客戶端
- **主要函式**：
  - `get_litellm_client() -> OpenAI`：獲取單例客戶端

#### `qdrant_client.py`
- **職責**：封裝 Qdrant 向量資料庫操作
- **主要函式**：
  - `get_qdrant_client() -> QdrantClient`：連接 Qdrant
  - `ensure_qdrant_collection(client, name, dim)`：確保集合存在

#### `neo4j_client.py`
- **職責**：封裝 Neo4j 圖資料庫操作
- **主要函式**：
  - `get_neo4j_driver() -> Driver`：獲取 Neo4j Driver

#### `reranker_client.py`
- **職責**：封裝 Reranker HTTP 服務呼叫
- **主要函式**：
  - `call_reranker(query, documents, top_n) -> Dict`：呼叫重排序服務

---

### Services 層

#### `chat_service.py` - ChatService
處理對話生成與文本嵌入。

**主要方法**：
- `chat(req: ChatReq, client_ip: str) -> Dict`
  - 支援 JSON mode
  - 自動重試 429 錯誤
  - 回應格式自動解析

- `embed(req: EmbedReq) -> Dict`
  - 批次生成文本嵌入向量
  - 回傳向量維度資訊

#### `vector_service.py` - VectorService
處理向量索引、搜尋與混合檢索。

**主要方法**：
- `index_chunks(req: IndexChunksReq) -> Dict`
  - 生成 embeddings
  - 寫入 Qdrant
  - 自動 UUID 生成

- `search(req: SearchReq) -> Dict`
  - 向量相似度搜尋
  - 支援過濾條件

- `retrieve(req: RetrieveReq) -> Dict`
  - 混合檢索（向量 + 圖譜）
  - 圖譜鄰域展開
  - 多來源引用標註

#### `graph_service.py` - GraphService
處理圖譜抽取、修復、存儲與查詢。

**主要方法**：
- `extract(req: GraphReq, client_ip: str) -> Dict`
  - 多 Provider 容錯機制
  - 自動 JSON 修復
  - Schema 驗證
  - 質量閾值檢查

- `probe(req: GraphProbeReq, client_ip: str) -> Dict`
  - 測試 Provider JSON 生成能力

- `upsert(req: GraphUpsertReq) -> Dict`
  - 插入/更新圖譜到 Neo4j
  - MERGE 語法避免重複

- `query(req: GraphQueryReq) -> Dict`
  - 執行唯讀 Cypher 查詢
  - 安全檢查（禁止寫入操作）

---

## 🔧 配置說明

### Graph 抽取配置

```python
# config.py
GRAPH_MIN_NODES = 1              # 最小節點數量
GRAPH_MIN_EDGES = 1              # 最小邊數量
GRAPH_ALLOW_EMPTY = False        # 是否允許空圖
GRAPH_MAX_ATTEMPTS = 2           # 每個 Provider 最大重試次數
PROVIDER_CHAIN = [               # Provider 優先順序
    "graph-extractor",
    "graph-extractor-o1mini",
    "graph-extractor-gemini"
]
```

### Middleware 配置

- **請求追蹤**：每個請求自動分配 `X-Request-ID`
- **結構化日誌**：包含 `request_id`, `client_ip`, `event`, `duration_ms`
- **Prometheus 指標**：
  - `gateway_requests_total`：請求總數（按 method, endpoint, status）
  - `gateway_request_duration_seconds`：請求延遲（按 method, endpoint）

---

## 🐛 除錯

### 啟用詳細日誌

```bash
export LOG_LEVEL="DEBUG"
export DEBUG_GRAPH="true"  # 圖譜抽取詳細日誌
```

### 常見問題

#### 1. `graph_schema.json not found`
**解決**：確保環境變數 `GRAPH_SCHEMA_PATH` 指向正確路徑
```bash
export GRAPH_SCHEMA_PATH="/path/to/schemas/graph_schema.json"
```

#### 2. `qdrant_unavailable` / `neo4j_unavailable`
**解決**：檢查對應服務是否啟動，環境變數是否正確
```bash
# 測試 Qdrant
curl http://qdrant:6333/collections

# 測試 Neo4j
cypher-shell -a bolt://neo4j:7687 -u neo4j -p password
```

#### 3. `missing or invalid API key`
**解決**：檢查 `API_GATEWAY_KEYS` 環境變數與請求 Header
```bash
export API_GATEWAY_KEYS="dev-key,prod-key"
```

---

## 📊 效能優化

### 建議配置

```bash
# 生產環境 workers 數量
uvicorn services.gateway.app:app \
  --host 0.0.0.0 \
  --port 9800 \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --timeout-keep-alive 75
```

### 最佳實踐

1. **使用連線池**：Qdrant/Neo4j 客戶端會自動管理連線
2. **批次處理**：`/index/chunks` 支援批次索引多個文本塊
3. **非同步 I/O**：未來可考慮改用 `async/await` 提升並發
4. **快取策略**：可在 Service 層加入 Redis 快取

---

## 🤝 貢獻指南

### 新增功能

1. **新增 Repository**：在 `repositories/` 建立新檔案
2. **新增 Service**：在 `services/` 建立服務類別
3. **新增 Router**：在 `routers/` 建立路由檔案
4. **更新 `app.py`**：註冊新的 router

### 程式碼風格

```bash
# 格式化
black services/gateway --line-length 120

# 排序 imports
isort services/gateway --profile black

# 型別檢查（可選）
mypy services/gateway --config-file mypy.ini
```

### 測試要求

- 所有新功能需有對應的單元測試
- 測試覆蓋率應 > 80%
- 測試應可獨立執行（使用 mock）

---

## 📚 相關文件

- [API 使用說明](../../docs/zh/api_usage.md)
- [Docker Compose 配置](../../docker-compose.yml)
- [Graph Schema 定義](../../schemas/graph_schema.json)
- [專案 Roadmap](../../ROADMAP.md)

---

## 📄 授權

此專案採用 MIT 授權條款，詳見 [LICENSE](../../LICENSE)。
