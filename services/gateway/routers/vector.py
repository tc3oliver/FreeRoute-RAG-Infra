"""
Vector indexing and retrieval routers.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ..deps import require_key
from ..models import IndexChunksReq, IndexChunksResp, RetrieveReq, RetrieveResp, SearchReq, SearchResp
from ..services import AsyncVectorService

router = APIRouter(tags=["index", "search", "retrieve"])


async def get_async_vector_service() -> AsyncVectorService:
    """Dependency injection for AsyncVectorService."""
    return AsyncVectorService()


@router.post("/index/chunks", dependencies=[Depends(require_key)], response_model=IndexChunksResp)
async def index_chunks(
    req: IndexChunksReq, service: AsyncVectorService = Depends(get_async_vector_service)
) -> Dict[str, Any]:
    """Index text chunks into Qdrant vector database (asynchronous)."""
    try:
        return await service.index_chunks(req)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/index/chunks error")
        raise HTTPException(status_code=502, detail=f"index_error: {e}")


@router.post("/search", dependencies=[Depends(require_key)], response_model=SearchResp)
async def search(req: SearchReq, service: AsyncVectorService = Depends(get_async_vector_service)) -> Dict[str, Any]:
    """Vector similarity search (asynchronous)."""
    try:
        return await service.search(req)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/search error")
        raise HTTPException(status_code=502, detail=f"search_error: {e}")


@router.post("/retrieve", dependencies=[Depends(require_key)], response_model=RetrieveResp)
async def retrieve(req: RetrieveReq, service: AsyncVectorService = Depends(get_async_vector_service)) -> Dict[str, Any]:
    """Hybrid retrieval: vector search + graph neighborhood expansion (asynchronous)."""
    try:
        return await service.retrieve(req)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/retrieve error")
        raise HTTPException(status_code=500, detail=f"retrieve_error: {e}")
