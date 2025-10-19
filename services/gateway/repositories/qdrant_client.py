"""
Qdrant vector database client wrapper.
"""

import importlib
from typing import Any

from ..config import QDRANT_URL

_async_client: Any = None


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


async def ensure_qdrant_collection_async(client: Any, name: str, dim: int) -> None:
    """
    Ensure a Qdrant collection exists; create it if missing (asynchronous).

    This is the preferred function for all new code.

    Args:
        client: Async Qdrant client instance
        name: Collection name
        dim: Vector dimension
    """
    try:
        models_mod = importlib.import_module("qdrant_client.models")
        Distance = getattr(models_mod, "Distance")
        VectorParams = getattr(models_mod, "VectorParams")
        await client.get_collection(name)
    except Exception:
        await client.recreate_collection(
            collection_name=name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
        )


async def close_async_client() -> None:
    """Close the async Qdrant client and cleanup resources."""
    global _async_client
    if _async_client is not None:
        await _async_client.close()
        _async_client = None
