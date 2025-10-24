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


@router.post("/index/chunks", response_model=IndexChunksResp)
async def index_chunks(
    req: IndexChunksReq,
    tenant_id: str = Depends(require_key),
    service: AsyncVectorService = Depends(get_async_vector_service),
) -> Dict[str, Any]:
    """Index text chunks into Qdrant vector database (asynchronous)."""
    try:
        return await service.index_chunks(req, tenant_id=tenant_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/index/chunks error")
        raise HTTPException(status_code=502, detail=f"index_error: {e}")


@router.post("/search", response_model=SearchResp)
async def search(
    req: SearchReq,
    tenant_id: str = Depends(require_key),
    service: AsyncVectorService = Depends(get_async_vector_service),
) -> Dict[str, Any]:
    """Vector similarity search (asynchronous)."""
    try:
        return await service.search(req, tenant_id=tenant_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/search error")
        # Qdrant collection 不存在時，回傳空 hits
        if "doesn't exist" in str(e) or "Not found: Collection" in str(e):
            return {"hits": [], "ok": True, "detail": "collection not found"}
        raise HTTPException(status_code=502, detail=f"search_error: {e}")


@router.post("/retrieve", response_model=RetrieveResp)
async def retrieve(
    req: RetrieveReq,
    tenant_id: str = Depends(require_key),
    service: AsyncVectorService = Depends(get_async_vector_service),
) -> Dict[str, Any]:
    """Hybrid retrieval: vector search + graph neighborhood expansion (asynchronous)."""
    try:
        return await service.retrieve(req, tenant_id=tenant_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/retrieve error")
        raise HTTPException(status_code=500, detail=f"retrieve_error: {e}")
