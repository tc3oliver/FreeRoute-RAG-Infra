from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..utils.auth import require_admin_token
from ..utils.db_helper import delete_api_key, get_api_key_by_id, patch_api_key_status, validate_api_key

router = APIRouter()


def _key_to_dict(key):
    if key is None:
        return None
    if isinstance(key, dict):
        return key
    # SQLAlchemy model instance
    return {
        "key_id": str(key.key_id),
        "tenant_id": key.tenant_id,
        "key_prefix": key.key_prefix,
        "name": key.name,
        "created_at": key.created_at,
        "expires_at": key.expires_at,
        "last_used_at": key.last_used_at,
        "status": key.status,
    }


@router.get("/{key_id}")
async def get_apikey(key_id: str, _: Any = Depends(require_admin_token), db: AsyncSession = Depends(get_db)):
    key = await get_api_key_by_id(db, key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    return _key_to_dict(key)


@router.delete("/{key_id}")
async def delete_apikey(key_id: str, _: Any = Depends(require_admin_token), db: AsyncSession = Depends(get_db)):
    deleted = await delete_api_key(db, key_id)
    return {"deleted": deleted}


@router.patch("/{key_id}/status")
async def patch_apikey_status_endpoint(
    key_id: str, payload: Dict[str, Any], _: Any = Depends(require_admin_token), db: AsyncSession = Depends(get_db)
):
    status = payload.get("status")
    updated = await patch_api_key_status(db, key_id, status)
    return {"updated": updated}


@router.post("/validate")
async def validate_key(
    payload: Dict[str, Any], _: Any = Depends(require_admin_token), db: AsyncSession = Depends(get_db)
):
    api_key_value = payload.get("api_key")
    if not api_key_value:
        raise HTTPException(status_code=400, detail="api_key is required")
    key = await validate_api_key(db, api_key_value)
    return {"valid": bool(key), "key": _key_to_dict(key)}
