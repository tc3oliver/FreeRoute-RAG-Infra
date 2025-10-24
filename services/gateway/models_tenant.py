"""Pydantic models for tenant management API."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CreateTenantRequest(BaseModel):
    """Request to create a new tenant."""

    name: str = Field(..., min_length=1, max_length=255, description="Tenant name")
    description: Optional[str] = Field(None, max_length=1000, description="Tenant description")


class TenantResponse(BaseModel):
    """Response for tenant operations."""

    tenant_id: str
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class CreateTenantResponse(BaseModel):
    """Response when creating a new tenant (includes API key)."""

    tenant_id: str
    name: str
    description: Optional[str]
    api_key: str  # Only returned once
    created_at: datetime


class TenantListResponse(BaseModel):
    """Response for listing tenants."""

    tenants: list[TenantResponse]
    total: int


class CreateAPIKeyRequest(BaseModel):
    """Request to create a new API key for a tenant."""

    name: Optional[str] = Field(None, max_length=255, description="API key name/label")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")


class APIKeyResponse(BaseModel):
    """Response for API key operations."""

    key_id: UUID
    tenant_id: str
    key_prefix: str
    name: Optional[str]
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    status: str


class CreateAPIKeyResponse(BaseModel):
    """Response when creating a new API key (includes full key)."""

    key_id: UUID
    tenant_id: str
    api_key: str  # Only returned once
    name: Optional[str]
    created_at: datetime
    expires_at: Optional[datetime]


class TenantDetailResponse(BaseModel):
    """Detailed tenant information including API keys."""

    tenant_id: str
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    api_keys: list[APIKeyResponse]
    stats: Optional[dict] = None  # Future: doc count, chunk count, etc.


class DeleteTenantResponse(BaseModel):
    """Response when deleting a tenant."""

    status: str
    tenant_id: str
    message: str
    job_id: Optional[str] = None  # For background deletion jobs
