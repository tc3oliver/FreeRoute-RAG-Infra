from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..utils.auth import require_admin_token
from ..utils.db_helper import (
    create_api_key,
    create_tenant,
    delete_tenant,
    get_api_keys,
    get_tenant,
    get_tenants,
    update_tenant_status,
)

router = APIRouter()


@router.get("/", response_model=List[dict])
async def list_tenants(_: bool = Depends(require_admin_token), db: AsyncSession = Depends(get_db)):
    tenants = await get_tenants(db)
    # db_helper returns list[dict]
    return tenants


@router.get("/{tenant_id}", response_model=dict)
async def get_tenant_detail(tenant_id: str, _: bool = Depends(require_admin_token), db: AsyncSession = Depends(get_db)):
    tenant = await get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.post("/", response_model=dict)
async def create_tenant_api(payload: dict, _: bool = Depends(require_admin_token), db: AsyncSession = Depends(get_db)):
    name = payload.get("name")
    description = payload.get("description", "")
    tenant = await create_tenant(db, name, description)
    return tenant


@router.delete("/{tenant_id}", response_model=dict)
async def delete_tenant_api(tenant_id: str, _: bool = Depends(require_admin_token), db: AsyncSession = Depends(get_db)):
    deleted = await delete_tenant(db, tenant_id)
    return {"deleted": deleted}


@router.patch("/{tenant_id}/status", response_model=dict)
async def patch_status_api(
    tenant_id: str, payload: dict, _: bool = Depends(require_admin_token), db: AsyncSession = Depends(get_db)
):
    status = payload.get("status")
    updated = await update_tenant_status(db, tenant_id, status)
    return {"updated": updated}


@router.get("/{tenant_id}/apikeys", response_model=List[dict])
async def list_apikeys_api(tenant_id: str, _: bool = Depends(require_admin_token), db: AsyncSession = Depends(get_db)):
    keys = await get_api_keys(db, tenant_id)
    return keys


@router.post("/{tenant_id}/apikeys", response_model=dict)
async def create_apikey_api(
    tenant_id: str, payload: dict, _: bool = Depends(require_admin_token), db: AsyncSession = Depends(get_db)
):
    name = payload.get("name", "")
    key = await create_api_key(db, tenant_id, name)
    return key
