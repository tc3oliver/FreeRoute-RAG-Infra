import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.db.models import AuditLog

from ..db import get_db
from ..schemas.graph import CypherRequest, CypherResult, IndexSpec
from ..utils.auth import require_admin_token
from ..utils.neo4j import get_async_neo4j_driver
from ..utils.neo4j import health as neo4j_health
from ..utils.neo4j import run_read, run_write

router = APIRouter(prefix="/admin/graph")


@router.get("/health")
async def graph_health(_: Any = Depends(require_admin_token)):
    driver = await get_async_neo4j_driver()
    try:
        return await neo4j_health(driver)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/records")
async def list_records(
    label: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _: Any = Depends(require_admin_token),
):
    """List nodes. Optional `label` filters nodes by label (alphanumeric+underscore only).
    Optional `tenant_id` filters nodes by tenant_id property.
    Returns id, labels, tenant_id (if present) and a short props_preview (first 200 chars).
    """
    # validate label to avoid injection
    if label and not re.match(r"^[A-Za-z0-9_]+$", label):
        raise HTTPException(status_code=400, detail="invalid label")

    params = {"limit": limit}
    # validate offset
    if offset < 0:
        raise HTTPException(status_code=400, detail="invalid offset")
    params["offset"] = offset
    where_clauses = []
    if tenant_id:
        where_clauses.append("n.tenant_id = $tenant_id")
        params["tenant_id"] = tenant_id
    if label:
        # use parameter membership check to avoid string interpolation
        where_clauses.append("$label IN labels(n)")
        params["label"] = label

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # Return props preview (first 200 chars) to avoid huge payloads
    cypher = (
        f"MATCH (n) {where_sql} RETURN id(n) AS id, labels(n) AS labels, n.tenant_id AS tenant_id, "
        "CASE WHEN n.props_json IS NOT NULL THEN substring(n.props_json, 0, 200) ELSE '' END AS props_preview SKIP $offset LIMIT $limit"
    )

    driver = await get_async_neo4j_driver()
    try:
        records = await run_read(driver, cypher, params)
        return {"records": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: int, db: AsyncSession = Depends(get_db), _: Any = Depends(require_admin_token)):
    """Delete a node by internal Neo4j id. Returns write summary."""
    driver = await get_async_neo4j_driver()
    try:
        cypher = "MATCH (n) WHERE id(n) = $id DETACH DELETE n"
        summary = await run_write(driver, cypher, {"id": int(node_id)})
        # audit
        audit = AuditLog(
            tenant_id=None, action="neo4j_delete_node", actor="admin-dashboard", details={"node_id": node_id}
        )
        db.add(audit)
        await db.commit()
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cypher")
async def run_cypher(payload: CypherRequest, db: AsyncSession = Depends(get_db), _: Any = Depends(require_admin_token)):
    driver = await get_async_neo4j_driver()
    try:
        if payload.read:
            records = await run_read(driver, payload.cypher, payload.params)
            return {"records": records}
        else:
            summary = await run_write(driver, payload.cypher, payload.params)
            # audit
            audit = AuditLog(
                tenant_id=None, action="neo4j_cypher_write", actor="admin-dashboard", details={"cypher": payload.cypher}
            )
            db.add(audit)
            await db.commit()
            return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index")
async def create_index(payload: IndexSpec, db: AsyncSession = Depends(get_db), _: Any = Depends(require_admin_token)):
    driver = await get_async_neo4j_driver()
    try:
        summary = await run_write(driver, payload.cypher)
        audit = AuditLog(
            tenant_id=None, action="neo4j_create_index", actor="admin-dashboard", details={"cypher": payload.cypher}
        )
        db.add(audit)
        await db.commit()
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/sample")
async def import_sample(db: AsyncSession = Depends(get_db), _: Any = Depends(require_admin_token)):
    """Create a tiny sample graph (two nodes and a relation) for smoke tests."""
    driver = await get_async_neo4j_driver()
    try:
        cypher = (
            "CREATE (a:Sample {name: 'Alice', tenant_id: 'admin'})\n"
            "CREATE (b:Sample {name: 'Bob', tenant_id: 'admin'})\n"
            "CREATE (a)-[:KNOWS]->(b)"
        )
        summary = await run_write(driver, cypher)
        audit = AuditLog(
            tenant_id=None, action="neo4j_import_sample", actor="admin-dashboard", details={"created": True}
        )
        db.add(audit)
        await db.commit()
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
