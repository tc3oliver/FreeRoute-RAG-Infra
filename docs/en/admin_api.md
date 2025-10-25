# Admin API Documentation (/admin)

All endpoints require an admin API Key (`Authorization: Bearer <admin-key>`).

## 1. Create Tenant
- **POST** `/admin/tenants`
- Create a new tenant, returns tenant info and initial API Key (shown only once)

**Request Example**
```json
{
  "name": "Acme Corp",
  "description": "Knowledge tenant for Acme Corp"
}
```

**Response Example**
```json
{
  "tenant_id": "acme8x",
  "name": "Acme Corp",
  "description": "Knowledge tenant for Acme Corp",
  "api_key": "sk-acme8x-xxxx",
  "created_at": "2025-10-26T12:34:56Z"
}
```

---

## 2. List Tenants
- **GET** `/admin/tenants?limit=100&offset=0`
- Get all tenants (paginated)

**Response Example**
```json
{
  "tenants": [
    {
      "tenant_id": "acme8x",
      "name": "Acme Corp",
      "description": "Knowledge tenant for Acme Corp",
      "status": "active",
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 1
}
```

---

## 3. Get Tenant Details (with API Keys)
- **GET** `/admin/tenants/{tenant_id}`
- Get detailed info for a tenant, including all API Keys

**Response Example**
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

## 4. Update Tenant Status
- **PUT** `/admin/tenants/{tenant_id}/status`
- Update tenant status (`active`/`suspended`/`deleted`)

**Request Example**
```json
{ "status": "suspended" }
```

**Response Example**
```json
{ "tenant_id": "acme8x", "status": "suspended" }
```

---

## 5. Delete Tenant (Soft Delete)
- **DELETE** `/admin/tenants/{tenant_id}`
- Marks tenant as deleted; actual data cleanup is handled by background jobs

**Response Example**
```json
{
  "status": "deleted",
  "tenant_id": "acme8x",
  "message": "Tenant acme8x marked as deleted. Background cleanup pending."
}
```

---

## 6. Create API Key
- **POST** `/admin/tenants/{tenant_id}/api-keys`
- Create a new API Key for a tenant, returns the full key (shown only once)

**Request Example**
```json
{
  "name": "integration-key",
  "expires_at": "2025-12-31T23:59:59Z"
}
```

**Response Example**
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

## 7. Revoke API Key
- **DELETE** `/admin/tenants/{tenant_id}/api-keys/{key_id}`
- Remove the specified API Key (204 No Content)

---

**Notes**
- All endpoints require `Authorization: Bearer <admin-key>`
- Deleting a tenant only marks it as deleted; actual data cleanup requires extra handling
- API Keys are only returned once at creation; store them securely
