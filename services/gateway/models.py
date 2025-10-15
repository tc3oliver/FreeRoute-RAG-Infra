from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ---------- Request Models ----------


class ChatReq(BaseModel):
    messages: List[Dict[str, str]] = Field(..., description="OpenAI chat messages")
    model: Optional[str] = Field(None, description="建議留空或使用入口名")
    temperature: float = 0.2
    json_mode: bool = False


class EmbedReq(BaseModel):
    texts: List[str]


class RerankReq(BaseModel):
    query: str
    documents: List[str]
    top_n: int = 6


class GraphReq(BaseModel):
    context: str
    strict: bool = True
    repair_if_invalid: bool = True
    min_nodes: Optional[int] = None
    min_edges: Optional[int] = None
    allow_empty: Optional[bool] = None
    max_attempts: Optional[int] = None
    provider_chain: Optional[List[str]] = None


class GraphProbeReq(BaseModel):
    model: str = Field(..., description="入口名或真實供應商名；建議用入口名 e.g. graph-extractor")
    strict_json: bool = False
    temperature: float = 0.0
    timeout: int = 60
    messages: Optional[List[Dict[str, str]]] = None


# ========== Index/Search (Vector) 請求/回應模型 ==========
class ChunkItem(BaseModel):
    doc_id: str
    text: str
    chunk_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class IndexChunksReq(BaseModel):
    chunks: List[ChunkItem]
    collection: str = Field(default="chunks", description="Qdrant collection name")


class SearchReq(BaseModel):
    query: str
    top_k: int = 5
    collection: str = "chunks"
    filters: Optional[Dict[str, Any]] = None


class GraphUpsertReq(BaseModel):
    data: "GraphData"  # Forward ref, defined below


class GraphQueryReq(BaseModel):
    query: str
    params: Optional[Dict[str, Any]] = None


class RetrieveReq(BaseModel):
    query: str
    top_k: int = 5
    collection: str = "chunks"
    include_subgraph: bool = True
    max_hops: int = 1
    filters: Optional[Dict[str, Any]] = None


# ---------- Response Models ----------


class HealthResp(BaseModel):
    ok: bool


class VersionResp(BaseModel):
    version: str


class WhoAmIResp(BaseModel):
    app_version: str
    litellm_base: str
    entrypoints: List[str]
    json_mode_hint_injection: bool
    graph_schema_path: str
    schema_hash: str
    graph_defaults: Dict[str, Any]


class EmbedResp(BaseModel):
    ok: bool
    vectors: List[List[float]]
    dim: int


class RerankItem(BaseModel):
    index: int
    score: float
    text: Optional[str] = None


class RerankResp(BaseModel):
    ok: bool
    results: List[RerankItem]


class ChatResp(BaseModel):
    ok: bool
    data: Any
    meta: Dict[str, Any]


class KV(BaseModel):
    key: str
    value: Any


class GraphNode(BaseModel):
    id: str
    type: str
    props: List["KV"]


class GraphEdge(BaseModel):
    src: str
    dst: str
    type: str
    props: List["KV"]


class GraphData(BaseModel):
    nodes: List["GraphNode"]
    edges: List["GraphEdge"]


class GraphExtractResp(BaseModel):
    ok: bool
    data: "GraphData"
    provider: str
    schema_hash: str


class GraphProbeResp(BaseModel):
    ok: bool
    mode: str
    provider: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    text: Optional[str] = None
    error: Optional[str] = None
    raw: Optional[str] = None


class IndexChunksResp(BaseModel):
    ok: bool
    upserted: int
    dim: int
    collection: str


class SearchHit(BaseModel):
    id: Any
    score: float
    payload: Dict[str, Any]


class SearchResp(BaseModel):
    ok: bool
    hits: List[SearchHit]


class GraphUpsertResp(BaseModel):
    ok: bool
    nodes: int
    edges: int


class GraphQueryResp(BaseModel):
    ok: bool
    records: List[Dict[str, Any]]


class Citation(BaseModel):
    source: str  # "vector" | "graph" | "hybrid"
    doc_id: Optional[str] = None
    chunk_id: Optional[str] = None
    node_id: Optional[str] = None
    edge_type: Optional[str] = None
    score: Optional[float] = None


class RetrieveHit(BaseModel):
    text: str
    metadata: Dict[str, Any]
    citations: List[Citation]
    score: Optional[float] = None


class SubgraphNode(BaseModel):
    id: str
    type: str
    props: Dict[str, Any]


class SubgraphEdge(BaseModel):
    src: str
    dst: str
    type: str
    props: Dict[str, Any]


class Subgraph(BaseModel):
    nodes: List[SubgraphNode]
    edges: List[SubgraphEdge]


class RetrieveResp(BaseModel):
    ok: bool
    hits: List[RetrieveHit]
    subgraph: Optional[Subgraph] = None
    query_time_ms: int


# Resolve forward refs (Pydantic V2 compatible)
GraphData.model_rebuild()
GraphNode.model_rebuild()
GraphEdge.model_rebuild()
GraphExtractResp.model_rebuild()
GraphUpsertReq.model_rebuild()
