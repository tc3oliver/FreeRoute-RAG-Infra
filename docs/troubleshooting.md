# FreeRoute RAG Infra - 故障排查指南

> **版本**: v0.1.2
> **最後更新**: 2025-10-18
> **語言**: [繁體中文](#) | [English](troubleshooting.en.md)

## 📑 目錄

- [常見問題快速索引](#常見問題快速索引)
- [部署相關問題](#部署相關問題)
- [服務連接問題](#服務連接問題)
- [API 錯誤處理](#api-錯誤處理)
- [性能問題](#性能問題)
- [資料問題](#資料問題)
- [日誌和除錯](#日誌和除錯)
- [進階除錯技巧](#進階除錯技巧)

---

## 常見問題快速索引

| 問題類型 | 症狀 | 章節 |
|---------|------|------|
| **部署失敗** | 容器無法啟動 | [部署相關問題](#部署相關問題) |
| **連接超時** | 服務間無法通訊 | [服務連接問題](#服務連接問題) |
| **401/403 錯誤** | API 認證失敗 | [API 錯誤處理](#api-錯誤處理) |
| **429 錯誤** | Token 用量超限 | [API 錯誤處理](#api-錯誤處理) |
| **響應緩慢** | 延遲過高 | [性能問題](#性能問題) |
| **檢索無結果** | 搜索返回空 | [資料問題](#資料問題) |
| **圖譜抽取失敗** | JSON 驗證錯誤 | [資料問題](#資料問題) |

---

## 部署相關問題

### 問題 1: `docker compose up` 失敗

**症狀**：
```bash
ERROR: The Compose file is invalid
```

**原因**：
- Docker Compose 版本過舊
- YAML 語法錯誤
- 環境變數未設定

**解決方案**：

1. **檢查 Docker Compose 版本**：
```bash
docker compose version
# 需要 v2.0.0 或更高版本
```

2. **驗證配置文件**：
```bash
docker compose config
```

3. **檢查 .env 文件**：
```bash
# 確保 .env 存在且包含必填變數
cp .env.example .env
nano .env  # 編輯必填項目
```

4. **必填環境變數**：
```bash
# .env 中必須設定
POSTGRES_PASSWORD=your_password
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
```

---

### 問題 2: 容器不斷重啟

**症狀**：
```bash
docker compose ps
# 顯示某些容器狀態為 Restarting
```

**除錯步驟**：

1. **查看容器日誌**：
```bash
docker compose logs -f <service_name>

# 常見問題服務
docker compose logs -f apigw
docker compose logs -f litellm
docker compose logs -f neo4j
```

2. **檢查健康檢查**：
```bash
docker inspect <container_name> | jq '.[0].State.Health'
```

3. **常見原因及解決**：

| 服務 | 原因 | 解決方案 |
|------|------|----------|
| **litellm** | PostgreSQL 未就緒 | 等待 30 秒後重試 |
| **apigw** | LiteLLM 未就緒 | 檢查 LiteLLM 日誌 |
| **neo4j** | 記憶體不足 | 調整 heap 大小 |
| **ollama** | GPU 驅動問題 | 檢查 NVIDIA 驅動 |

---

### 問題 3: GPU 無法使用

**症狀**：
```bash
# Ollama 或 Reranker 日誌顯示
WARNING: CUDA not available, using CPU
```

**檢查步驟**：

1. **確認 NVIDIA 驅動安裝**：
```bash
nvidia-smi
# 應該顯示 GPU 資訊
```

2. **確認 NVIDIA Container Toolkit 安裝**：
```bash
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

3. **檢查 Docker Compose 配置**：
```yaml
# docker-compose.yml
services:
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: ["gpu"]
```

4. **無 GPU 解決方案**：
```bash
# .env 中設定
DEVICE=cpu  # Reranker 使用 CPU
# 注意：性能會下降，但仍可運行
```

---

### 問題 4: 埠號衝突

**症狀**：
```bash
ERROR: for qdrant  Cannot start service qdrant:
Ports are not available: listen tcp 0.0.0.0:9333: bind: address already in use
```

**解決方案**：

1. **找出佔用埠號的進程**：
```bash
# Linux/Mac
lsof -i :9333
sudo netstat -tulpn | grep 9333

# Windows
netstat -ano | findstr :9333
```

2. **停止佔用埠號的服務**，或修改 docker-compose.yml：
```yaml
services:
  qdrant:
    ports:
      - "19333:6333"  # 改用其他外部埠號
```

3. **對應埠號列表**：
```bash
# 外部:內部
9333:6333   # Qdrant
9474:7474   # Neo4j HTTP
9687:7687   # Neo4j Bolt
9379:6379   # Redis
9400:4000   # LiteLLM
9143:11434  # Ollama
9080:8080   # Reranker
9800:8000   # Gateway
9900:8000   # Ingestor
```

---

## 服務連接問題

### 問題 5: Gateway 無法連接 LiteLLM

**症狀**：
```bash
# Gateway 日誌
ERROR: Connection refused to http://litellm:4000
```

**檢查步驟**：

1. **確認 LiteLLM 健康狀態**：
```bash
docker compose ps litellm
# 應該顯示 healthy

curl http://localhost:9400/health
# 應該返回 200
```

2. **檢查網絡連接**：
```bash
docker compose exec apigw ping litellm
docker compose exec apigw curl http://litellm:4000/health
```

3. **檢查環境變數**：
```bash
docker compose exec apigw env | grep LITELLM
# 應該顯示：
# LITELLM_BASE=http://litellm:4000/v1
# LITELLM_KEY=sk-admin
```

4. **重啟服務**：
```bash
docker compose restart apigw litellm
```

---

### 問題 6: Qdrant 連接失敗

**症狀**：
```bash
# Gateway 日誌
ERROR: Failed to connect to Qdrant at http://qdrant:6333
```

**解決方案**：

1. **確認 Qdrant 運行**：
```bash
docker compose ps qdrant
curl http://localhost:9333/collections
```

2. **檢查 Collection 存在**：
```bash
curl http://localhost:9333/collections/<collection_name>
```

3. **重新創建 Collection**（如果不存在）：
```bash
curl -X PUT http://localhost:9333/collections/test_collection \
  -H 'Content-Type: application/json' \
  -d '{
    "vectors": {
      "size": 1024,
      "distance": "Cosine"
    }
  }'
```

---

### 問題 7: Neo4j 連接超時

**症狀**：
```bash
# Gateway 日誌
neo4j.exceptions.ServiceUnavailable: Failed to establish connection
```

**檢查步驟**：

1. **確認 Neo4j 啟動完成**：
```bash
docker compose logs neo4j | tail -50
# 應該看到 "Started."
```

2. **測試 Bolt 連接**：
```bash
docker compose exec apigw python3 << 'EOF'
from neo4j import GraphDatabase
driver = GraphDatabase.driver(
    "bolt://neo4j:7687",
    auth=("neo4j", "neo4j123")
)
with driver.session() as session:
    result = session.run("RETURN 1 as num")
    print(result.single()["num"])
driver.close()
EOF
```

3. **檢查密碼**：
```bash
# .env 中的密碼必須一致
NEO4J_PASSWORD=neo4j123
```

4. **重置 Neo4j**（⚠️ 會刪除所有資料）：
```bash
docker compose down
docker volume rm free-rag_neo4j_data
docker compose up -d neo4j
```

---

## API 錯誤處理

### 問題 8: 401 Unauthorized

**症狀**：
```json
{
  "detail": "Invalid or missing API key"
}
```

**解決方案**：

1. **檢查 API Key 格式**：
```bash
# 正確格式
curl http://localhost:9800/chat \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"rag-answer","messages":[...]}'

# 或使用 Bearer Token
curl http://localhost:9800/chat \
  -H "Authorization: Bearer dev-key" \
  ...
```

2. **確認配置的 Key**：
```bash
# 檢查 Gateway 配置
docker compose exec apigw env | grep API_GATEWAY_KEYS
# 應該包含您使用的 Key
```

3. **更新 .env**：
```bash
# .env
API_GATEWAY_KEYS=dev-key,prod-key,another-key
GATEWAY_API_KEY=dev-key
```

---

### 問題 9: 429 Too Many Requests

**症狀**：
```json
{
  "detail": "Daily OpenAI token limit exceeded. Requests are being throttled or rerouted."
}
```

**原因**：
- 達到每日 OpenAI Token 用量上限（`OPENAI_TPD_LIMIT`）
- TokenCap 插件自動限流或 reroute

**解決方案**：

1. **檢查當前用量**：
```bash
docker compose exec redis redis-cli GET "tpd:openai:$(date +%Y-%m-%d)"
# 顯示今日已使用的 token 數
```

2. **提高限額**（臨時）：
```bash
# .env
OPENAI_TPD_LIMIT=20000000  # 提高到 20M

docker compose restart litellm
```

3. **啟用自動 Reroute**：
```bash
# .env
OPENAI_REROUTE_REAL=true  # 自動切換到 Gemini

docker compose restart litellm
```

4. **手動重置計數器**（⚠️ 謹慎使用）：
```bash
docker compose exec redis redis-cli DEL "tpd:openai:$(date +%Y-%m-%d)"
```

5. **查看 Reroute 日誌**：
```bash
docker compose logs litellm | grep -i reroute | tail -20
```

---

### 問題 10: 500 Internal Server Error

**症狀**：
```json
{
  "detail": "Internal server error"
}
```

**除錯步驟**：

1. **查看詳細錯誤**：
```bash
docker compose logs apigw | tail -100
```

2. **啟用 DEBUG 日誌**：
```bash
# .env
LOG_LEVEL=DEBUG

docker compose restart apigw
```

3. **常見原因**：

| 錯誤訊息 | 原因 | 解決方案 |
|---------|------|----------|
| `KeyError: 'OPENAI_API_KEY'` | 環境變數未設定 | 檢查 .env |
| `ConnectionError` | 服務未就緒 | 檢查依賴服務 |
| `ValidationError` | 請求格式錯誤 | 檢查 API 文檔 |
| `JSONDecodeError` | LLM 返回非 JSON | 檢查模型配置 |

---

## 性能問題

### 問題 11: API 響應緩慢

**症狀**：
- 請求延遲 > 5 秒
- P95 延遲過高

**診斷步驟**：

1. **檢查各服務延遲**：
```bash
# 測試 Gateway
time curl http://localhost:9800/health

# 測試 LiteLLM
time curl http://localhost:9400/health

# 測試 Qdrant
time curl http://localhost:9333/collections

# 測試 Neo4j
time curl http://localhost:9474/
```

2. **查看 Prometheus 指標**：
```bash
curl http://localhost:9800/metrics | grep duration
```

3. **檢查系統資源**：
```bash
# CPU 和記憶體使用
docker stats

# 磁碟 I/O
docker compose exec apigw df -h
```

**優化建議**：

1. **增加資源限制**：
```yaml
# docker-compose.yml
services:
  apigw:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
```

2. **啟用 GPU 加速**：
```bash
# 確保 Reranker 和 Ollama 使用 GPU
docker compose logs reranker | grep -i cuda
docker compose logs ollama | grep -i gpu
```

3. **減少批次大小**（如果記憶體不足）：
```bash
# 在 Gateway 調用時減少 top_k
{
  "query": "...",
  "top_k": 3  # 從 10 降到 3
}
```

---

### 問題 12: 記憶體不足 (OOM)

**症狀**：
```bash
# 容器日誌
137  # Exit code 137 = OOMKilled
```

**解決方案**：

1. **檢查記憶體使用**：
```bash
docker stats --no-stream
```

2. **增加容器記憶體限制**：
```yaml
# docker-compose.yml
services:
  neo4j:
    environment:
      NEO4J_server_memory_heap_max__size: 2G  # 降低到 2G
```

3. **減少並發請求**：
```bash
# 限制客戶端並發數
# 或在 Gateway 添加限流
```

4. **清理資料**：
```bash
# 清理舊的向量資料
curl -X DELETE http://localhost:9333/collections/<old_collection>

# 清理 Neo4j 資料
docker compose exec neo4j cypher-shell -u neo4j -p neo4j123 \
  "MATCH (n) DETACH DELETE n"
```

---

## 資料問題

### 問題 13: 向量搜索無結果

**症狀**：
```json
{
  "ok": true,
  "results": []
}
```

**檢查步驟**：

1. **確認資料已索引**：
```bash
curl http://localhost:9333/collections/<collection_name>
# 檢查 points_count 是否 > 0
```

2. **測試查詢**：
```bash
curl -X POST http://localhost:9333/collections/<collection_name>/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{"limit": 10}'
# 應該返回一些點
```

3. **檢查向量維度**：
```bash
# bge-m3 = 1024 維
# 確保 Collection 和嵌入模型一致
```

4. **重新索引**：
```bash
# 使用 Ingestor 重新索引
docker compose exec ingestor python cli.py --path /data
```

---

### 問題 14: 圖譜抽取失敗

**症狀**：
```json
{
  "ok": false,
  "error": "Graph extraction failed after 2 attempts"
}
```

**常見原因**：

1. **JSON Schema 驗證失敗**：
```bash
# 檢查 Schema
cat schemas/graph_schema.json | jq .

# 確認 LLM 輸出符合 Schema
docker compose logs apigw | grep "graph_extract"
```

2. **節點/邊數量不足**：
```bash
# .env 中調整閾值
GRAPH_MIN_NODES=1
GRAPH_MIN_EDGES=0  # 允許只有節點
GRAPH_ALLOW_EMPTY=true  # 允許空圖譜

docker compose restart apigw
```

3. **LLM 回答格式錯誤**：
```bash
# 查看原始 LLM 輸出
docker compose logs litellm | grep -A 20 "graph-extractor"
```

**解決方案**：

1. **啟用自動修復**：
```json
{
  "context": "...",
  "repair_if_invalid": true,  // 啟用
  "strict": false  // 降低嚴格度
}
```

2. **嘗試不同模型**：
```json
{
  "context": "...",
  "model": "graph-extractor-gemini"  // 改用 Gemini
}
```

3. **簡化輸入文字**：
```python
# 將長文切分成小段
chunks = split_text(long_text, chunk_size=500)
for chunk in chunks:
    extract_graph(chunk)
```

---

### 問題 15: Neo4j 查詢超時

**症狀**：
```json
{
  "error": "Query execution timed out"
}
```

**優化 Cypher 查詢**：

1. **添加索引**：
```cypher
// 在常用屬性上創建索引
CREATE INDEX FOR (n:Person) ON (n.name);
CREATE INDEX FOR (n:Company) ON (n.name);
```

2. **限制查詢範圍**：
```cypher
// ❌ 避免
MATCH (n)-[*]-(m) RETURN n, m

// ✅ 推薦
MATCH (n)-[*1..2]-(m) RETURN n, m LIMIT 100
```

3. **使用 EXPLAIN 分析**：
```cypher
EXPLAIN MATCH (n:Person)-[:WORKS_AT]->(c:Company)
WHERE n.name = 'Alice'
RETURN c.name
```

---

## 日誌和除錯

### 查看日誌

**實時查看所有服務日誌**：
```bash
docker compose logs -f
```

**查看特定服務**：
```bash
docker compose logs -f apigw
docker compose logs -f litellm
docker compose logs -f neo4j
```

**查看最近 N 行**：
```bash
docker compose logs --tail=100 apigw
```

**按時間篩選**：
```bash
docker compose logs --since 10m apigw  # 最近 10 分鐘
docker compose logs --since 2025-10-18T10:00:00 apigw
```

**搜索關鍵字**：
```bash
docker compose logs apigw | grep -i error
docker compose logs apigw | grep "request_id"
```

---

### 日誌級別控制

**設定日誌級別**：
```bash
# .env
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR, CRITICAL

docker compose restart apigw
```

**臨時啟用 DEBUG**：
```bash
docker compose exec apigw env LOG_LEVEL=DEBUG uvicorn ...
```

---

### 追蹤請求

**使用 Request ID 追蹤**：

1. **發送請求時指定**：
```bash
curl http://localhost:9800/chat \
  -H "X-Request-ID: my-unique-id-123" \
  -H "X-API-Key: dev-key" \
  ...
```

2. **查找相關日誌**：
```bash
docker compose logs apigw | grep "my-unique-id-123"
docker compose logs litellm | grep "my-unique-id-123"
```

---

## 進階除錯技巧

### 進入容器內部

```bash
# 進入 Gateway 容器
docker compose exec apigw bash

# 進入 LiteLLM 容器
docker compose exec litellm sh

# 進入 Neo4j 容器並使用 cypher-shell
docker compose exec neo4j cypher-shell -u neo4j -p neo4j123
```

### Python 除錯

**在容器內執行 Python**：
```bash
docker compose exec apigw python3
>>> from services.gateway.config import *
>>> print(LITELLM_BASE)
>>> print(QDRANT_URL)
```

**測試單個模組**：
```bash
docker compose exec apigw python3 -m pytest tests/unit/test_gateway_utils.py -v
```

### 網絡除錯

**測試服務間連接**：
```bash
# 從 Gateway ping LiteLLM
docker compose exec apigw ping litellm

# 測試 HTTP 連接
docker compose exec apigw curl http://litellm:4000/health

# 測試 Bolt 連接（Neo4j）
docker compose exec apigw nc -zv neo4j 7687
```

### 資料庫除錯

**直接訪問 Redis**：
```bash
docker compose exec redis redis-cli

# 查看所有 Key
KEYS *

# 查看 Token 統計
GET tpd:openai:2025-10-18

# 清空資料庫（⚠️ 謹慎使用）
FLUSHDB
```

**直接訪問 PostgreSQL**：
```bash
docker compose exec db psql -U llmproxy -d litellm

# 查看表
\dt

# 查看模型配置
SELECT * FROM litellm_config;
```

**直接訪問 Neo4j**：
```bash
docker compose exec neo4j cypher-shell -u neo4j -p neo4j123

# 查看所有節點類型
MATCH (n) RETURN DISTINCT labels(n);

# 查看節點數量
MATCH (n) RETURN count(n);

# 查看邊類型
MATCH ()-[r]->() RETURN DISTINCT type(r);
```

---

## 重置和清理

### 重置單個服務

```bash
# 重啟服務
docker compose restart apigw

# 重建服務
docker compose up -d --force-recreate --no-deps apigw

# 重建並更新映像
docker compose build --no-cache apigw
docker compose up -d apigw
```

### 完全重置（⚠️ 會刪除所有資料）

```bash
# 停止並刪除所有容器和卷
docker compose down -v

# 刪除映像（可選）
docker compose down --rmi all

# 重新部署
docker compose up -d --build
```

### 清理磁碟空間

```bash
# 清理未使用的映像
docker image prune -a

# 清理未使用的卷
docker volume prune

# 清理所有未使用資源
docker system prune -a --volumes
```

---

## 獲取幫助

如果以上方法都無法解決您的問題，請：

1. **查看文檔**：
   - [README](../README.zh-TW.md)
   - [API 使用指南](zh/api_usage.md)
   - [架構設計](architecture.md)

2. **搜索已知問題**：
   - [GitHub Issues](https://github.com/tc3oliver/FreeRoute-RAG-Infra/issues)

3. **提交新問題**：
   - [創建 Issue](https://github.com/tc3oliver/FreeRoute-RAG-Infra/issues/new)
   - 請提供：
     - 完整的錯誤訊息
     - `docker compose logs` 輸出
     - `.env` 配置（移除敏感資訊）
     - 復現步驟

4. **社群討論**：
   - [GitHub Discussions](https://github.com/tc3oliver/FreeRoute-RAG-Infra/discussions)

---

**作者**: tc3oliver
**版本**: v0.1.2
**最後更新**: 2025-10-18
