"""
資料刪除 API 路由（多租戶安全）
"""

from fastapi import APIRouter, Depends, HTTPException

from ..deps import require_key
from ..models_delete import DeleteGraphReq, DeleteResp, DeleteVectorReq
from ..services.async_graph_service import AsyncGraphService
from ..services.async_vector_service import AsyncVectorService

router = APIRouter(tags=["delete"])


async def get_async_vector_service() -> AsyncVectorService:
    return AsyncVectorService()


async def get_async_graph_service() -> AsyncGraphService:
    return AsyncGraphService()


@router.post("/delete/vector", response_model=DeleteResp)
async def delete_vector(
    req: DeleteVectorReq,
    tenant_id: str = Depends(require_key),
    service: AsyncVectorService = Depends(get_async_vector_service),
) -> DeleteResp:
    try:
        deleted = await service.delete(req, tenant_id=tenant_id)
        return DeleteResp(ok=True, deleted=deleted)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"delete_vector_error: {e}")


@router.post("/delete/graph", response_model=DeleteResp)
async def delete_graph(
    req: DeleteGraphReq,
    tenant_id: str = Depends(require_key),
    service: AsyncGraphService = Depends(get_async_graph_service),
) -> DeleteResp:
    try:
        deleted = await service.delete(req, tenant_id=tenant_id)
        return DeleteResp(ok=True, deleted=deleted)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"delete_graph_error: {e}")
