"""
Neo4j graph database driver wrapper.
"""

import importlib
from typing import Any

from ..config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

# Singleton instances
_sync_driver: Any = None
_async_driver: Any = None


def get_neo4j_driver() -> Any:
    """
    Lazy-load and return a Neo4j driver (synchronous).

    DEPRECATED: Use get_async_neo4j_driver() for async operations.
    This function is kept for backward compatibility during migration.

    Raises:
        RuntimeError: If NEO4J_URI or NEO4J_PASSWORD is not configured.
    """
    global _sync_driver
    if not (NEO4J_URI and NEO4J_PASSWORD):
        raise RuntimeError("neo4j_unavailable: missing NEO4J_URI/NEO4J_PASSWORD env")
    if _sync_driver is None:
        try:
            neo4j_mod = importlib.import_module("neo4j")
            GraphDatabase = getattr(neo4j_mod, "GraphDatabase")
            _sync_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        except Exception as e:
            raise RuntimeError(f"neo4j_unavailable: {e}")
    return _sync_driver


async def get_async_neo4j_driver() -> Any:
    """
    Lazy-load and return an async Neo4j driver.

    This is the preferred driver for all new code.

    Raises:
        RuntimeError: If NEO4J_URI or NEO4J_PASSWORD is not configured.
    """
    global _async_driver
    if not (NEO4J_URI and NEO4J_PASSWORD):
        raise RuntimeError("neo4j_unavailable: missing NEO4J_URI/NEO4J_PASSWORD env")
    if _async_driver is None:
        try:
            neo4j_mod = importlib.import_module("neo4j")
            AsyncGraphDatabase = getattr(neo4j_mod, "AsyncGraphDatabase")
            _async_driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        except Exception as e:
            raise RuntimeError(f"neo4j_unavailable: {e}")
    return _async_driver


async def close_async_driver() -> None:
    """Close the async Neo4j driver and cleanup resources."""
    global _async_driver
    if _async_driver is not None:
        await _async_driver.close()
        _async_driver = None
