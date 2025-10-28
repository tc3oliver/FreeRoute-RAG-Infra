from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CollectionSpec(BaseModel):
    name: str
    vector_size: int = Field(..., alias="vector_size")
    distance: Optional[str] = "Cosine"
    hnsw_config: Optional[Dict[str, Any]] = None


class UpsertPoint(BaseModel):
    id: Optional[str]
    vector: List[float]
    payload: Optional[Dict[str, Any]] = None


class UpsertRequest(BaseModel):
    points: List[UpsertPoint]


class SearchRequest(BaseModel):
    vector: List[float]
    top_k: int = 10
    with_payload: bool = True


class SnapshotResponse(BaseModel):
    snapshot_id: Optional[str]
    info: Optional[Dict[str, Any]] = None
