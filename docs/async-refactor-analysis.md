# 異步化架構改造分析報告

> **日期**: 2025-10-19
> **版本**: v0.2.0
> **分支**: `feature/async-architecture-refactor`

## 📊 當前狀態分析

### 1. 服務層（services/）

#### ChatService (`chat_service.py`)
- **狀態**: ❌ 完全同步
- **問題點**:
  - `chat()`: 使用同步 `client.chat.completions.create()`
  - `embed()`: 使用同步 `client.embeddings.create()`
  - 無並發處理能力
- **影響**: 阻塞 I/O 導致低吞吐量

#### VectorService (`vector_service.py`)
- **狀態**: ❌ 完全同步
- **問題點**:
  - `index_chunks()`: 同步嵌入生成 + Qdrant 寫入
  - `search()`: 同步嵌入生成 + Qdrant 查詢
  - `retrieve()`: 同步嵌入 + Qdrant + Neo4j 查詢（串行執行）
  - `_expand_graph_neighborhood()`: 同步 Neo4j 查詢
- **影響**: 多步驟操作無法並行，延遲累加

#### GraphService (`graph_service.py`)
- **狀態**: ❌ 完全同步
- **問題點**:
  - `probe()`: 同步 LLM 調用
  - `extract()`: 多次串行 LLM 調用（provider fallback）
  - `upsert()`: 同步 Neo4j 批量寫入
  - `query()`: 同步 Neo4j 查詢
- **影響**: 多供應商回退策略無法並行嘗試

### 2. 數據庫客戶端（repositories/）

#### LiteLLM Client (`litellm_client.py`)
- **狀態**: ❌ 使用同步 `OpenAI` 客戶端
- **需要**: 遷移至 `openai.AsyncOpenAI`

#### Qdrant Client (`qdrant_client.py`)
- **狀態**: ❌ 使用同步 `QdrantClient`
- **需要**: 遷移至 `httpx.AsyncClient` 或 `AsyncQdrantClient`

#### Neo4j Driver (`neo4j_client.py`)
- **狀態**: ❌ 使用同步 `GraphDatabase.driver()`
- **需要**: 遷移至 `neo4j.AsyncDriver`

#### Reranker Client (`reranker_client.py`)
- **狀態**: ❌ 使用同步 `requests.post()`
- **需要**: 遷移至 `httpx.AsyncClient`

### 3. 路由層（routers/）

#### Chat Router (`routers/chat.py`)
- **狀態**: ⚠️ 部分同步
- **端點**:
  - `POST /chat`: 同步函數，調用同步服務
  - `POST /embed`: 同步函數，調用同步服務
  - `POST /rerank`: 同步函數，調用同步服務
- **需要**: 改為 `async def`

### 4. 依賴項（deps.py）

- **狀態**: 需要檢查和更新
- **可能問題**: 依賴注入函數可能需要支持異步

## 🎯 改造計劃

### Phase 1: 基礎設施準備（1-2 天）

#### 任務 1.1: 更新依賴項
```txt
# 添加到 requirements.txt
httpx>=0.28.1,<1.0.0          # 異步 HTTP 客戶端
aiofiles>=24.1.0,<25.0.0      # 異步文件操作
pytest-asyncio>=0.24.0,<1.0.0 # 異步測試支持
```

#### 任務 1.2: 創建異步客戶端基礎

**優先級**: ⭐⭐⭐⭐⭐

### Phase 2: 客戶端層異步化（3-5 天）

#### 任務 2.1: LiteLLM Client → AsyncOpenAI
```python
# 修改 litellm_client.py
from openai import AsyncOpenAI

_async_client: AsyncOpenAI | None = None

async def get_async_litellm_client() -> AsyncOpenAI:
    global _async_client
    if _async_client is None:
        _async_client = AsyncOpenAI(
            base_url=LITELLM_BASE,
            api_key=LITELLM_KEY,
            timeout=30.0,
            max_retries=2,
        )
    return _async_client
```

**預估**: 0.5 天
**優先級**: ⭐⭐⭐⭐⭐

#### 任務 2.2: Qdrant Client → httpx.AsyncClient
```python
# 選項 A: 官方 AsyncQdrantClient（推薦）
from qdrant_client import AsyncQdrantClient

# 選項 B: 自定義 httpx wrapper
async def async_search(collection: str, vector: List[float], limit: int):
    async with httpx.AsyncClient() as client:
        response = await client.post(...)
        return response.json()
```

**預估**: 1-1.5 天
**優先級**: ⭐⭐⭐⭐⭐

#### 任務 2.3: Neo4j Driver → AsyncDriver
```python
# 修改 neo4j_client.py
from neo4j import AsyncGraphDatabase

async def get_async_neo4j_driver():
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )
    return driver

async def execute_query(driver, query: str, params: dict):
    async with driver.session() as session:
        result = await session.run(query, **params)
        records = [record async for record in result]
        return records
```

**預估**: 1-1.5 天
**優先級**: ⭐⭐⭐⭐⭐

#### 任務 2.4: Reranker Client → httpx.AsyncClient
```python
# 修改 reranker_client.py
import httpx

async def call_reranker_async(query: str, documents: List[str], top_n: int = 6):
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{RERANKER_URL}/rerank",
            json={"query": query, "documents": documents, "top_n": top_n},
        )
        response.raise_for_status()
        return response.json()
```

**預估**: 0.5 天
**優先級**: ⭐⭐⭐⭐

### Phase 3: 服務層異步化（5-7 天）

#### 任務 3.1: ChatService 異步化
```python
class ChatService:
    def __init__(self):
        self.client = None  # 延遲初始化

    async def _ensure_client(self):
        if self.client is None:
            self.client = await get_async_litellm_client()

    async def chat(self, req: ChatReq, client_ip: str) -> Dict[str, Any]:
        await self._ensure_client()
        # ... 使用 await self.client.chat.completions.create()

    async def embed(self, req: EmbedReq) -> Dict[str, Any]:
        await self._ensure_client()
        # ... 使用 await self.client.embeddings.create()
```

**預估**: 1 天
**優先級**: ⭐⭐⭐⭐⭐
**測試**: 更新 `test_gateway_chat_service.py`

#### 任務 3.2: VectorService 異步化

**關鍵優化**:
```python
async def index_chunks(self, req: IndexChunksReq):
    # 1. 並行生成嵌入（批量）
    embeddings = await self._batch_embed(texts)

    # 2. 並行寫入 Qdrant
    await qdrant_client.upsert(...)

async def retrieve(self, req: RetrieveReq):
    # 並行執行向量搜索和圖譜擴展
    vector_task = asyncio.create_task(self._vector_search(req))
    graph_task = asyncio.create_task(self._expand_graph(req))

    vector_hits, subgraph = await asyncio.gather(
        vector_task, graph_task,
        return_exceptions=True
    )
```

**預估**: 2-3 天
**優先級**: ⭐⭐⭐⭐⭐
**並發增益**: 最高（向量+圖譜並行）

#### 任務 3.3: GraphService 異步化

**關鍵優化**:
```python
async def extract(self, req: GraphReq, client_ip: str):
    # 多供應商並行嘗試（而非串行回退）
    tasks = []
    for provider in provider_chain[:3]:  # 同時嘗試前3個
        tasks.append(self._try_extract(provider, req))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 選擇最佳結果
    for result in results:
        if isinstance(result, dict) and result.get("ok"):
            return result
```

**預估**: 2-3 天
**優先級**: ⭐⭐⭐⭐⭐
**並發增益**: 高（多供應商並行）

### Phase 4: 路由層整合（1-2 天）

#### 任務 4.1: 更新所有路由為 async def
```python
@router.post("/chat")
async def chat(
    req: ChatReq,
    request: Request,
    service: ChatService = Depends(get_chat_service)
):
    return await service.chat(req, request.client.host)
```

**預估**: 1 天
**優先級**: ⭐⭐⭐⭐⭐

#### 任務 4.2: 更新依賴注入
```python
# deps.py
async def get_chat_service() -> ChatService:
    service = ChatService()
    await service._ensure_client()
    return service
```

**預估**: 0.5 天
**優先級**: ⭐⭐⭐⭐

### Phase 5: 測試與驗證（3-4 天）

#### 任務 5.1: 更新單元測試
- 使用 `@pytest.mark.asyncio`
- 修改所有 `def test_` → `async def test_`
- 使用 `await` 調用異步服務

**預估**: 2 天
**優先級**: ⭐⭐⭐⭐⭐

#### 任務 5.2: 性能基準測試
```python
# tests/performance/test_async_throughput.py
import asyncio
import time

async def test_concurrent_requests():
    tasks = [service.chat(req) for _ in range(50)]
    start = time.time()
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start
    qps = 50 / elapsed
    assert qps > 100  # 目標: 100+ QPS
```

**預估**: 1-2 天
**優先級**: ⭐⭐⭐⭐⭐

## 📈 預期性能提升

### 吞吐量（QPS）
- **當前**: ~20-30 QPS（單機，同步）
- **目標**: 100-150 QPS
- **提升**: 3-5x ✅

### 延遲（P95）
| 端點 | 當前 (ms) | 目標 (ms) | 改善 |
|------|-----------|-----------|------|
| /chat | 500-800 | 300-500 | 30-40% |
| /embed | 100-200 | 60-120 | 40% |
| /retrieve | 800-1500 | 500-900 | 35-40% |
| /graph/extract | 2000-5000 | 1200-3000 | 40% |

### 並發能力
- **當前**: 5-10 並發請求
- **目標**: 50+ 並發請求
- **提升**: 5-10x ✅

## ⚠️ 風險與注意事項

### 1. 向後兼容性
- **問題**: 現有同步測試會全部失敗
- **解決**:
  - 保留同步版本一段時間（`_sync` 後綴）
  - 漸進式遷移

### 2. 錯誤處理
- **問題**: 異步錯誤更難追蹤
- **解決**:
  - 使用 `asyncio.gather(..., return_exceptions=True)`
  - 詳細的異步日誌和追蹤

### 3. 連接池管理
- **問題**: 異步客戶端需要正確的生命週期管理
- **解決**:
  - 使用 FastAPI lifespan events
  - 正確關閉連接池

### 4. 測試複雜度
- **問題**: 異步測試需要特殊設置
- **解決**:
  - pytest-asyncio fixtures
  - mock async 函數

## 📋 檢查清單

### Phase 1: 準備
- [ ] 更新 `requirements.txt`
- [ ] 安裝新依賴
- [ ] 設置 pytest-asyncio

### Phase 2: 客戶端
- [ ] LiteLLM → AsyncOpenAI
- [ ] Qdrant → AsyncQdrantClient
- [ ] Neo4j → AsyncDriver
- [ ] Reranker → httpx.AsyncClient

### Phase 3: 服務層
- [ ] ChatService 異步化
- [ ] VectorService 異步化
- [ ] GraphService 異步化

### Phase 4: 路由層
- [ ] 更新所有路由為 async def
- [ ] 更新依賴注入

### Phase 5: 測試
- [ ] 更新單元測試
- [ ] 性能基準測試
- [ ] 端到端測試

## 🎯 成功標準

- ✅ 所有測試通過（覆蓋率 ≥ 80%）
- ✅ 吞吐量提升 ≥ 3x
- ✅ P95 延遲降低 ≥ 30%
- ✅ 並發請求處理 ≥ 50
- ✅ 零回歸 bug
- ✅ 文檔更新完成

## 📚 參考資料

- [FastAPI Async](https://fastapi.tiangolo.com/async/)
- [OpenAI Python SDK - Async](https://github.com/openai/openai-python#async-usage)
- [Qdrant Async Client](https://qdrant.tech/documentation/frameworks/python/)
- [Neo4j Async Driver](https://neo4j.com/docs/api/python-driver/current/async_api.html)
- [httpx Async](https://www.python-httpx.org/async/)

---

**建立日期**: 2025-10-19
**更新日期**: 2025-10-19
**負責人**: GitHub Copilot + 社群貢獻者
