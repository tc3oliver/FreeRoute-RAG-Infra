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
from ..services import GraphService

router = APIRouter(prefix="/graph", tags=["graph"])


def get_graph_service() -> GraphService:
    """Dependency injection for GraphService."""
    return GraphService()


@router.post("/probe", dependencies=[Depends(require_key)], response_model=GraphProbeResp)
def graph_probe(
    req: GraphProbeReq, request: Request, service: GraphService = Depends(get_graph_service)
) -> Dict[str, Any]:
    """Test a provider's JSON/text generation capability."""
    try:
        return service.probe(req, request.client.host)
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/graph/probe upstream error")
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_probe_error", "model": req.model, "message": str(e)},
        )


@router.post("/extract", dependencies=[Depends(require_key)], response_model=GraphExtractResp)
def graph_extract(
    req: GraphReq, request: Request, service: GraphService = Depends(get_graph_service)
) -> Dict[str, Any]:
    """Extract graph data from text using multi-provider fallback."""
    try:
        return service.extract(req, request.client.host)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/graph/extract unexpected error")
        raise HTTPException(status_code=500, detail=f"internal_error: {e}")


@router.post("/upsert", dependencies=[Depends(require_key)], response_model=GraphUpsertResp)
def graph_upsert(req: GraphUpsertReq, service: GraphService = Depends(get_graph_service)) -> Dict[str, Any]:
    """Upsert graph nodes and edges into Neo4j."""
    try:
        return service.upsert(req)
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/graph/upsert neo4j error")
        raise HTTPException(status_code=502, detail=f"neo4j_error: {e}")


@router.post("/query", dependencies=[Depends(require_key)], response_model=GraphQueryResp)
def graph_query(req: GraphQueryReq, service: GraphService = Depends(get_graph_service)) -> Dict[str, Any]:
    """Execute a read-only Cypher query on Neo4j."""
    try:
        return service.query(req)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/graph/query neo4j error")
        raise HTTPException(status_code=502, detail=f"neo4j_error: {e}")
