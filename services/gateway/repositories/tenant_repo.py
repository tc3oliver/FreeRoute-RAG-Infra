"""Repository for tenant and API key management (SQLAlchemy ORM)."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.connection import get_db_session
from ..db.models import APIKey, AuditLog, Tenant


class TenantRepository:
    async def list_api_keys(self, tenant_id: str) -> list[dict]:
        """List all API keys for a tenant."""
        async with get_db_session() as session:
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

    async def update_tenant_status(self, tenant_id: str, status: str) -> bool:
        """
        Update tenant status (active/suspended/deleted).
        """
        async with get_db_session() as session:
            if status not in ("active", "suspended", "deleted"):
                raise ValueError("Invalid status")
            result = await session.execute(
                update(Tenant).where(Tenant.tenant_id == tenant_id).values(status=status, updated_at=datetime.utcnow())
            )
            await session.commit()
            return result.rowcount > 0

    """Repository for tenant operations using SQLAlchemy ORM."""

    @staticmethod
    def generate_tenant_id() -> str:
        """Generate a unique tenant ID (8 characters)."""
        return secrets.token_urlsafe(6)[:8].lower().replace("_", "x").replace("-", "y")

    @staticmethod
    def generate_api_key(tenant_id: str) -> str:
        """Generate an API key with format: sk-{tenant_id}-{random}."""
        random_part = secrets.token_urlsafe(32)
        return f"sk-{tenant_id}-{random_part}"

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash an API key using bcrypt."""
        return bcrypt.hashpw(api_key.encode(), bcrypt.gensalt(rounds=12)).decode()

    @staticmethod
    def verify_api_key_hash(api_key: str, hashed: str) -> bool:
        """Verify an API key against its hash."""
        return bcrypt.checkpw(api_key.encode(), hashed.encode())

    async def create_tenant(
        self, name: str, description: Optional[str] = None, max_retries: int = 5
    ) -> tuple[str, str]:
        """
        Create a new tenant with an initial API key.
        Returns: (tenant_id, api_key)
        """
        for attempt in range(max_retries):
            tenant_id = self.generate_tenant_id()

            try:
                async with get_db_session() as session:
                    # Check if tenant_id already exists
                    result = await session.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
                    if result.scalar_one_or_none():
                        continue  # Collision, retry

                    # Create tenant
                    tenant = Tenant(tenant_id=tenant_id, name=name, description=description, status="active")
                    session.add(tenant)

                    # Generate and hash API key
                    api_key = self.generate_api_key(tenant_id)
                    api_key_hash = self.hash_api_key(api_key)
                    key_prefix = f"sk-{tenant_id}"

                    # Create API key
                    key = APIKey(
                        tenant_id=tenant_id,
                        api_key_hash=api_key_hash,
                        key_prefix=key_prefix,
                        name="default",
                        status="active",
                    )
                    session.add(key)

                    # Log audit
                    audit = AuditLog(
                        tenant_id=tenant_id, action="create_tenant", actor="system", details={"name": name}
                    )
                    session.add(audit)

                    await session.commit()

                    return tenant_id, api_key

            except Exception as e:
                if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
                    if attempt < max_retries - 1:
                        continue
                raise

        raise RuntimeError("Failed to generate unique tenant ID after retries")

    async def get_tenant(self, tenant_id: str) -> Optional[dict]:
        """Get tenant by ID."""
        async with get_db_session() as session:
            result = await session.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
            tenant = result.scalar_one_or_none()

            if not tenant:
                return None

            return {
                "tenant_id": tenant.tenant_id,
                "name": tenant.name,
                "description": tenant.description,
                "status": tenant.status,
                "created_at": tenant.created_at,
                "updated_at": tenant.updated_at,
            }

    async def list_tenants(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """List all tenants."""
        async with get_db_session() as session:
            result = await session.execute(
                select(Tenant).order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
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

    async def count_tenants(self) -> int:
        """Count total tenants."""
        async with get_db_session() as session:
            result = await session.execute(select(func.count(Tenant.tenant_id)))
            return result.scalar() or 0

    async def delete_tenant(self, tenant_id: str) -> bool:
        """
        Delete a tenant (soft delete by setting status).
        API keys will be CASCADE deleted by database.
        """
        async with get_db_session() as session:
            result = await session.execute(
                update(Tenant)
                .where(Tenant.tenant_id == tenant_id)
                .values(status="deleted", updated_at=datetime.utcnow())
            )

            # Log audit
            audit = AuditLog(
                tenant_id=tenant_id, action="delete_tenant", actor="admin", details={"tenant_id": tenant_id}
            )
            session.add(audit)

            await session.commit()
            return result.rowcount > 0

    async def create_api_key(
        self, tenant_id: str, name: Optional[str] = None, expires_in_days: Optional[int] = None
    ) -> dict:
        """Create a new API key for a tenant."""
        api_key = self.generate_api_key(tenant_id)
        api_key_hash = self.hash_api_key(api_key)
        key_prefix = f"sk-{tenant_id}"

        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        async with get_db_session() as session:
            key = APIKey(
                tenant_id=tenant_id,
                api_key_hash=api_key_hash,
                key_prefix=key_prefix,
                name=name or "api-key",
                expires_at=expires_at,
                status="active",
            )
            session.add(key)

            # Log audit
            audit = AuditLog(
                tenant_id=tenant_id,
                action="create_api_key",
                actor="admin",
                details={"key_id": str(key.key_id), "name": name},
            )
            session.add(audit)

            await session.commit()

            return {
                "id": key.key_id,
                "tenant_id": key.tenant_id,
                "api_key": api_key,  # Return plaintext key (only time it's shown)
                "name": key.name,
                "created_at": key.created_at,
                "expires_at": key.expires_at,
            }

    async def verify_api_key(self, api_key: str) -> Optional[str]:
        """
        Verify an API key and return tenant_id if valid and tenant is active.
        Also updates last_used_at timestamp.
        """
        # Parse key format: sk-{tenant_id}-{random}
        if not api_key.startswith("sk-") or api_key.count("-") < 2:
            return None

        parts = api_key.split("-", 2)
        tenant_id = parts[1]
        key_prefix = f"sk-{tenant_id}"

        async with get_db_session() as session:
            # Check tenant status
            tenant_result = await session.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
            tenant = tenant_result.scalar_one_or_none()
            if not tenant or tenant.status != "active":
                return None

            # Find active keys for this tenant
            result = await session.execute(
                select(APIKey).where(APIKey.key_prefix == key_prefix, APIKey.status == "active")
            )
            keys = result.scalars().all()

            # Check each key's hash
            now = datetime.now(timezone.utc)
            for key in keys:
                # Check expiration
                if key.expires_at and key.expires_at < now:
                    continue

                # Verify hash
                if self.verify_api_key_hash(api_key, key.api_key_hash):
                    # Update last_used_at (in background, don't block response)
                    await session.execute(update(APIKey).where(APIKey.key_id == key.key_id).values(last_used_at=now))
                    await session.commit()

                    return tenant_id

            return None

    async def revoke_api_key(self, tenant_id: str, key_id: UUID) -> bool:
        """Revoke an API key."""
        async with get_db_session() as session:
            result = await session.execute(
                update(APIKey).where(APIKey.key_id == key_id, APIKey.tenant_id == tenant_id).values(status="revoked")
            )

            # Log audit
            audit = AuditLog(
                tenant_id=tenant_id, action="revoke_api_key", actor="admin", details={"key_id": str(key_id)}
            )
            session.add(audit)

            await session.commit()
            return result.rowcount > 0

    async def log_audit(self, tenant_id: Optional[str], action: str, actor: str, details: Optional[dict] = None):
        """Log an audit event."""
        async with get_db_session() as session:
            audit = AuditLog(tenant_id=tenant_id, action=action, actor=actor, details=details)
            session.add(audit)
            await session.commit()
