# FreeRoute RAG Infra - curl 測試指南

本文件提供各種 API 端點的 curl 測試命令，用於驗證系統功能。

## 前置設定

### 服務端點
- **LiteLLM Proxy**: http://localhost:9400 (認證: Bearer sk-admin)
- **API Gateway**: http://localhost:9800 (認證: X-API-Key: dev-key)
- **Ingestor**: http://localhost:9900
- **Reranker**: http://localhost:9080

### 認證說明
- LiteLLM 直連: 使用 `Authorization: Bearer sk-admin`
- API Gateway: 使用 `X-API-Key: dev-key`

---

## API 比較與建議

### /v1/responses vs /v1/chat/completions

| 特性 | /v1/responses (推薦) | /v1/chat/completions (傳統) |
|------|---------------------|----------------------------|
| **功能完整性** | ✅ 統一式多模態 | ⚠️ 僅文字聊天 |
| **Reasoning 支援** | ✅ 完整支援 | ⚠️ 部分支援 |
| **工具呼叫** | ✅ 並行工具呼叫 | ✅ 基本工具呼叫 |
| **串流輸出** | ✅ 更好的串流格式 | ✅ 基本串流 |
| **結構化輸出** | ✅ 原生支援 | ⚠️ 需要特殊參數 |
| **多模態輸入** | ✅ 支援影像/音訊 | ❌ 不支援 |
| **未來相容性** | ✅ OpenAI 主要推薦 | ⚠️ 維護模式 |

**使用建議**：
- **新專案**：優先使用 `/v1/responses`
- **現有專案**：可繼續使用 `/v1/chat/completions`，考慮逐步遷移
- **複雜應用**：必須使用 `/v1/responses` (工具呼叫、reasoning、多模態)

---

## 1. 統一式多模態生成 API - /v1/responses (推薦)

`/v1/responses` 是 OpenAI 的統一式多模態生成 API，可在單一端點處理文字、程式碼、影像、音訊、工具呼叫與文件引用等多種任務。

### 1.1 基本文字生成

#### 簡單對話
```bash
curl -s http://localhost:9400/v1/responses \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer",
    "input": "請用繁體中文說明什麼是 RAG？",
    "max_output_tokens": 300
  }' | jq '.output[-1].content[0].text'
```

#### 進階分析 (rag-answer-pro)
```bash
curl -s http://localhost:9400/v1/responses \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer-pro",
    "input": "詳細分析 GraphRAG 與傳統 RAG 的技術差異和應用場景",
    "max_output_tokens": 800,
    "temperature": 0.5
  }' | jq '.output[-1].content[0].text'
```

### 1.2 推理模型支援

 Responses API 完整支援 reasoning 模型，會自動顯示推理過程：
```bash
curl -s http://localhost:9400/v1/responses \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer",
    "input": "分析複雜的演算法問題：如何優化大規模 RAG 系統的檢索效率？",
    "reasoning": {
      "effort": "high"
    },
    "max_output_tokens": 1000
  }' | jq '{reasoning_output: .output[0], final_answer: .output[-1].content[0].text}'
```

### 1.3 結構化輸出

#### JSON 格式輸出
```bash
curl -s http://localhost:9400/v1/responses \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer",
    "input": "請分析 RAG 系統的優缺點，並以 JSON 格式回應，包含 advantages 和 disadvantages 兩個陣列",
    "max_output_tokens": 400,
    "temperature": 0.3
  }' | jq '.output[-1].content[0].text'
```

### 1.4 工具呼叫 (Function Calling)

#### 定義工具並呼叫
```bash
curl -s http://localhost:9400/v1/responses \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer",
    "input": "請幫我查詢今天的天氣並建議適合的活動",
    "tools": [
      {
        "type": "function",
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "City name"
            },
            "unit": {
              "type": "string",
              "enum": ["celsius", "fahrenheit"],
              "description": "Temperature unit"
            }
          },
          "required": ["location"]
        }
      },
      {
        "type": "function",
        "name": "suggest_activity",
        "description": "Suggest activities based on weather",
        "parameters": {
          "type": "object",
          "properties": {
            "weather_condition": {
              "type": "string",
              "description": "Weather condition (sunny, rainy, cloudy, etc.)"
            },
            "temperature": {
              "type": "number",
              "description": "Temperature in degrees"
            }
          },
          "required": ["weather_condition"]
        }
      }
    ],
    "tool_choice": "auto"
  }' | jq '.output[] | {type: .type, tool_calls: .tool_calls}'
```

### 1.5 串流輸出

#### 即時回應串流
```bash
curl -s http://localhost:9400/v1/responses \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer",
    "input": "請詳細解釋量子運算的基本原理",
    "stream": true
  }'
```

### 1.6 多輪對話

#### 帶有上下文的對話
```bash
curl -s http://localhost:9400/v1/responses \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer",
    "input": [
      {"role": "system", "content": "你是一個專門研究 RAG 系統的專家"},
      {"role": "user", "content": "什麼是向量資料庫？"},
      {"role": "assistant", "content": "向量資料庫是專門設計用來儲存和檢索高維向量資料的資料庫系統。"},
      {"role": "user", "content": "那 Qdrant 和 Pinecone 有什麼不同？"}
    ],
    "max_output_tokens": 400
  }' | jq '.output[-1].content[0].text'
```

### 1.7 不同模型測試

#### 使用免費模型 (Gemini)
```bash
curl -s http://localhost:9400/v1/responses \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer-gemini",
    "input": "解釋什麼是機器學習中的過擬合問題，以及如何避免",
    "max_output_tokens": 300
  }' | jq '.output[-1].content[0].text'
```

#### 使用低延遲模型 (Groq)
```bash
curl -s http://localhost:9400/v1/responses \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer-groq",
    "input": "快速回答：Python 中 list 和 tuple 的主要差異",
    "max_output_tokens": 200
  }' | jq '.output[-1].content[0].text'
```

### 1.8 進階功能

#### 設定 Reasoning 努力程度
```bash
curl -s http://localhost:9400/v1/responses \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer-pro",
    "input": "分析一個複雜的商業案例：一家傳統製造公司如何数字化转型",
    "reasoning": {
      "effort": "high"
    },
    "max_output_tokens": 1500
  }' | jq '.usage'
```

#### 並行工具呼叫
```bash
curl -s http://localhost:9400/v1/responses \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer",
    "input": "請同時查詢台北的天氣、股價指數和新聞頭條",
    "tools": [
      {
        "type": "function",
        "name": "get_weather",
        "description": "Get weather information"
      },
      {
        "type": "function",
        "name": "get_stock_price",
        "description": "Get stock market index"
      },
      {
        "type": "function",
        "name": "get_news",
        "description": "Get news headlines"
      }
    ],
    "parallel_tool_calls": true
  }' | jq '.output[] | select(.tool_calls) | .tool_calls'
```

---

## 2. 傳統模型測試 (LiteLLM Proxy - /v1/chat/completions)

### 2.1 主要聊天模型

#### rag-answer (gpt-5-mini) - 經濟實用
```bash
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer",
    "messages": [
      {"role": "user", "content": "請用繁體中文簡要說明什麼是 RAG？"}
    ],
    "temperature": 0.7
  }' | jq '.choices[0].message.content'
```

#### rag-answer-pro (gpt-5) - 進階分析
```bash
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer-pro",
    "messages": [
      {"role": "user", "content": "請詳細比較 GraphRAG 與傳統 RAG 的優缺點"}
    ],
    "temperature": 0.5
  }' | jq '.choices[0].message.content'
```

### 2.2 備用/免費模型

#### Google Gemini (免費)
```bash
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer-gemini",
    "messages": [
      {"role": "user", "content": "解釋機器學習中的過擬合問題"}
    ]
  }' | jq '.choices[0].message.content'
```

#### OpenRouter (社群免費)
```bash
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer-openrouter",
    "messages": [
      {"role": "user", "content": "什麼是向量資料庫？"}
    ]
  }' | jq '.choices[0].message.content'
```

#### Groq (低延遲)
```bash
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer-groq",
    "messages": [
      {"role": "user", "content": "快速回答：Python 和 JavaScript 的主要差異"}
    ]
  }' | jq '.choices[0].message.content'
```

### 2.3 圖譜抽取模型

#### 主要圖譜抽取 (OpenAI)
```bash
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "graph-extractor",
    "messages": [
      {"role": "user", "content": "從以下文字抽取實體和關係：Alice 於 2022 年加入台北的 Acme 公司擔任軟體工程師，她的主管是 Bob。"}
    ],
    "temperature": 0.0
  }' | jq '.choices[0].message.content'
```

#### 圖譜抽取 (Gemini)
```bash
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "graph-extractor-gemini",
    "messages": [
      {"role": "user", "content": "抽取：台積電在竹科設立總部，由黃仁芳創建，主要生產半導體晶片。"}
    ]
  }' | jq '.choices[0].message.content'
```

### 2.4 嵌入模型

#### 本地嵌入 (Ollama bge-m3)
```bash
curl -s http://localhost:9400/v1/embeddings \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local-embed",
    "input": ["什麼是人工智慧？", "機器學習是 AI 的子集"]
  }' | jq '.data[0].embedding | length'
```

---

## 3. API Gateway 測試

### 3.1 OpenAI 相容端點 (推薦對外使用)

#### 聊天完成
```bash
curl -s http://localhost:9800/v1/chat/completions \
  -H "Authorization: Bearer dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rag-answer",
    "messages": [
      {"role": "system", "content": "你是一個專業的 AI 助手"},
      {"role": "user", "content": "解釋什麼是向量搜尋"}
    ]
  }' | jq '.choices[0].message.content'
```

#### 嵌入向量
```bash
curl -s http://localhost:9800/v1/embeddings \
  -H "Authorization: Bearer dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local-embed",
    "input": "RAG 系統包含檢索和生成兩個階段"
  }' | jq '.data[0].embedding | length'
```

### 3.2 Gateway 特有端點

#### 聊天端點 (JSON 模式)
```bash
curl -s http://localhost:9800/chat \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "請用 JSON 格式回應 RAG 的三個主要元件"}
    ],
    "json_mode": true,
    "temperature": 0.2
  }' | jq '.choices[0].message.content'
```

#### 搜尋端點
```bash
curl -s http://localhost:9800/search \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Python 程式設計",
    "top_k": 3,
    "collection": "knowledge_base"
  }' | jq '.results'
```

#### 混合檢索
```bash
curl -s http://localhost:9800/retrieve \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "誰在 Acme 公司工作？他們的專長是什麼？",
    "top_k": 5,
    "include_subgraph": true,
    "max_hops": 2
  }' | jq '.context'
```

#### 重排序
```bash
curl -s http://localhost:9800/rerank \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "什麼是生成式 AI？",
    "documents": [
      "AI 是人工智慧的縮寫",
      "生成式 AI 可以創建新的內容，如文字、圖片和音樂",
      "機器學習是 AI 的一個分支"
    ],
    "top_n": 2
  }' | jq '.results'
```

---

## 3. 圖譜操作 (API Gateway)

### 4.1 圖譜查詢
```bash
# 查詢節點數量
curl -s http://localhost:9800/graph/query \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (n) RETURN count(n) as total_nodes"
  }' | jq '.data'

# 查詢人員和公司關係
curl -s http://localhost:9800/graph/query \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (p:Person)-[r]-(c:Company) RETURN p.id, type(r), c.id LIMIT 10"
  }' | jq '.data'
```

### 4.2 圖譜抽取
```bash
curl -s http://localhost:9800/graph/extract \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "context": "張三是 Google 的軟體工程師，專長是機器學習，他與李四一起開發了一個 AI 專案。",
    "model": "graph-extractor"
  }' | jq '.data'
```

### 4.3 圖譜資料插入
```bash
curl -s http://localhost:9800/graph/upsert \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "nodes": [
        {
          "id": "王五",
          "type": "Person",
          "props": [
            {"key": "role", "value": "Data Scientist"},
            {"key": "company", "value": "TechCorp"}
          ]
        }
      ],
      "edges": [
        {
          "src": "王五",
          "dst": "TechCorp",
          "type": "WORKS_AT",
          "props": []
        }
      ]
    }
  }' | jq '.success'
```

---

## 4. 文件攝取 (Ingestor)

### 5.1 批量攝取目錄
```bash
# 創建測試資料
mkdir -p ./test_data
echo "台積電是全球最大的半導體代工廠，總部位於新竹科學園區。" > ./test_data/tsmc.md
echo "聯發科專注於晶片設計，在智慧型手機處理器市場佔有重要地位。" > ./test_data/mediatek.md

# 攝取文件
curl -s http://localhost:9900/ingest/directory \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/test_data",
    "collection": "tech_companies",
    "file_patterns": ["*.md", "*.txt"],
    "chunk_size": 800,
    "extract_graph": true,
    "force_reprocess": true
  }' | jq '.status'
```

### 5.2 攝取單一文檔
```bash
curl -s http://localhost:9900/ingest/file \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/test_data/tsmc.md",
    "collection": "tech_companies",
    "extract_graph": true
  }' | jq '.chunks_processed'
```

---

## 5. 健康檢查與狀態

### 6.1 服務健康檢查
```bash
# LiteLLM Proxy 健康檢查
curl -s http://localhost:9400/health | jq

# API Gateway 健康檢查
curl -s http://localhost:9800/health | jq

# Ingestor 健康檢查
curl -s http://localhost:9900/health | jq

# Reranker 健康檢查
curl -s http://localhost:9080/health | jq
```

### 6.2 服務狀態檢查
```bash
# 檢查 Ollama 模型狀態
curl -s http://localhost:11434/api/tags | jq '.models[].name'

# 檢查 Qdrant 集合
curl -s http://localhost:6333/collections | jq '.result.collections[]'

# 檢查 Neo4j 連線
curl -s http://localhost:7474/ | head -n 1
```

---

## 6. 效能測試

### 7.1 回應時間測試
```bash
# 測試不同模型的回應時間
time curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{"model":"rag-answer","messages":[{"role":"user","content":"Hello"}]}' \
  > /dev/null

time curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{"model":"rag-answer-groq","messages":[{"role":"user","content":"Hello"}]}' \
  > /dev/null
```

### 7.2 並發測試
```bash
# 簡單並發測試
for i in {1..5}; do
  curl -s http://localhost:9800/search \
    -H "X-API-Key: dev-key" \
    -H "Content-Type: application/json" \
    -d '{"query":"測試查詢","top_k":3}' \
    > result_$i.json &
done
wait
echo "並發測試完成"
```

---

## 7. 錯誤測試

### 8.1 認證錯誤測試
```bash
# 錯誤的 API Key
curl -s http://localhost:9800/search \
  -H "X-API-Key: wrong-key" \
  -H "Content-Type: application/json" \
  -d '{"query":"test"}' | jq '.error'

# 缺少認證
curl -s http://localhost:9800/search \
  -H "Content-Type: application/json" \
  -d '{"query":"test"}' | jq '.error'
```

### 8.2 模型錯誤測試
```bash
# 不存在的模型
curl -s http://localhost:9400/v1/chat/completions \
  -H "Authorization: Bearer sk-admin" \
  -H "Content-Type: application/json" \
  -d '{"model":"nonexistent-model","messages":[{"role":"user","content":"test"}]}' \
  | jq '.error'
```

---

## 8. 實用腳本

### 9.1 批量模型測試腳本
```bash
#!/bin/bash
# test_all_models.sh

models=("rag-answer" "rag-answer-pro" "rag-answer-gemini" "rag-answer-groq")
test_query="請用一句話解釋什麼是 AI？"

echo "開始測試所有模型..."
for model in "${models[@]}"; do
  echo "測試模型: $model"
  curl -s http://localhost:9400/v1/chat/completions \
    -H "Authorization: Bearer sk-admin" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"$test_query\"}]}" \
    | jq -r '.choices[0].message.content' | head -c 100
  echo "..."
  echo "---"
done
```

### 9.2 服務狀態檢查腳本
```bash
#!/bin/bash
# check_services.sh

services=(
  "LiteLLM:9400/health"
  "API Gateway:9800/health"
  "Ingestor:9900/health"
  "Reranker:9080/health"
)

echo "檢查所有服務狀態..."
for service in "${services[@]}"; do
  name=$(echo $service | cut -d: -f1)
  endpoint=$(echo $service | cut -d: -f2-)

  if curl -s http://localhost:$endpoint > /dev/null 2>&1; then
    echo "✅ $name: 正常"
  else
    echo "❌ $name: 異常"
  fi
done
```

---

## 使用說明

1. **複製命令**: 直接複製需要的 curl 命令到終端執行
2. **修改參數**: 根據需求調整 JSON 參數中的內容
3. **管線過濾**: 使用 `jq` 來過濾和格式化輸出結果
4. **批次測試**: 使用提供的腳本進行批量測試
5. **錯誤排查**: 透過錯誤測試命令驗證系統的錯誤處理

## 注意事項

- 確保所有服務都已啟動 (`docker compose up -d`)
- 檢查必要的環境變數是否已設定 (.env 檔案)
- 某些測試需要先攝入文件資料
- 建議在測試前執行健康檢查確認服務狀態
