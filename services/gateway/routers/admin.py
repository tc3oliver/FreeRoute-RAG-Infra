"""Admin API router for tenant management."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from ..deps import require_admin_key
from ..models_tenant import (
    APIKeyResponse,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    CreateTenantRequest,
    CreateTenantResponse,
    DeleteTenantResponse,
    TenantDetailResponse,
    TenantListResponse,
    TenantResponse,
)
from ..repositories.tenant_repo import TenantRepository

router = APIRouter(prefix="/admin", tags=["admin"])


@router.put("/tenants/{tenant_id}/status", status_code=200)
async def update_tenant_status(
    tenant_id: str, status: str = Body(..., embed=True), _admin: bool = Depends(require_admin_key)
):
    """
    Update tenant status (active/suspended/deleted).
    **Requires admin API key.**
    """
    repo = TenantRepository()
    success = await repo.update_tenant_status(tenant_id, status)
    if not success:
        raise HTTPException(404, f"Tenant {tenant_id} not found")
    return {"tenant_id": tenant_id, "status": status}


@router.post("/tenants", response_model=CreateTenantResponse, status_code=201)
async def create_tenant(req: CreateTenantRequest, _admin: bool = Depends(require_admin_key)):
    """
    Create a new tenant with an auto-generated tenant_id and API key.

    **Requires admin API key.**

    Returns the tenant information along with the initial API key (shown only once).
    """
    repo = TenantRepository()

    try:
        tenant_id, api_key = await repo.create_tenant(name=req.name, description=req.description)

        # Fetch created tenant
        tenant = await repo.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(500, "Failed to create tenant")

        return CreateTenantResponse(
            tenant_id=tenant["tenant_id"],
            name=tenant["name"],
            description=tenant["description"],
            api_key=api_key,
            created_at=tenant["created_at"],
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to create tenant: {str(e)}")


@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), _admin: bool = Depends(require_admin_key)
):
    """
    List all tenants.

    **Requires admin API key.**
    """
    repo = TenantRepository()

    try:
        tenants = await repo.list_tenants(limit=limit, offset=offset)
        total = await repo.count_tenants()

        tenant_responses = [
            TenantResponse(
                tenant_id=t["tenant_id"],
                name=t["name"],
                description=t["description"],
                status=t["status"],
                created_at=t["created_at"],
                updated_at=t["updated_at"],
            )
            for t in tenants
        ]

        return TenantListResponse(tenants=tenant_responses, total=total)
    except Exception as e:
        raise HTTPException(500, f"Failed to list tenants: {str(e)}")


@router.get("/tenants/{tenant_id}", response_model=TenantDetailResponse)
async def get_tenant(tenant_id: str, _admin: bool = Depends(require_admin_key)):
    """
    Get detailed information about a specific tenant, including API keys.

    **Requires admin API key.**
    """
    repo = TenantRepository()

    try:
        tenant = await repo.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(404, f"Tenant {tenant_id} not found")

        api_keys = await repo.list_api_keys(tenant_id)

        api_key_responses = [
            APIKeyResponse(
                key_id=k["key_id"],
                tenant_id=k["tenant_id"],
                key_prefix=k["key_prefix"],
                name=k["name"],
                created_at=k["created_at"],
                expires_at=k["expires_at"],
                last_used_at=k["last_used_at"],
                status=k["status"],
            )
            for k in api_keys
        ]

        return TenantDetailResponse(
            tenant_id=tenant["tenant_id"],
            name=tenant["name"],
            description=tenant["description"],
            status=tenant["status"],
            created_at=tenant["created_at"],
            updated_at=tenant["updated_at"],
            api_keys=api_key_responses,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to get tenant: {str(e)}")


@router.delete("/tenants/{tenant_id}", response_model=DeleteTenantResponse)
async def delete_tenant(tenant_id: str, _admin: bool = Depends(require_admin_key)):
    """
    Delete a tenant (soft delete).

    **Requires admin API key.**

    Note: This marks the tenant as deleted. Actual data cleanup
    (Qdrant collections, Neo4j nodes, etc.) should be done by a background job.
    """
    repo = TenantRepository()

    try:
        success = await repo.delete_tenant(tenant_id)
        if not success:
            raise HTTPException(404, f"Tenant {tenant_id} not found")

        return DeleteTenantResponse(
            status="deleted",
            tenant_id=tenant_id,
            message=f"Tenant {tenant_id} marked as deleted. Background cleanup pending.",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to delete tenant: {str(e)}")


@router.post("/tenants/{tenant_id}/api-keys", response_model=CreateAPIKeyResponse, status_code=201)
async def create_api_key(tenant_id: str, req: CreateAPIKeyRequest, _admin: bool = Depends(require_admin_key)):
    """
    Create a new API key for a tenant.

    **Requires admin API key.**

    Returns the full API key (shown only once).
    """
    repo = TenantRepository()

    try:
        # Calculate expires_in_days from expires_at if provided
        expires_in_days = None
        if req.expires_at:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            delta = req.expires_at - now
            expires_in_days = max(1, int(delta.total_seconds() / 86400))  # Convert to days

        key_data = await repo.create_api_key(tenant_id=tenant_id, name=req.name, expires_in_days=expires_in_days)

        return CreateAPIKeyResponse(
            key_id=key_data["id"],
            tenant_id=key_data["tenant_id"],
            api_key=key_data["api_key"],
            name=key_data["name"],
            created_at=key_data["created_at"],
            expires_at=key_data["expires_at"],
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to create API key: {str(e)}")


@router.delete("/tenants/{tenant_id}/api-keys/{key_id}", status_code=204)
async def revoke_api_key(tenant_id: str, key_id: UUID, _admin: bool = Depends(require_admin_key)):
    """
    Revoke an API key.

    **Requires admin API key.**
    """
    repo = TenantRepository()

    try:
        success = await repo.revoke_api_key(tenant_id, key_id)
        if not success:
            raise HTTPException(404, f"API key {key_id} not found for tenant {tenant_id}")

        return None  # 204 No Content
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to revoke API key: {str(e)}")
