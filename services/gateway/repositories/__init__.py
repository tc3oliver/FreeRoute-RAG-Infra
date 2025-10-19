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
    from .neo4j_client import get_async_neo4j_driver
except Exception:  # pragma: no cover

    async def close_async_neo4j_driver() -> None:  # type: ignore
        return None

    def get_async_neo4j_driver():  # type: ignore
        raise RuntimeError("neo4j_unavailable")


try:  # Qdrant
    from .qdrant_client import close_async_client as close_async_qdrant_client
    from .qdrant_client import ensure_qdrant_collection_async, get_async_qdrant_client
except Exception:  # pragma: no cover

    async def close_async_qdrant_client() -> None:  # type: ignore
        return None

    async def ensure_qdrant_collection_async(*_args, **_kwargs) -> None:  # type: ignore
        return None

    def get_async_qdrant_client():  # type: ignore
        raise RuntimeError("qdrant_unavailable")


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
    "get_async_neo4j_driver",
    "call_reranker_async",
    # Cleanup functions
    "close_async_litellm_client",
    "close_async_qdrant_client",
    "close_async_neo4j_driver",
]
