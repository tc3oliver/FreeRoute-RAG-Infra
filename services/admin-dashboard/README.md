# 🧭 Admin Dashboard

## 概述

`admin-dashboard` 是 **FreeRoute RAG Infra** 的獨立後台管理服務（基於 FastAPI），提供：

* **租戶（Tenants）與 API Key 管理**

  * 建立租戶、發行 API Key（明文僅顯示一次，資料庫以 bcrypt 儲存雜湊）
* **RAG 知識庫管理（Qdrant）**

  * 列出 / 建立 / 刪除 collections
  * 檢視與刪除 points（支援 raw debug）
* **圖譜管理（Neo4j）**

  * 查詢節點、執行 Cypher 語句、刪除節點

此服務直接連線至資料庫、Qdrant 與 Neo4j，不經 Gateway Proxy，可作為內部管理節點容器化部署。

---

## ✨ 特色

* FastAPI + Async 客戶端（支援 Qdrant / Neo4j）
* 內建前端管理介面 `/admin/ui`
* 內建 **AuditLog**（所有操作紀錄寫入 Tenant DB）
* 支援 Docker Compose 容器間直接連線
* 簡單安全機制（以 `ADMIN_TOKEN` 驗證）

---

## ⚙️ 開發環境啟動

### 1️⃣ 安裝相依套件

```bash
pip install -r requirements.txt
```

### 2️⃣ 設定環境變數

以下為必填項：

```bash
export ADMIN_TOKEN=admin-secret-key
export TENANT_DB_URL=postgresql+asyncpg://user:pass@tenant-db:5432/tenants
export QDRANT_URL=http://qdrant:6333
export NEO4J_URI=http://neo4j:7474
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=secret
```

### 3️⃣ 啟動開發伺服器

```bash
uvicorn services.admin-dashboard.app:app --host 0.0.0.0 --port 9000 --reload
```

### 4️⃣ 開啟管理介面

前往：

```
http://localhost:9000/admin/ui
```

輸入或於 localStorage 設定 `ADMIN_TOKEN` 後即可登入。

---

## 🐳 Docker / Production 部署

在專案根目錄的 `docker-compose.yml` 中可直接加入此模組，例如：

```yaml
services:
  admin-dashboard:
    build: ./services/admin-dashboard
    ports:
      - "9000:9000"
    environment:
      ADMIN_TOKEN: admin-secret-key
      TENANT_DB_URL: postgresql+asyncpg://user:pass@tenant-db:5432/tenants
      QDRANT_URL: http://qdrant:6333
      NEO4J_URI: http://neo4j:7474
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: secret
    depends_on:
      - tenant-db
      - qdrant
      - neo4j
    networks:
      - internal
```

> 💡 在容器網路中請使用 service 名稱（如 `tenant-db`, `qdrant`, `neo4j`）作為主機位址。

---

## 🔑 主要環境變數

| 變數名稱                            | 說明                                 |
| ------------------------------- | ---------------------------------- |
| `ADMIN_TOKEN`                   | 管理 UI / API 的簡易驗證令牌（開發用）           |
| `TENANT_DB_URL`                 | Tenant 資料庫連線字串（Postgres + asyncpg） |
| `QDRANT_URL`                    | Qdrant API 服務位址                    |
| `NEO4J_URI`                     | Neo4j HTTP 端點                      |
| `NEO4J_USER` / `NEO4J_PASSWORD` | Neo4j 認證資訊                         |

---

## 📡 主要 API 範例

所有管理 API 均需在 Header 帶入：

```
X-Admin-Token: <ADMIN_TOKEN>
```

### 🏷️ 租戶與 API Key

```bash
GET    /admin/tenants
POST   /admin/tenants
DELETE /admin/tenants/{tenant_id}

GET    /admin/tenants/{tenant_id}/apikeys
POST   /admin/tenants/{tenant_id}/apikeys   # 建立 API Key（回傳一次性 plaintext）
DELETE /admin/apikeys/{key_id}
```

---

### 🧠 RAG（Qdrant）

```bash
GET    /admin/rag/collections
POST   /admin/rag/collections
DELETE /admin/rag/collections/{name}

GET    /admin/rag/collections/{name}/points?limit=&offset=&raw=
DELETE /admin/rag/collections/{name}/points/{point_id}
```

> `raw=true` 可回傳 Qdrant Client 原始結構（供 debug）

---

### 🌐 Graph（Neo4j）

```bash
GET    /admin/graph/records?limit=&offset=&tenant_id=
POST   /admin/graph/cypher   # body: { "cypher": "...", "params": {}, "read": true }
```

---

## 🔒 認證與安全

* 預設使用 `X-Admin-Token` 作為管理認證，僅適合內部或開發環境。
* 生產環境建議改用：

  * OAuth2 + JWT
  * RBAC 權限控管
  * HTTPS + 防火牆限制

---

## 🧩 除錯與常見問題

| 問題            | 排查建議                                       |
| ------------- | ------------------------------------------ |
| 管理頁面載入空白      | 檢查 `ADMIN_TOKEN` 是否正確                      |
| Qdrant 操作異常   | 檢查版本與 API 格式；可使用 `?raw=true` 回傳原始資料        |
| Neo4j 查詢失敗    | 檢查 `NEO4J_URI` / 認證設定與容器網路可達性              |
| Postgres 無法連線 | 確認 `TENANT_DB_URL` 主機名稱對應到 Compose network |
