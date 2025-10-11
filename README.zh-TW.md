# FreeRoute RAG Infra

<div align="right">
  <sup>語言：</sup>
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a>

</div>

Zero-Cost RAG/GraphRAG Infrastructure — LangChain Compatible

<!-- 徽章 -->
[![CI](https://github.com/tc3oliver/FreeRoute-RAG-Infra/actions/workflows/ci.yml/badge.svg)](https://github.com/tc3oliver/FreeRoute-RAG-Infra/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)

## 專案簡介

FreeRoute RAG Infra 是一套可本機部署的 RAG/GraphRAG 基礎設施，目標是讓開發者在無付費門檻下，充分利用免費 API 與本地元件進行開發與測試（Free-first）。

重點能力：

- Free-first 路由：優先走免費或低成本供應商；當 OpenAI 達每日 Token 上限（TPD）或出錯時，自動改道至 Gemini / Groq / OpenRouter。本地 Embeddings 走 Ollama。
- 標準介面：LiteLLM 提供 OpenAI 相容端點（供 LangChain/SDK）；API Gateway 提供 /chat /embed /rerank /graph/extract。
- 本地能力：Ollama（bge-m3）向量嵌入、bge-reranker-v2-m3 重排序，可選 GPU。
- 可觀測與治理：TokenCap（每日 Token 限額與計數）、Redis、Dashboard UI。
- GraphRAG：抽取與 Schema 驗證/修復，結構可映射 Neo4j/GraphDB。

適用場景：個人/團隊 Dev/Test、私有 LLM API Proxy、課程/工作坊、RAG/GraphRAG PoC。

## 目錄

- [專案簡介](#專案簡介)
- [概觀](#概觀)
- [功能](#功能)
- [架構](#架構)
- [需求](#需求)
- [快速開始](#快速開始)
- [設定與環境變數](#設定與環境變數)
- [服務與埠號](#服務與埠號)
- [免費額度與來源](#免費額度與來源)
- [模型入口與路由](#模型入口與路由)
- [API](#api)
- [Graph Schema](#graph-schema)
- [Reranker 與 Embeddings](#reranker-與-embeddings)
- [測試](#測試)
- [疑難排解](#疑難排解)
- [專案結構](#專案結構)
- [授權](#授權)

## 概觀

FreeRoute RAG Infra 提供可直接部署的檢索增強生成（RAG）與 GraphRAG 執行環境，重點在於：

- LangChain/OpenAI API 相容；可作為私有 LLM API Proxy 使用。
- 多供應商容錯與改道（OpenAI 達 TPD/錯誤時自動切換至 Gemini/Groq/OpenRouter）。
- Gateway 層提供 JSON 模式、Graph 抽取流程、Schema 驗證與修復。
- TokenCap 控制每日 OpenAI Token，搭配 Redis 計數與 Dashboard 視覺化。

## 功能

- OpenAI 相容 API（LiteLLM Proxy）
- API Gateway：/chat、/embed、/rerank、/graph/extract
- 本地 Embeddings：Ollama bge-m3
- 本地 Reranker：BAAI/bge-reranker-v2-m3（支援 GPU）
- TokenCap：每日 Token 限額、跨供應商自動改道
- Dashboard UI：請求、錯誤、用量觀測

## 對象

- 想以最低成本驗證 RAG/GraphRAG 的個人與團隊
- 需要私有化、可觀測、LangChain 相容 API 的工程場景

## 架構

```mermaid
flowchart TB
  subgraph CLIENT["使用者應用層"]
    LC["LangChain / SDK"]
    FE["Web / API Client"]
  end

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

  subgraph LOCAL["本地服務"]
    OLLAMA[("Ollama<br/>bge-m3")]
    RERANK["bge-reranker-v2-m3"]
    REDIS["Redis"]
    PG["Postgres"]
  end

  subgraph PROVIDERS["雲端模型供應商"]
    OAI["OpenAI"]
    GGM["Gemini"]
    OPR["OpenRouter"]
    GRQ["Groq"]
  end

  LC --|OpenAI 相容 API|--> LITELLM
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

備註：LangChain 建議直連 LiteLLM（9400）。前端或應用層流程走 API Gateway（9800）。

## 需求

- Docker 24+（Compose v2）
- 可選 GPU：NVIDIA 驅動與 Container Toolkit（Linux 建議 CUDA 12.x）

## 快速開始

1) 建立 .env

```bash
# .env（示例）
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
GROQ_API_KEY=...
# 可選：API_GATEWAY_KEYS=dev-key,another-key
```

2) 啟動

```bash
docker compose up -d --build
```

3) 健康檢查

```bash
curl -s http://localhost:9400/health || curl -s http://localhost:9400/health/readiness | jq
curl -s http://localhost:9800/health | jq
```

4) Dashboard

-- URL: http://localhost:9400/ui
- 預設帳密：admin / admin123（請儘速修改）

首次啟動注意事項：

- Ollama 會自動拉取 bge-m3 模型；Reranker 會下載 BAAI/bge-reranker-v2-m3，首次啟動需數分鐘，之後會快很多。
- 對應緩存卷：`ollama_models`、`reranker_models`。

## 設定與環境變數

建議放在 .env，勿提交版本控制。

| 變數 | 範例 | 說明 |
| --- | --- | --- |
| LITELLM_MASTER_KEY | sk-admin | LiteLLM 統一 API 金鑰（供 LangChain/SDK） |
| OPENAI_API_KEY | sk-... | OpenAI 金鑰（受每日 Token 限制） |
| GOOGLE_API_KEY | AIza... | Gemini 金鑰 |
| OPENROUTER_API_KEY | sk-or-... | OpenRouter 金鑰 |
| GROQ_API_KEY | gsk_... | Groq 金鑰 |
| OPENAI_TPD_LIMIT | 10000000 | 每日 OpenAI Token 上限（例 10M） |
| OPENAI_REROUTE_REAL | true | 直接打真實 OpenAI 型號且超量時也會改道 |
| GRAPH_SCHEMA_PATH | /app/schemas/graph_schema.json | Graph Schema 路徑（TokenCap/Gateway 共用） |
| TZ | Asia/Taipei | 時區 |
| TZ_OFFSET_HOURS | 8 | Redis 計數時區偏移 |
| API_GATEWAY_KEYS | dev-key,another-key | Gateway 允許的 X-API-Key 清單 |

API Gateway 補充環境變數：

- LITELLM_BASE（預設 http://litellm:4000/v1）：Gateway 代理至 LiteLLM 的 Base URL
- LITELLM_KEY（預設 sk-admin）：Gateway 代理用的管理金鑰
- RERANKER_URL（預設 http://reranker:8080；若未設，程式預設 80）：重排服務 URL
- GRAPH_SCHEMA_PATH（預設 `/app/schemas/graph_schema.json`）：Gateway 與 TokenCap 共用（由 `./schemas/graph_schema.json` 掛載）
- GRAPH_MIN_NODES / GRAPH_MIN_EDGES（預設 1 / 1）：/graph/extract 最小門檻
- GRAPH_ALLOW_EMPTY（預設 false）：是否允許空結果通過
- GRAPH_MAX_ATTEMPTS（預設 2）：每個 provider 嘗試次數（strict → nudge）
- GRAPH_PROVIDER_CHAIN（預設 `graph-extractor,graph-extractor-o1mini,graph-extractor-gemini`）：provider 嘗試順序

費用保護：

- `litellm.config.yaml` 已設定 `general_settings.max_budget_per_day: 0.0`，避免產生費用。
- TokenCap 以 `OPENAI_TPD_LIMIT` 控制每日 OpenAI Token；compose 預設 9M（預留 1M 系統空間）。

## 服務與埠號

| 服務 | 埠 | 說明 |
| --- | ---: | --- |
| LiteLLM Proxy | 4000 | OpenAI 相容 API（給 LangChain/SDK） |
| Dashboard UI | 4000 | http://localhost:9400/ui |
| API Gateway | 8000 | /chat /embed /rerank /graph/extract |
| Reranker | 8080 | POST /rerank（bge-reranker-v2-m3） |
| Ollama | 11434 | bge-m3 embeddings |
| Redis | 6379 | Token 計數/快取 |
| Postgres | 5432 | 內部用途，預設不對外 |

## 免費額度與來源

供應商的免費政策與配額會變動，下列資訊僅作為導引，請以官方頁面為準。

- OpenAI（API）
  - 現況：無「分享資料換每日免費 API token」的官方方案。API 預設不使用你的資料訓練（可選擇是否提供資料以改善服務）。
  - 免費額度多來自新戶促銷或特定方案，是否提供視時點與地區而定。
  - 參考：
    - https://platform.openai.com/docs/billing/overview
    - https://platform.openai.com/docs/guides/rate-limits/usage-tiers

- Google Gemini
  - 在 AI Studio/Developers 提供免費或試用額度，不同模型與區域有差異。
  - 參考：
    - https://ai.google.dev/pricing

- Groq
  - 提供可免費使用的推理 API（如 Llama/Mixtral 變體），有速率與配額限制。
  - 參考：
    - https://groq.com/pricing

- OpenRouter
  - 聚合多家模型，部分標示為 free 的型號可免費使用，通常有佇列與速率限制。
  - 參考：
    - https://openrouter.ai/pricing
    - https://openrouter.ai/models?tag=free

- Ollama（本地）
  - 本地推理，不需雲端費用；性能取決於硬體。
  - 參考：
    - https://ollama.com/

備註：本專案預設優先走免費或低成本供應商。達到 OpenAI 每日 Token 上限（TPD）或發生錯誤時，會自動改道至 Gemini/Groq/OpenRouter；本地 Embeddings 走 Ollama。

## 模型入口與路由

已在 `litellm.config.yaml` 定義入口名，常用如下。

Chat / 推理：

| 入口名 | 後端 | 說明 |
| --- | --- | --- |
| rag-answer | OpenAI gpt-5-mini | 預設；達頂改道 |
| rag-answer-gemini | Gemini 2.5 Flash | 免費備援 |
| rag-answer-openrouter | Mistral Small 24B（free） | OpenRouter 備援 |
| rag-answer-groq | Groq Llama/Mixtral | 低延遲備援 |

Graph 抽取：

| 入口名 | 後端 | 備註 |
| --- | --- | --- |
| graph-extractor | OpenAI mini | 預設；TokenCap 注入 JSON Schema |
| graph-extractor-o1mini | OpenAI o1-mini | 備援 |
| graph-extractor-gemini | Gemini 2.5 Flash | 超量或失敗時優先改道 |

Embeddings / Rerank：

| 入口名 | 後端 | 備註 |
| --- | --- | --- |
| local-embed | Ollama bge-m3 | 本地免費 |
| reranker（Gateway） | bge-reranker-v2-m3 | 自架 API，GPU 最佳 |

路由策略（TokenCap）：

- 每日 OpenAI Token 計數 key：`tpd:openai:YYYY-MM-DD`
- 多跳改道：
  - graph-extractor → graph-extractor-gemini
  - rag-answer → rag-answer-gemini → rag-answer-openrouter → rag-answer-groq
- OPENAI_REROUTE_REAL=true：即使直接呼叫真實 OpenAI 型號也會改道

## API

LiteLLM（統一 API）

- Base URL：`http://localhost:4000/v1`
- Auth：`Authorization: Bearer <LITELLM_MASTER_KEY>`

範例（Python / LangChain）

```python
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

llm = ChatOpenAI(base_url="http://localhost:4000/v1", api_key="sk-admin", model="rag-answer", temperature=0.2)
emb = OpenAIEmbeddings(base_url="http://localhost:4000/v1", api_key="sk-admin", model="local-embed")

print(llm.invoke("用三行說明 RAG").content)
print(len(emb.embed_query("GraphRAG 與 RAG 差異")))
```

OpenAI 相容 REST

```bash
curl -s http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{"model":"rag-answer","messages":[{"role":"user","content":"列出三點 RAG 優點"}]}'
```

API Gateway（應用層）

- Base：`http://localhost:8000`
- Auth：`X-API-Key: <key>`（預設 dev-key，可透過 `API_GATEWAY_KEYS` 調整）

路由一覽：

| 方法 | 路徑 | 功能 |
| --- | --- | --- |
| GET | /health | 健康檢查 |
| GET | /whoami | 配置摘要（需金鑰） |
| POST | /chat | Chat / JSON 模式（自動補提示） |
| POST | /embed | 向量嵌入（local-embed） |
| POST | /rerank | 文本重排（bge-reranker-v2-m3） |
| POST | /graph/extract | Graph 抽取與 Schema 驗證 |

請求示例：

```bash
# /chat
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"請用 JSON 回答兩點優點"}],"json_mode":true,"temperature":0.2}' \
  http://localhost:8000/chat | jq

# /embed
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"texts":["RAG 是什麼？","GraphRAG 是什麼？"]}' \
  http://localhost:8000/embed | jq

# /rerank
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"query":"生成式 AI 是什麼？","documents":["AI 是人工智慧","生成式 AI 可產生內容"],"top_n":2}' \
  http://localhost:8000/rerank | jq

# /graph/probe（輕量探測，不驗 schema）
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"model":"graph-extractor","strict_json":true}' \
  http://localhost:8000/graph/probe | jq
```

## Graph Schema

- Repo 路徑：`schemas/graph_schema.json`
- 容器路徑：`/app/schemas/graph_schema.json`（由 docker-compose 掛載）
- 頂層結構：

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

備註：`props[].value` 支援 string/number/boolean/null。

Gateway 與 TokenCap 只讀此檔案，啟動時驗證 Schema（若無效則 fail-fast）。

Graph 抽取端點（建議走 Gateway）：

```bash
curl -s -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"context":"Alice 於 2022 年加入 Acme 擔任工程師；Acme 總部在台北，創辦人 Bob。"}' \
  http://localhost:9800/graph/extract | jq
```

常用參數：

- context（必填）
- min_nodes / min_edges（預設 1 / 1）
- allow_empty（預設 false）
- max_attempts（預設 2；每個 provider 嚴格一次、nudged 一次）
- provider_chain（選填，覆寫預設鏈）

## Reranker 與 Embeddings

Embeddings（Ollama bge-m3）

- LiteLLM 模型名：`local-embed`
- 在 LangChain 使用 `OpenAIEmbeddings` 指向 LiteLLM Base URL

Reranker（bge-reranker-v2-m3）

-- 直接端點：`POST http://localhost:9080/rerank`
-- 經由 Gateway：`POST http://localhost:9800/rerank`
- 回傳格式：`{"ok": true, "results": [{"index": 1, "score": 0.83, "text": "..."}]}`

## 測試

使用 pytest 執行整合測試（需先啟動 docker-compose）：

```bash
pytest -q tests/gateway
pytest -q tests/reranker
```

## 疑難排解

GPU / 平台差異：

- `... platform (linux/arm64/v8) does not match (linux/amd64) ...` → 固定 `platform: linux/amd64` 或改用相容映像。
- 無法偵測 GPU → 安裝 NVIDIA Container Toolkit；驗證：`docker run --gpus all nvidia/cuda:12.4.0-base nvidia-smi`。

環境變數未載入：

- 看到 `WARN The "OPENAI_API_KEY" variable is not set` → 檢查 `.env` 與 `docker compose config` 展開結果。

LiteLLM `/usage` 404：

- 新版未保證提供 `/usage`，改看 UI 或 Proxy 日誌。

JSON 模式錯誤：

- 直打 LiteLLM 請設定 `response_format={"type":"json_object"}` 並在提示中要求 JSON；Gateway `/chat` 設定 `json_mode=true` 會自動補 system 提示。

Graph 抽取空內容/非法 JSON：

- Gateway 會嘗試修正與正規化，仍失敗回 422 並附 provider 嘗試清單。確認 `schemas/graph_schema.json` 有效。

已達 TPD 仍走 OpenAI：

- 確認 `OPENAI_REROUTE_REAL=true`；檢查外掛日誌是否有 `reroute(hop ...)` 訊息。

## 專案結構

```
.
├─ services/
│  ├─ gateway/               # API Gateway（FastAPI）
│  │  ├─ app.py
│  │  └─ requirements.txt
│  └─ reranker/              # PyTorch Reranker（FastAPI）
│     └─ server.py
├─ integrations/
│  └─ litellm/
│     └─ plugins/
│        └─ token_cap.py     # TokenCap：TPD + 改道 + Schema 注入
├─ containers/
│  ├─ gateway/Dockerfile     # Gateway 容器
│  └─ litellm/Dockerfile     # LiteLLM 容器
├─ schemas/
│  └─ graph_schema.json      # Graph JSON Schema（掛載到 /app/schemas）
├─ configs/
│  └─ litellm.config.yaml    # 模型入口與路由策略
├─ tests/
│  ├─ gateway/test_gateway.py
│  └─ reranker/test_reranker.py
├─ docker-compose.yml        # 一鍵部署
├─ pyproject.toml
├─ README.md / README.zh-TW.md / ROADMAP.md
└─ ...
```

## 授權

- License：MIT
- 歡迎 PR 與建議改善。
