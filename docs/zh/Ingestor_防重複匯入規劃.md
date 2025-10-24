# Ingestor 防重複匯入規劃文件

## 目標
確保多租戶、多資料夾環境下，Ingestor 能有效防止同一份檔案或內容被重複匯入向量庫（Qdrant）與圖譜（Neo4j），避免資料污染與資源浪費。

---

## 需求說明

- **多租戶**：每個 tenant 有獨立的資料空間，但同一租戶可能重複上傳同一份檔案。
- **多資料夾**：同一租戶下不同目錄可能有相同檔案（內容或檔名）。
- **重複來源**：可能來自同一檔案、不同檔案但內容相同、或跨租戶（可選是否全域防重）。
- **防重點**：只要內容（hash）重複，應避免重複匯入。

---

## 技術方案

### 1. 檔案內容 Hash 計算
- 每個檔案 ingest 前，計算內容的 SHA256（或更快的 hash）。
- 可選：chunk 級別 hash（若分段 ingest）。

### 2. Hash 持久化儲存
- **Qdrant**：每個向量 payload 增加 `content_hash` 欄位。
- **Neo4j**：每個 node 增加 `content_hash` 屬性。
- **外部 DB**（可選）：建立 `ingest_hashes` table，記錄 `(tenant_id, content_hash, file_path, created_at)`。

### 3. 匯入前查重
- Ingestor 在匯入前，查詢該 tenant/collection/graph 是否已存在相同 `content_hash`。
- 若已存在，跳過該檔案或 chunk，不重複匯入。

### 4. API/CLI 介面
- CLI/API 增加 `--skip-duplicate` 參數（預設開啟）。
- 匯入報告顯示哪些檔案/內容被跳過。

### 5. 可選進階
- 支援「全域查重」：跨租戶查詢 hash（如有合規需求）。
- 支援「強制覆蓋」：加參數允許重複匯入（如需重新整理資料）。

---

## 實作步驟

1. **設計 hash 計算與儲存格式**
   - 決定 hash 粒度（檔案/段落/頁面）
   - 決定 payload/schema 格式

2. **修改 Ingestor pipeline**
   - 匯入前查詢 hash
   - 匯入時寫入 hash

3. **修改 Qdrant/Neo4j repository**
   - 增加 hash 查詢與寫入邏輯

4. **CLI/API 參數與回報**
   - 增加 `--skip-duplicate` 參數
   - 匯入結果顯示哪些被跳過

5. **測試**
   - 單元測試：同一檔案多次匯入只會成功一次
   - 整合測試：跨租戶、跨資料夾測試

---

## 風險與注意事項

- Hash 計算需一致（不同 OS/編碼/換行符需正規化）
- 若 chunk 級別 hash，需考慮分段策略一致性
- 查詢效率：Qdrant/Neo4j 須為 hash 建索引
- 合規：如需跨租戶查重，需考慮資料隔離政策

---

## 後續建議

- 若資料量大，考慮用外部 DB 儲存 hash 索引
- 可結合檔案 metadata（如 file_id、來源 URI）做更細緻的重複判斷
- 支援 hash 清理（當資料被刪除時同步移除 hash）

---

## 結論

此方案可大幅降低重複資料匯入風險，提升多租戶 RAG 系統的資料品質與效能。建議納入主線開發，並於 M4/M5 階段實作。
