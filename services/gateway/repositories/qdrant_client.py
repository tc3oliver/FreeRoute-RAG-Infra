"""
Qdrant vector database client wrapper.
"""

import importlib
from typing import Any

from ..config import QDRANT_URL


def get_qdrant_client() -> Any:
    """
    Lazy-load and return a Qdrant client.
    Raises RuntimeError if QDRANT_URL is not configured or qdrant-client is unavailable.
    """
    if not QDRANT_URL:
        raise RuntimeError("qdrant_unavailable: missing QDRANT_URL env")
    try:
        qdc_mod = importlib.import_module("qdrant_client")
        QdrantClient = getattr(qdc_mod, "QdrantClient")
        return QdrantClient(url=QDRANT_URL)
    except Exception as e:
        raise RuntimeError(f"qdrant_unavailable: {e}")


def ensure_qdrant_collection(client: Any, name: str, dim: int) -> None:
    """
    Ensure a Qdrant collection exists; create it if missing.

    Args:
        client: Qdrant client instance
        name: Collection name
        dim: Vector dimension
    """
    try:
        models_mod = importlib.import_module("qdrant_client.models")
        Distance = getattr(models_mod, "Distance")
        VectorParams = getattr(models_mod, "VectorParams")
        client.get_collection(name)
    except Exception:
        client.recreate_collection(
            collection_name=name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
        )
