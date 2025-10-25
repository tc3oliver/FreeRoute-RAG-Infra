# 管理員 API 文件（/admin）

所有端點皆需管理員 API Key（`Authorization: Bearer <admin-key>`）。

## 1. 建立租戶
- **POST** `/admin/tenants`
- 建立新租戶，回傳租戶資訊與初始 API Key（只顯示一次）

**Request 範例**
```json
{
  "name": "Acme Corp",
  "description": "Acme 公司的知識租戶"
}
```

**Response 範例**
```json
{
  "tenant_id": "acme8x",
  "name": "Acme Corp",
  "description": "Acme 公司的知識租戶",
  "api_key": "sk-acme8x-xxxx",
  "created_at": "2025-10-26T12:34:56Z"
}
```

---

## 2. 查詢租戶列表
- **GET** `/admin/tenants?limit=100&offset=0`
- 取得所有租戶（分頁）

**Response 範例**
```json
{
  "tenants": [
    {
      "tenant_id": "acme8x",
      "name": "Acme Corp",
      "description": "Acme 公司的知識租戶",
      "status": "active",
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 1
}
```

---

## 3. 查詢單一租戶（含 API Key）
- **GET** `/admin/tenants/{tenant_id}`
- 取得指定租戶詳細資訊與所有 API Key

**Response 範例**
```json
{
  "tenant_id": "acme8x",
  "name": "Acme Corp",
  "description": "...",
  "status": "active",
  "created_at": "...",
  "updated_at": "...",
  "api_keys": [
    {
      "key_id": "uuid",
      "tenant_id": "acme8x",
      "key_prefix": "sk-acme8x",
      "name": "default",
      "created_at": "...",
      "expires_at": "...",
      "last_used_at": "...",
      "status": "active"
    }
  ]
}
```

---

## 4. 更新租戶狀態
- **PUT** `/admin/tenants/{tenant_id}/status`
- 更新租戶狀態（active/suspended/deleted）

**Request 範例**
```json
{ "status": "suspended" }
```

**Response 範例**
```json
{ "tenant_id": "acme8x", "status": "suspended" }
```

---

## 5. 刪除租戶（軟刪除）
- **DELETE** `/admin/tenants/{tenant_id}`
- 標記租戶為 deleted，實際資料清理由背景任務處理

**Response 範例**
```json
{
  "status": "deleted",
  "tenant_id": "acme8x",
  "message": "Tenant acme8x marked as deleted. Background cleanup pending."
}
```

---

## 6. 新增 API Key
- **POST** `/admin/tenants/{tenant_id}/api-keys`
- 為租戶新增 API Key，回傳完整金鑰（只顯示一次）

**Request 範例**
```json
{
  "name": "integration-key",
  "expires_at": "2025-12-31T23:59:59Z"
}
```

**Response 範例**
```json
{
  "key_id": "uuid",
  "tenant_id": "acme8x",
  "api_key": "sk-acme8x-xxxx",
  "name": "integration-key",
  "created_at": "...",
  "expires_at": "..."
}
```

---

## 7. 移除 API Key
- **DELETE** `/admin/tenants/{tenant_id}/api-keys/{key_id}`
- 移除指定 API Key（204 No Content）

---

**備註**
- 所有端點皆需 `Authorization: Bearer <admin-key>`
- 刪除租戶僅標記，實際資料清理需額外處理
- API Key 只在建立時回傳一次，請妥善保存
