"""
共用依賴：API 金鑰驗證
"""

import os
from typing import Optional

from fastapi import Header, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .repositories.tenant_repo import TenantRepository

# Legacy API keys (for backwards compatibility during migration)
API_KEYS = {k.strip() for k in os.environ.get("API_GATEWAY_KEYS", "dev-key").split(",") if k.strip()}

security = HTTPBearer()


async def require_key(x_api_key: Optional[str] = Header(None), authorization: Optional[str] = Header(None)) -> str:
    """
    驗證 API 金鑰並返回 tenant_id

    支援兩種金鑰格式:
    - 新格式: sk-{tenant_id}-{random} (從資料庫驗證)
    - 舊格式: 任意字串 (向後相容,映射到 "default" tenant)

    Returns:
        tenant_id: 該 API key 所屬的 tenant ID

    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_api_key:
        token = x_api_key.strip()

    if not token:
        raise HTTPException(status_code=401, detail="Missing API key")

    # Check if it's a tenant-based API key (new format: sk-{tenant_id}-{random})
    if token.startswith("sk-") and token.count("-") >= 2:
        repo = TenantRepository()
        tenant_id = await repo.verify_api_key(token)
        if tenant_id:
            return tenant_id
        raise HTTPException(status_code=401, detail="Invalid or expired API key")

    # Legacy API key (backwards compatibility)
    if token in API_KEYS:
        return "default"  # Map legacy keys to default tenant

    raise HTTPException(status_code=401, detail="Invalid API key")


async def require_admin_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> None:
    """
    驗證 Admin API 金鑰 (用於 /admin/* 端點)
    從環境變數 ADMIN_API_KEY 讀取,預設為 "admin-secret-key"

    Raises:
        HTTPException: 403 if admin key is missing or invalid
    """
    token = credentials.credentials
    admin_key = os.getenv("ADMIN_API_KEY", "admin-secret-key")

    if token != admin_key:
        raise HTTPException(status_code=403, detail="Admin access required")
