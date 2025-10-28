"""
Async Neo4j helper wrapper for admin-dashboard.

Provides minimal async driver helper: get driver, run read/write cypher, health and close.
"""

import importlib
import os
from typing import Any, Dict, List, Optional

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

_async_driver: Optional[Any] = None


async def get_async_neo4j_driver() -> Any:
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


async def run_read(driver: Any, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(cypher, **(params or {}))
        records = []
        async for rec in result:
            try:
                records.append(rec.data())
            except Exception:
                # fallback: to dict of values
                records.append({k: rec[k] for k in rec.keys()})
        return records


async def run_write(driver: Any, cypher: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    async with driver.session() as session:
        result = await session.run(cypher, **(params or {}))
        # In the async driver, result.consume() is a coroutine and must be awaited
        try:
            summary_obj = await result.consume()
        except Exception:
            # If consume fails, return an empty summary but don't crash
            return {"counters": {}}

        counters = {}
        if hasattr(summary_obj, "counters"):
            try:
                # counters is a object with attributes (nodes_created, relationships_created, etc.)
                counters = summary_obj.counters.__dict__
            except Exception:
                # fallback to empty dict
                counters = {}

        return {"counters": counters}


async def health(driver: Any) -> Dict[str, Any]:
    try:
        records = await run_read(driver, "RETURN 1 AS ok")
        return {"ok": True, "sample": records}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def close_driver() -> None:
    global _async_driver
    if _async_driver is not None:
        try:
            await _async_driver.close()
        finally:
            _async_driver = None
