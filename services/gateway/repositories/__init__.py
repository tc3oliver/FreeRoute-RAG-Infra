"""
Repositories layer: External system integrations and data access.
"""

# Use safe imports so app/module import doesn't fail if optional deps are missing in tests
try:  # LiteLLM
    from .litellm_client import close_async_client as close_async_litellm_client
    from .litellm_client import get_async_litellm_client
except Exception:  # pragma: no cover

    async def close_async_litellm_client() -> None:  # type: ignore
        return None

    def get_async_litellm_client():  # type: ignore
        raise RuntimeError("litellm_unavailable")


try:  # Neo4j
    from .neo4j_client import close_async_driver as close_async_neo4j_driver
    from .neo4j_client import delete_tenant_nodes_async, get_async_neo4j_driver
except Exception:  # pragma: no cover

    async def close_async_neo4j_driver() -> None:  # type: ignore
        return None

    def get_async_neo4j_driver():  # type: ignore
        raise RuntimeError("neo4j_unavailable")

    async def delete_tenant_nodes_async(*_args, **_kwargs) -> int:  # type: ignore
        return 0


try:  # Qdrant
    from .qdrant_client import close_async_client as close_async_qdrant_client
    from .qdrant_client import (
        delete_tenant_collection_async,
        ensure_qdrant_collection_async,
        get_async_qdrant_client,
        get_tenant_collection_name,
    )
except Exception:  # pragma: no cover

    async def close_async_qdrant_client() -> None:  # type: ignore
        return None

    async def ensure_qdrant_collection_async(*_args, **_kwargs) -> str:  # type: ignore
        return "default"

    def get_async_qdrant_client():  # type: ignore
        raise RuntimeError("qdrant_unavailable")

    def get_tenant_collection_name(*_args, **_kwargs) -> str:  # type: ignore
        return "default"

    async def delete_tenant_collection_async(*_args, **_kwargs) -> bool:  # type: ignore
        return False


try:
    from .reranker_client import call_reranker_async
except Exception:  # pragma: no cover

    async def call_reranker_async(*_args, **_kwargs):  # type: ignore
        raise RuntimeError("reranker_unavailable")


__all__ = [
    # Asynchronous clients (preferred)
    "get_async_litellm_client",
    "get_async_qdrant_client",
    "ensure_qdrant_collection_async",
    "get_tenant_collection_name",
    "delete_tenant_collection_async",
    "get_async_neo4j_driver",
    "delete_tenant_nodes_async",
    "call_reranker_async",
    # Cleanup functions
    "close_async_litellm_client",
    "close_async_qdrant_client",
    "close_async_neo4j_driver",
]
