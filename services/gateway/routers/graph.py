"""
Graph extraction and query routers.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ..deps import require_key
from ..models import (
    GraphExtractResp,
    GraphProbeReq,
    GraphProbeResp,
    GraphQueryReq,
    GraphQueryResp,
    GraphReq,
    GraphUpsertReq,
    GraphUpsertResp,
)
from ..services import AsyncGraphService

router = APIRouter(prefix="/graph", tags=["graph"])


async def get_async_graph_service() -> AsyncGraphService:
    """Dependency injection for AsyncGraphService."""
    return AsyncGraphService()


@router.post("/probe", response_model=GraphProbeResp)
async def graph_probe(
    req: GraphProbeReq,
    request: Request,
    tenant_id: str = Depends(require_key),
    service: AsyncGraphService = Depends(get_async_graph_service),
) -> Dict[str, Any]:
    """Test a provider's JSON/text generation capability (asynchronous)."""
    try:
        return await service.probe(req, request.client.host)
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/graph/probe upstream error")
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_probe_error", "model": req.model, "message": str(e)},
        )


@router.post("/extract", response_model=GraphExtractResp)
async def graph_extract(
    req: GraphReq,
    request: Request,
    tenant_id: str = Depends(require_key),
    service: AsyncGraphService = Depends(get_async_graph_service),
) -> Dict[str, Any]:
    """Extract graph data from text using parallel provider attempts (asynchronous)."""
    try:
        return await service.extract(req, request.client.host, tenant_id=tenant_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/graph/extract unexpected error")
        raise HTTPException(status_code=500, detail=f"internal_error: {e}")


@router.post("/upsert", response_model=GraphUpsertResp)
async def graph_upsert(
    req: GraphUpsertReq,
    tenant_id: str = Depends(require_key),
    service: AsyncGraphService = Depends(get_async_graph_service),
) -> Dict[str, Any]:
    """Upsert graph nodes and edges into Neo4j (asynchronous)."""
    try:
        return await service.upsert(req, tenant_id=tenant_id)
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/graph/upsert neo4j error")
        raise HTTPException(status_code=502, detail=f"neo4j_error: {e}")


@router.post("/query", response_model=GraphQueryResp)
async def graph_query(
    req: GraphQueryReq,
    tenant_id: str = Depends(require_key),
    service: AsyncGraphService = Depends(get_async_graph_service),
) -> Dict[str, Any]:
    """Execute a read-only Cypher query on Neo4j (asynchronous)."""
    try:
        return await service.query(req, tenant_id=tenant_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/graph/query neo4j error")
        raise HTTPException(status_code=502, detail=f"neo4j_error: {e}")
