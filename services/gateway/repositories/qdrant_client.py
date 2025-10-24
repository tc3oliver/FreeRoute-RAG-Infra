"""
Qdrant vector database client wrapper with tenant isolation.
"""

import importlib
from typing import Any

from ..config import QDRANT_URL

_async_client: Any = None


def get_tenant_collection_name(tenant_id: str, base_name: str = "vectors") -> str:
    """
    Generate tenant-specific collection name.

    Format: {base_name}_{tenant_id}
    Example: vectors_acme8x

    Args:
        tenant_id: Tenant identifier
        base_name: Base collection name (default: "vectors")

    Returns:
        Tenant-specific collection name
    """
    return f"{base_name}_{tenant_id}"


async def get_async_qdrant_client() -> Any:
    """
    Lazy-load and return an async Qdrant client.

    This is the preferred client for all new code.

    Raises:
        RuntimeError: If QDRANT_URL is not configured or qdrant-client is unavailable.
    """
    global _async_client
    if not QDRANT_URL:
        raise RuntimeError("qdrant_unavailable: missing QDRANT_URL env")
    if _async_client is None:
        try:
            qdc_mod = importlib.import_module("qdrant_client")
            AsyncQdrantClient = getattr(qdc_mod, "AsyncQdrantClient")
            _async_client = AsyncQdrantClient(url=QDRANT_URL)
        except Exception as e:
            raise RuntimeError(f"qdrant_unavailable: {e}")
    return _async_client


async def ensure_qdrant_collection_async(client: Any, name: str, dim: int, tenant_id: str | None = None) -> str:
    """
    Ensure a Qdrant collection exists; create it if missing (asynchronous).

    Supports tenant isolation: if tenant_id is provided, uses tenant-specific collection name.

    This is the preferred function for all new code.

    Args:
        client: Async Qdrant client instance
        name: Base collection name
        dim: Vector dimension
        tenant_id: Optional tenant ID for isolation

    Returns:
        Actual collection name used (with tenant prefix if applicable)
    """
    # Generate tenant-specific collection name if tenant_id provided
    actual_collection = get_tenant_collection_name(tenant_id, name) if tenant_id else name

    try:
        models_mod = importlib.import_module("qdrant_client.models")
        Distance = getattr(models_mod, "Distance")
        VectorParams = getattr(models_mod, "VectorParams")
        await client.get_collection(actual_collection)
    except Exception:
        await client.recreate_collection(
            collection_name=actual_collection, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
        )

    return actual_collection


async def delete_tenant_collection_async(client: Any, tenant_id: str, base_name: str = "vectors") -> bool:
    """
    Delete a tenant's collection from Qdrant.

    Args:
        client: Async Qdrant client instance
        tenant_id: Tenant identifier
        base_name: Base collection name (default: "vectors")

    Returns:
        True if collection was deleted, False if it didn't exist
    """
    collection_name = get_tenant_collection_name(tenant_id, base_name)
    try:
        await client.delete_collection(collection_name)
        return True
    except Exception:
        return False


async def close_async_client() -> None:
    """Close the async Qdrant client and cleanup resources."""
    global _async_client
    if _async_client is not None:
        await _async_client.close()
        _async_client = None
