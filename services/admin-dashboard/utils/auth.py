from os import getenv

from fastapi import Header, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

ADMIN_TOKEN = getenv("ADMIN_TOKEN")
admin_api_key = APIKeyHeader(name="X-Admin-Token", auto_error=False)


async def require_admin_token(x_admin_token: str = Security(admin_api_key)):
    """簡單的 header token 驗證，預期環境變數 ADMIN_TOKEN 被設定。"""
    if not ADMIN_TOKEN:
        # 如果沒有設定，允許通過（開發模式）
        return True
    if not x_admin_token:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Token header")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return True
