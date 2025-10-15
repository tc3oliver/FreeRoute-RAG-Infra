"""
Vector indexing and retrieval routers.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ..deps import require_key
from ..models import IndexChunksReq, IndexChunksResp, RetrieveReq, RetrieveResp, SearchReq, SearchResp
from ..services import VectorService

router = APIRouter(tags=["index", "search", "retrieve"])


def get_vector_service() -> VectorService:
    """Dependency injection for VectorService."""
    return VectorService()


@router.post("/index/chunks", dependencies=[Depends(require_key)], response_model=IndexChunksResp)
def index_chunks(req: IndexChunksReq, service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    """Index text chunks into Qdrant vector database."""
    try:
        return service.index_chunks(req)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/index/chunks error")
        raise HTTPException(status_code=502, detail=f"index_error: {e}")


@router.post("/search", dependencies=[Depends(require_key)], response_model=SearchResp)
def search(req: SearchReq, service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    """Vector similarity search."""
    try:
        return service.search(req)
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/search error")
        raise HTTPException(status_code=502, detail=f"search_error: {e}")


@router.post("/retrieve", dependencies=[Depends(require_key)], response_model=RetrieveResp)
def retrieve(req: RetrieveReq, service: VectorService = Depends(get_vector_service)) -> Dict[str, Any]:
    """Hybrid retrieval: vector search + graph neighborhood expansion."""
    try:
        return service.retrieve(req)
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/retrieve error")
        raise HTTPException(status_code=500, detail=f"retrieve_error: {e}")
