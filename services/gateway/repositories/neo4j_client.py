"""
Neo4j graph database driver wrapper.
"""

import importlib
from typing import Any

from ..config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER


def get_neo4j_driver() -> Any:
    """
    Lazy-load and return a Neo4j driver.
    Raises RuntimeError if NEO4J_URI or NEO4J_PASSWORD is not configured.
    """
    if not (NEO4J_URI and NEO4J_PASSWORD):
        raise RuntimeError("neo4j_unavailable: missing NEO4J_URI/NEO4J_PASSWORD env")
    try:
        neo4j_mod = importlib.import_module("neo4j")
        GraphDatabase = getattr(neo4j_mod, "GraphDatabase")
        return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    except Exception as e:
        raise RuntimeError(f"neo4j_unavailable: {e}")
