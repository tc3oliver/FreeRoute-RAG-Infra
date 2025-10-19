"""
Repositories layer: External system integrations and data access.
"""

from .litellm_client import close_async_client as close_async_litellm_client
from .litellm_client import get_async_litellm_client, get_litellm_client
from .neo4j_client import close_async_driver as close_async_neo4j_driver
from .neo4j_client import get_async_neo4j_driver, get_neo4j_driver
from .qdrant_client import close_async_client as close_async_qdrant_client
from .qdrant_client import (
    ensure_qdrant_collection,
    ensure_qdrant_collection_async,
    get_async_qdrant_client,
    get_qdrant_client,
)
from .reranker_client import call_reranker, call_reranker_async

__all__ = [
    # Synchronous clients (deprecated, kept for backward compatibility)
    "get_litellm_client",
    "get_qdrant_client",
    "ensure_qdrant_collection",
    "get_neo4j_driver",
    "call_reranker",
    # Asynchronous clients (preferred)
    "get_async_litellm_client",
    "get_async_qdrant_client",
    "ensure_qdrant_collection_async",
    "get_async_neo4j_driver",
    "call_reranker_async",
    # Cleanup functions
    "close_async_litellm_client",
    "close_async_qdrant_client",
    "close_async_neo4j_driver",
]
