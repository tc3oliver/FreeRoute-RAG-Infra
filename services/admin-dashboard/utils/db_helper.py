"""
CRUD helper for tenants, api_keys, audit_logs (複用 gateway/db/models.py)
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.db.models import APIKey, AuditLog, Tenant


# 租戶 CRUD - 參考 gateway/repositories/tenant_repo.py 的行為和回傳格式
async def get_tenants(session: AsyncSession, limit: int = 100, offset: int = 0) -> List[dict]:
    # By default exclude tenants marked as 'deleted'
    result = await session.execute(
        select(Tenant).where(Tenant.status != "deleted").order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
    )
    tenants = result.scalars().all()
    return [
        {
            "tenant_id": t.tenant_id,
            "name": t.name,
            "description": t.description,
            "status": t.status,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
        for t in tenants
    ]


async def get_tenant(session: AsyncSession, tenant_id: str) -> Optional[dict]:
    result = await session.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return None
    # Treat deleted tenants as non-existent for API listing/details
    if getattr(tenant, "status", None) == "deleted":
        return None
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "description": tenant.description,
        "status": tenant.status,
        "created_at": tenant.created_at,
        "updated_at": tenant.updated_at,
    }


async def create_tenant(session: AsyncSession, name: str, description: str = "") -> dict:
    """Create tenant and initial API key. Returns {tenant_id, api_key, ...}
    Behavior mirrors gateway TenantRepository.create_tenant
    """
    max_retries = 5
    for attempt in range(max_retries):
        tenant_id = secrets.token_urlsafe(6)[:8].lower().replace("_", "x").replace("-", "y")
        try:
            # Check collision
            res = await session.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
            if res.scalar_one_or_none():
                continue

            tenant = Tenant(tenant_id=tenant_id, name=name, description=description, status="active")
            session.add(tenant)

            # generate api key, hash and store
            api_key = f"sk-{tenant_id}-{secrets.token_urlsafe(32)}"
            api_key_hash = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt(rounds=12)).decode()
            key_prefix = f"sk-{tenant_id}"

            key = APIKey(
                tenant_id=tenant_id,
                api_key_hash=api_key_hash,
                key_prefix=key_prefix,
                name="default",
                status="active",
            )
            session.add(key)

            audit = AuditLog(
                tenant_id=tenant_id, action="create_tenant", actor="admin-dashboard", details={"name": name}
            )
            session.add(audit)

            await session.commit()

            return {
                "tenant_id": tenant_id,
                "name": name,
                "description": description,
                "api_key": api_key,
                "created_at": tenant.created_at,
            }
        except Exception as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                if attempt < max_retries - 1:
                    continue
            raise
    raise RuntimeError("Failed to create tenant after retries")


async def delete_tenant(session: AsyncSession, tenant_id: str) -> int:
    result = await session.execute(
        update(Tenant).where(Tenant.tenant_id == tenant_id).values(status="deleted", updated_at=datetime.utcnow())
    )
    # log audit
    audit = AuditLog(
        tenant_id=tenant_id, action="delete_tenant", actor="admin-dashboard", details={"tenant_id": tenant_id}
    )
    session.add(audit)
    await session.commit()
    return result.rowcount


async def update_tenant_status(session: AsyncSession, tenant_id: str, status: str) -> int:
    result = await session.execute(
        update(Tenant).where(Tenant.tenant_id == tenant_id).values(status=status, updated_at=datetime.utcnow())
    )
    await session.commit()
    return result.rowcount


async def get_api_keys(session: AsyncSession, tenant_id: str) -> List[dict]:
    result = await session.execute(select(APIKey).where(APIKey.tenant_id == tenant_id))
    keys = result.scalars().all()
    return [
        {
            "key_id": str(k.key_id),
            "tenant_id": k.tenant_id,
            "key_prefix": k.key_prefix,
            "name": k.name,
            "created_at": k.created_at,
            "expires_at": k.expires_at,
            "last_used_at": k.last_used_at,
            "status": k.status,
        }
        for k in keys
    ]


async def create_api_key(
    session: AsyncSession, tenant_id: str, name: str = None, expires_in_days: Optional[int] = None
) -> dict:
    api_key = f"sk-{tenant_id}-{secrets.token_urlsafe(32)}"
    api_key_hash = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt(rounds=12)).decode()
    key_prefix = f"sk-{tenant_id}"

    expires_at = None
    if expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    key = APIKey(
        tenant_id=tenant_id,
        api_key_hash=api_key_hash,
        key_prefix=key_prefix,
        name=name or "api-key",
        expires_at=expires_at,
        status="active",
    )
    session.add(key)
    audit = AuditLog(tenant_id=tenant_id, action="create_api_key", actor="admin-dashboard", details={"name": name})
    session.add(audit)
    await session.commit()

    return {
        "id": str(key.key_id),
        "tenant_id": key.tenant_id,
        "api_key": api_key,  # plaintext returned once
        "name": key.name,
        "created_at": key.created_at,
        "expires_at": key.expires_at,
    }


async def delete_api_key(session: AsyncSession, key_id: str) -> int:
    result = await session.execute(delete(APIKey).where(APIKey.key_id == key_id))
    await session.commit()
    return result.rowcount


async def get_api_key_by_id(session: AsyncSession, key_id: str) -> Optional[APIKey]:
    result = await session.execute(select(APIKey).where(APIKey.key_id == key_id))
    return result.scalar_one_or_none()


async def patch_api_key_status(session: AsyncSession, key_id: str, status: str) -> int:
    result = await session.execute(update(APIKey).where(APIKey.key_id == key_id).values(status=status))
    await session.commit()
    return result.rowcount


async def validate_api_key(session: AsyncSession, api_key_value: str) -> Optional[APIKey]:
    """Validate plaintext api_key, return key row if valid (mirrors gateway.verify_api_key logic simplified)."""
    # basic format parse
    if not api_key_value.startswith("sk-") or api_key_value.count("-") < 2:
        return None
    parts = api_key_value.split("-", 2)
    tenant_id = parts[1]
    key_prefix = f"sk-{tenant_id}"

    result = await session.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant or tenant.status != "active":
        return None

    result = await session.execute(select(APIKey).where(APIKey.key_prefix == key_prefix, APIKey.status == "active"))
    keys = result.scalars().all()
    from sqlalchemy import update as sa_update

    now = datetime.now(timezone.utc)
    for key in keys:
        if key.expires_at and key.expires_at < now:
            continue
        try:
            if bcrypt.checkpw(api_key_value.encode(), key.api_key_hash.encode()):
                # update last_used_at
                await session.execute(sa_update(APIKey).where(APIKey.key_id == key.key_id).values(last_used_at=now))
                await session.commit()
                return key
        except Exception:
            continue
    return None
