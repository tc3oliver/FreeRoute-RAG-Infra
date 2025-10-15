import os
from typing import Optional

from fastapi import Header, HTTPException

API_KEYS = {k.strip() for k in os.environ.get("API_GATEWAY_KEYS", "dev-key").split(",") if k.strip()}


def require_key(x_api_key: Optional[str] = Header(None), authorization: Optional[str] = Header(None)) -> bool:
    token = None
    if x_api_key:
        token = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or token not in API_KEYS:
        raise HTTPException(status_code=401, detail="missing or invalid API key")
    return True
