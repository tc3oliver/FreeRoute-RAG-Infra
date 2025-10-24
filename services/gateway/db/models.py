"""SQLAlchemy ORM models for tenant management."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Tenant(Base):
    """Tenant model."""

    __tablename__ = "tenants"

    tenant_id = Column(String, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=datetime.utcnow
    )
    status = Column(String(20), nullable=False, server_default=text("'active'"))

    # Relationships
    api_keys = relationship("APIKey", back_populates="tenant", cascade="all, delete-orphan")


class APIKey(Base):
    """API Key model."""

    __tablename__ = "api_keys"

    key_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(String, ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False, index=True)
    api_key_hash = Column(Text, nullable=False)
    key_prefix = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_used_at = Column(TIMESTAMP(timezone=True), nullable=True, index=True)
    status = Column(String(20), nullable=False, server_default=text("'active'"))

    # Relationships
    tenant = relationship("Tenant", back_populates="api_keys")

    __table_args__ = (UniqueConstraint("key_prefix", "api_key_hash", name="uq_api_keys_prefix_hash"),)


class AuditLog(Base):
    """Audit log model."""

    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(String, nullable=True, index=True)
    action = Column(String(100), nullable=False)
    actor = Column(String(255), nullable=True)
    details = Column("details", JSONB, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)
