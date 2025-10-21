# FreeRoute RAG Infra - 系統架構設計

> **版本**: v0.1.2
> **最後更新**: 2025-10-18
> **語言**: [繁體中文](#) | [English](architecture.en.md)

## 📑 目錄

- [概述](#概述)
- [架構總覽](#架構總覽)
- [核心組件](#核心組件)
- [數據流程](#數據流程)
- [技術選型](#技術選型)
- [部署架構](#部署架構)
- [性能考量](#性能考量)
- [安全設計](#安全設計)
- [擴展性設計](#擴展性設計)

---

## 概述

FreeRoute RAG Infra 是一個生產就緒的 GraphRAG（Graph-based Retrieval-Augmented Generation）基礎設施，旨在提供：

- 🚀 **零成本運行**：優先使用免費 API 配額和本地推理
- 🔧 **即插即用**：Docker Compose 一鍵部署
- 🌍 **生產就緒**：完整的監控、日誌和錯誤處理
- 🔗 **框架中立**：OpenAI 相容 API，可與任何 LLM 框架整合

### 核心功能

- **混合檢索**：向量檢索（Qdrant）+ 知識圖譜（Neo4j）
- **智能路由**：多 LLM 供應商自動切換和回退
- **Token 控制**：每日用量上限和自動 fallback
- **本地推理**：Ollama 嵌入 + PyTorch Reranker

---

## 架構總覽

### 系統層次架構

```
┌─────────────────────────────────────────────────────────────────┐
│                         客戶端應用層                              │
│  (LangChain / LlamaIndex / Custom Apps / Streamlit / ...)       │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 │ HTTP/REST API
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Gateway (Port 9800)                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  • 路由層 (FastAPI)                                         │  │
│  │  • 認證 & 授權 (API Key)                                    │  │
│  │  • 請求追蹤 (X-Request-ID)                                  │  │
│  │  • 結構化日誌                                               │  │
│  │  • Prometheus 指標                                         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
    ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │  LLM Proxy 層    │ │   檢索服務層     │ │   圖譜服務層     │
    │   (LiteLLM)     │ │                 │ │                 │
    │  Port 9400      │ │                 │ │                 │
    └─────────────────┘ └─────────────────┘ └─────────────────┘
              │                  │                  │
      ┌───────┴───────┐         │         ┌────────┴────────┐
      ▼               ▼         ▼         ▼                 ▼
  ┌────────┐    ┌──────────┐ ┌──────┐ ┌─────────┐   ┌──────────┐
  │OpenAI  │    │ Gemini   │ │Qdrant│ │ Ollama  │   │  Neo4j   │
  │        │    │          │ │Vector│ │Embedding│   │  Graph   │
  │ (Cloud)│    │ (Cloud)  │ │  DB  │ │ (Local) │   │    DB    │
  └────────┘    └──────────┘ └──────┘ └─────────┘   └──────────┘
      │               │         │          │              │
      └───────────────┴─────────┴──────────┴──────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   Reranker       │
                    │   (PyTorch)      │
                    │   Port 9080      │
                    └──────────────────┘
                              │
                    ┌──────────────────┐
                    │   Redis          │
                    │   (快取 & 統計)   │
                    │   Port 9379      │
                    └──────────────────┘
                              │
                    ┌──────────────────┐
                    │   PostgreSQL     │
                    │   (LiteLLM 配置)  │
                    └──────────────────┘
```

### 組件通訊協議

| 來源 | 目標 | 協議 | 用途 |
|------|------|------|------|
| Client | Gateway | HTTP/REST | API 調用 |
| Gateway | LiteLLM | HTTP/REST | LLM 推理 |
| Gateway | Qdrant | HTTP/REST | 向量檢索 |
| Gateway | Neo4j | Bolt/HTTP | 圖譜查詢 |
| Gateway | Ollama | HTTP/REST | 本地嵌入 |
| Gateway | Reranker | HTTP/REST | 結果重排 |
| LiteLLM | Redis | Redis Protocol | Token 統計 |
| LiteLLM | PostgreSQL | PostgreSQL | 配置儲存 |

---

## 核心組件

### 1. API Gateway (services/gateway/)

**職責**：
- 對外統一入口，提供 RESTful API
- 路由請求到不同的服務層
- API Key 認證和授權
- 請求追蹤和日誌
- Prometheus 指標收集

**技術棧**：
- FastAPI (ASGI Web Framework)
- Pydantic (資料驗證)
- Python 3.10+

**關鍵模組**：
```
gateway/
├── app.py              # FastAPI 應用入口
├── config.py           # 配置管理
├── deps.py             # 依賴注入（認證）
├── middleware.py       # 中間件（追蹤、日誌、指標）
├── models.py           # Pydantic 模型
├── utils.py            # 工具函數
├── routers/            # API 路由
│   ├── chat.py         # /chat, /embed, /rerank
│   ├── vector.py       # /index/chunks, /search, /retrieve
│   ├── graph.py        # /graph/extract, /graph/query, ...
│   └── meta.py         # /health, /version, /metrics, /whoami
├── services/           # 業務邏輯層
│   ├── chat_service.py
│   ├── vector_service.py
│   └── graph_service.py
└── repositories/       # 資料訪問層
    ├── litellm_client.py
    ├── qdrant_client.py
    ├── neo4j_client.py
    └── reranker_client.py
```

**API 端點**：

| 端點 | 方法 | 功能 | 認證 |
|------|------|------|------|
| `/health` | GET | 健康檢查 | ❌ |
| `/version` | GET | 版本資訊 | ❌ |
| `/whoami` | GET | 配置資訊 | ✅ |
| `/metrics` | GET | Prometheus 指標 | ❌ |
| `/chat` | POST | 聊天完成 | ✅ |
| `/embed` | POST | 文字嵌入 | ✅ |
| `/rerank` | POST | 結果重排 | ✅ |
| `/index/chunks` | POST | 索引文字塊 | ✅ |
| `/search` | POST | 向量搜索 | ✅ |
| `/retrieve` | POST | 混合檢索 | ✅ |
| `/graph/probe` | POST | 測試供應商 JSON 能力 | ✅ |
| `/graph/extract` | POST | 抽取知識圖譜 | ✅ |
| `/graph/upsert` | POST | 插入/更新圖譜 | ✅ |
| `/graph/query` | POST | Cypher 查詢 | ✅ |

### 2. LiteLLM Proxy

**職責**：
- 統一多供應商 LLM API（OpenAI 相容）
- Token 用量追蹤和限制
- 自動 fallback 和重試
- 請求日誌和成本統計

**支援的供應商**：
- OpenAI (gpt-4o-mini, o1-mini)
- Google Gemini (gemini-1.5-flash-8b)
- OpenRouter (多種模型)
- Groq (llama, mixtral)
- Ollama (本地模型)

**TokenCap 插件**：
- 每日 OpenAI token 用量上限
- 自動切換到免費供應商（Gemini）
- JSON Schema 注入（圖譜抽取）
- 結構化日誌和事件追蹤

**配置文件**：`configs/litellm.config.yaml`

### 3. 向量資料庫 (Qdrant)

**職責**：
- 儲存文字嵌入向量
- 高效向量相似度搜索
- 元數據過濾

**特點**：
- 開源、免費、本地部署
- 支援多種距離度量（Cosine、Euclidean、Dot Product）
- Collection 隔離（多租戶支持）
- RESTful API

**資料結構**：
```json
{
  "id": "doc_id_chunk_1",
  "vector": [0.1, 0.2, ...],  // 1024-dim (bge-m3)
  "payload": {
    "text": "原始文字內容",
    "doc_id": "document_identifier",
    "metadata": {
      "source": "file.md",
      "chunk_id": "chunk_1",
      "timestamp": "2025-10-18T10:00:00Z"
    }
  }
}
```

### 4. 知識圖譜 (Neo4j)

**職責**：
- 儲存實體和關係
- 圖譜查詢和遍歷
- 知識推理

**資料模型**：
- **節點 (Node)**：實體，帶類型和屬性
- **邊 (Edge/Relationship)**：關係，帶類型和屬性

**Schema 設計** (`schemas/graph_schema.json`)：
```json
{
  "type": "object",
  "properties": {
    "nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "type": {"type": "string"},
          "props": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "key": {"type": "string"},
                "value": {"type": ["string", "number", "boolean"]}
              }
            }
          }
        }
      }
    },
    "edges": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "src": {"type": "string"},
          "dst": {"type": "string"},
          "type": {"type": "string"},
          "props": {"type": "array"}
        }
      }
    }
  }
}
```

**圖譜抽取流程**：
1. LLM 讀取文字，按 JSON Schema 抽取實體和關係
2. 驗證 JSON 格式和內容
3. 如失敗且 `repair_if_invalid=true`，嘗試修復
4. 如仍失敗，嘗試下一個供應商（fallback chain）
5. 成功後 upsert 到 Neo4j

### 5. 本地嵌入 (Ollama + bge-m3)

**職責**：
- 本地生成文字嵌入向量
- 支援中英文多語言
- 1024 維向量

**模型**：`bge-m3`（BAAI/bge-m3）
- 參數量：~560M
- 最大長度：8192 tokens
- 語言：中文、英文、多語言

**API**：
```bash
POST http://localhost:9143/api/embeddings
{
  "model": "bge-m3",
  "prompt": "文字內容"
}
```

### 6. 重排序服務 (Reranker)

**職責**：
- 重新排序檢索結果
- 提升相關性精確度

**模型**：`BAAI/bge-reranker-v2-m3`
- 交叉編碼器架構（Cross-Encoder）
- 輸入：Query + Document
- 輸出：相關性分數 (0-1)

**GPU 加速**：
- CUDA 12.x
- bfloat16 精度
- 批次處理

**API**：
```bash
POST http://localhost:9080/rerank
{
  "query": "查詢文字",
  "documents": ["文檔1", "文檔2", ...],
  "top_n": 3
}
```

### 7. Ingestor 文件處理服務

**職責**：
- 掃描和讀取文件
- 文字切分（Chunking）
- 批次索引到 Qdrant
- 批次圖譜抽取

**支援格式**：
- Markdown (.md)
- 純文字 (.txt)
- JSON (.json)
- 未來：PDF, DOCX, HTML

**切分策略**：
```python
def _simple_chunk_text(text: str, chunk_size: int, overlap: int):
    """簡單的滑動窗口切分"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks
```

---

## 數據流程

### 1. 文件攝取流程

```
┌─────────┐
│ 使用者  │
│上傳文件 │
└────┬────┘
     │
     ▼
┌─────────────────────────────────────┐
│  Ingestor CLI                       │
│  python cli.py --path /data         │
└─────────────────────────────────────┘
     │
     ├─► 1. 掃描文件 (*.md, *.txt)
     │
     ├─► 2. 讀取內容
     │
     ├─► 3. 文字切分
     │      ├─ chunk_size: 1000
     │      └─ overlap: 200
     │
     ├─► 4. 批次嵌入
     │      └─► POST /embed (Ollama + bge-m3)
     │
     ├─► 5. 索引到 Qdrant
     │      └─► POST /index/chunks
     │
     └─► 6. 圖譜抽取（可選）
            └─► POST /graph/extract
                 └─► 儲存到 Neo4j
```

### 2. 混合檢索流程

```
┌─────────┐
│ 使用者  │
│查詢請求 │
└────┬────┘
     │
     ▼
┌─────────────────────────────────────┐
│  Gateway: POST /retrieve            │
│  {                                  │
│    "query": "什麼是 LiteLLM?",       │
│    "top_k": 5,                      │
│    "use_graph": true                │
│  }                                  │
└─────────────────────────────────────┘
     │
     ├─► 1. 生成 Query 嵌入
     │      └─► POST /embed
     │
     ├─► 2. 向量搜索
     │      └─► Qdrant 相似度搜索
     │           └─► 返回 Top-K 結果
     │
     ├─► 3. 圖譜查詢（如果 use_graph=true）
     │      ├─ 提取 Query 實體
     │      └─► Neo4j Cypher 查詢
     │           └─► 返回相關節點和關係
     │
     ├─► 4. 結果合併
     │      └─ 向量結果 + 圖譜結果
     │
     ├─► 5. 重排序（可選）
     │      └─► POST /rerank
     │           └─► 返回重排後的 Top-N
     │
     └─► 6. 返回最終結果
```

### 3. 聊天補全流程

```
┌─────────┐
│ 使用者  │
│聊天請求 │
└────┬────┘
     │
     ▼
┌─────────────────────────────────────┐
│  Gateway: POST /chat                │
│  {                                  │
│    "model": "rag-answer",           │
│    "messages": [...]                │
│  }                                  │
└─────────────────────────────────────┘
     │
     ├─► 1. 認證檢查
     │      └─ X-API-Key 驗證
     │
     ├─► 2. 檢索相關上下文（RAG）
     │      ├─► POST /retrieve
     │      └─► 返回相關文檔
     │
     ├─► 3. 構建增強提示詞
     │      └─ System + Context + User Query
     │
     ├─► 4. LLM 推理
     │      └─► LiteLLM Proxy
     │           ├─ 檢查 Token Cap
     │           ├─ 選擇供應商
     │           │   ├─ OpenAI (gpt-4o-mini)
     │           │   └─ Fallback → Gemini
     │           └─► 返回回答
     │
     └─► 5. 返回結果
```

### 4. 知識圖譜抽取流程

```
┌─────────┐
│ 使用者   │
│抽取請求  │
└────┬────┘
     │
     ▼
┌──────────────────────────────────────┐
│  Gateway: POST /graph/extract        │
│  {                                   │
│    "context": "Nick 於 2022 加入...", │
│    "strict": true,                   │
│    "repair_if_invalid": true         │
│  }                                   │
└──────────────────────────────────────┘
     │
     ├─► 1. 載入 JSON Schema
     │      └─ schemas/graph_schema.json
     │
     ├─► 2. 構建抽取提示詞
     │      ├─ Schema 注入
     │      └─ Few-shot Examples
     │
     ├─► 3. LLM 抽取（重試鏈）
     │      └─► LiteLLM Proxy
     │           ├─ 嘗試 graph-extractor (GPT-4o-mini)
     │           ├─ JSON Mode 輸出
     │           └─ 返回 JSON
     │
     ├─► 4. 驗證 JSON
     │      ├─ Schema 驗證
     │      └─ 質量檢查（min_nodes, min_edges）
     │
     ├─► 5. 失敗？
     │      ├─ Yes → 修復嘗試（如 repair_if_invalid=true）
     │      │         └─► 重新發送給 LLM 修復
     │      │
     │      └─ 仍失敗？
     │             └─ 嘗試下一個供應商
     │                  ├─ graph-extractor-o1mini
     │                  └─ graph-extractor-gemini
     │
     ├─► 6. 成功
     │      └─► POST /graph/upsert
     │           └─ 儲存到 Neo4j
     │
     └─► 7. 返回結果
```

---

## 技術選型

### 為什麼選擇這些技術？

| 組件 | 技術 | 原因 |
|------|------|------|
| **Web 框架** | FastAPI | • 高性能 ASGI<br>• 自動 API 文檔<br>• 類型檢查<br>• 異步支持 |
| **LLM Proxy** | LiteLLM | • 多供應商統一 API<br>• 內建 fallback<br>• Token 追蹤<br>• 開源免費 |
| **向量資料庫** | Qdrant | • 開源免費<br>• 本地部署<br>• 高性能<br>• RESTful API |
| **圖資料庫** | Neo4j | • 成熟穩定<br>• Cypher 查詢語言<br>• 社群版免費<br>• APOC 擴展 |
| **嵌入模型** | bge-m3 | • 中英文優秀<br>• 開源免費<br>• 1024 維<br>• 可本地運行 |
| **Reranker** | bge-reranker-v2-m3 | • 高精度<br>• 開源免費<br>• GPU 加速<br>• 多語言支持 |
| **容器化** | Docker Compose | • 一鍵部署<br>• 環境隔離<br>• 易於擴展<br>• 生產就緒 |
| **日誌** | Python logging | • 標準庫<br>• 結構化日誌<br>• 可擴展<br>• ELK/Loki 相容 |
| **指標** | Prometheus | • 業界標準<br>• 時序資料<br>• Grafana 整合<br>• 查詢語言強大 |

### 成本優化策略

1. **本地推理優先**：
   - Ollama 嵌入（免費）
   - PyTorch Reranker（免費）

2. **免費 API 配額**：
   - Gemini Flash 8B（大配額）
   - Groq（快速免費推理）

3. **Token Cap**：
   - 每日 OpenAI 用量上限
   - 自動切換到免費供應商

4. **快取策略**：
   - Redis 快取嵌入向量
   - LLM 回答快取（未來）

---

## 部署架構

### 單機部署 (v0.1.x)

```
┌────────────────────────────────────────────────────────┐
│                  Docker Host                           │
│                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │  Gateway │  │ LiteLLM  │  │ Ingestor │              │
│  │  :9800   │  │  :9400   │  │  :9900   │              │
│  └──────────┘  └──────────┘  └──────────┘              │
│       │             │              │                   │
│  ┌────┴─────────────┴──────────────┴───┐               │
│  │                                      │              │
│  ▼              ▼              ▼        ▼              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐    │
│  │  Qdrant  │  │  Neo4j   │  │  Redis   │  │ PG   │    │
│  │  :9333   │  │  :9474   │  │  :9379   │  │ :5432│    │
│  └──────────┘  └──────────┘  └──────────┘  └──────┘    │
│                                                        │
│  ┌──────────┐  ┌──────────┐                            │
│  │  Ollama  │  │ Reranker │                            │
│  │  :9143   │  │  :9080   │                            │
│  └──────────┘  └──────────┘                            │
│       │             │                                  │
│  ┌────┴─────────────┴───┐                              │
│  │      GPU (Optional)  │                              │
│  └──────────────────────┘                              │
└────────────────────────────────────────────────────────┘
```

**系統需求**：
- **CPU**: 4 核心以上
- **記憶體**: 16GB 以上（32GB 建議）
- **磁碟**: 50GB 以上 SSD
- **GPU**: NVIDIA GPU（選填，用於 Reranker 和 Ollama 加速）

### 分散式部署 (v0.4.0 計劃)

```
┌─────────────────────────────────────────────────────────────┐
│                       Load Balancer                         │
│                    (Nginx / HAProxy)                        │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ Gateway  │    │ Gateway  │    │ Gateway  │
  │ Instance │    │ Instance │    │ Instance │
  │    #1    │    │    #2    │    │    #3    │
  └──────────┘    └──────────┘    └──────────┘
        │               │               │
        └───────────────┼───────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │  Qdrant  │    │  Neo4j   │    │ LiteLLM  │
  │ Cluster  │    │ Cluster  │    │ Cluster  │
  └──────────┘    └──────────┘    └──────────┘
        │               │               │
        └───────────────┼───────────────┘
                        │
                        ▼
                  ┌──────────┐
                  │  Redis   │
                  │ Cluster  │
                  └──────────┘
```

---

## 性能考量

### 當前性能（v0.1.x）

| 操作 | 延遲 (P95) | 吞吐量 | 備註 |
|------|-----------|--------|------|
| **向量搜索** | ~200ms | ~10 QPS | 單機 Qdrant |
| **圖譜查詢** | ~150ms | ~15 QPS | 簡單 Cypher |
| **嵌入生成** | ~500ms/batch | ~20 QPS | bge-m3, batch=10 |
| **重排序** | ~300ms/batch | ~5 QPS | GPU 加速 |
| **圖譜抽取** | ~5s | ~2 QPS | 含 LLM 推理 |

### 性能瓶頸

1. **同步 I/O**：目前大部分操作是同步的
2. **單線程處理**：未充分利用多核 CPU
3. **網絡往返**：多次服務間調用
4. **LLM 延遲**：雲端 API 延遲高

### v0.2.0 優化計劃

- **異步化**：所有 I/O 操作改為 async/await
- **批次處理**：嵌入、重排序批次化
- **連接池**：資料庫連接池優化
- **快取層**：Redis 快取熱門查詢

**目標**：
- 吞吐量提升 3-5x
- P95 延遲降低 30-40%

---

## 安全設計

### 認證與授權

**API Key 認證**：
```python
# 在 HTTP Header 中傳遞
X-API-Key: dev-key

# 或使用 Bearer Token
Authorization: Bearer dev-key
```

**多 Key 支持**（v0.4.0）：
```bash
# .env 中配置多個 Key
API_GATEWAY_KEYS=prod-key-1,prod-key-2,dev-key
```

### 資料安全

1. **傳輸加密**：
   - 生產環境使用 HTTPS/TLS
   - 內部通訊可使用 Docker 網絡隔離

2. **儲存加密**：
   - 敏感資料（API Keys）使用環境變數
   - 資料庫密碼加密儲存

3. **日誌脫敏**：
   - API Keys 不記錄在日誌中
   - 敏感資料自動遮罩

### 輸入驗證

```python
# Pydantic 模型自動驗證
class ChatReq(BaseModel):
    model: str = Field(..., min_length=1, max_length=100)
    messages: List[Message] = Field(..., min_items=1, max_items=100)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
```

### 注入攻擊防護

- **Cypher 注入**：使用參數化查詢
- **SQL 注入**：ORM 和參數化查詢
- **Prompt 注入**：輸入長度和字符限制

---

## 擴展性設計

### 水平擴展

**無狀態設計**：
- Gateway 服務無狀態，可任意擴展
- 狀態儲存在外部服務（Redis、PostgreSQL）

**負載均衡**：
```nginx
upstream gateway {
    server gateway-1:8000;
    server gateway-2:8000;
    server gateway-3:8000;
}
```

### 垂直擴展

**資源配置**：
```yaml
# docker-compose.yml
services:
  apigw:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

### 資料庫擴展

**Qdrant 分片**：
```python
# 按租戶分 Collection
collection_name = f"tenant_{tenant_id}"
```

**Neo4j 分片**（未來）：
- 按業務領域分庫
- Federation 查詢

---

## 相關文檔

- [API 使用指南](zh/api_usage.md)
- [故障排查指南](troubleshooting.md)
- [產品路線圖](../ROADMAP.md)
- [貢獻指南](../CONTRIBUTING.md)

---

**作者**: tc3oliver
**版本**: v0.1.2
**最後更新**: 2025-10-18
