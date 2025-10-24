from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DeleteVectorReq(BaseModel):
    collection: str = Field(..., description="Qdrant collection name")
    doc_id: Optional[str] = Field(None, description="指定 doc_id 則只刪單一文件，否則刪整個 collection")
    tenant_id: Optional[str] = Field(None, description="多租戶隔離")


class DeleteGraphReq(BaseModel):
    doc_id: Optional[str] = Field(None, description="指定 doc_id 則只刪單一文件相關圖譜，否則刪整個 tenant 的圖")
    tenant_id: Optional[str] = Field(None, description="多租戶隔離")


class DeleteResp(BaseModel):
    ok: bool
    deleted: int
    detail: Optional[str] = None
    errors: Optional[List[Dict[str, Any]]] = None
