# === 標準函式庫 ===
import hashlib
import importlib
import json
import logging
import os
import time
import uuid
import uuid as uuidlib
from contextvars import ContextVar
from typing import Any, Dict, List, Optional, Tuple

# === 第三方套件 ===
import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from jsonschema import Draft202012Validator, validate
from openai import OpenAI
from pydantic import BaseModel, Field

# --- Local module imports (kept at top; no non-import code before this block) ---
from .deps import API_KEYS, require_key
from .middleware import METRICS_ENABLED as METRICS_ENABLED
from .middleware import RequestContextFilter, add_request_id, log_event, prometheus_middleware, request_ctx
from .models import (
    KV,
    ChatReq,
    ChatResp,
    ChunkItem,
    Citation,
    EmbedReq,
    EmbedResp,
    GraphData,
    GraphEdge,
    GraphExtractResp,
    GraphNode,
    GraphProbeReq,
    GraphProbeResp,
    GraphQueryReq,
    GraphQueryResp,
    GraphReq,
    GraphUpsertReq,
    GraphUpsertResp,
    HealthResp,
    IndexChunksReq,
    IndexChunksResp,
    RerankItem,
    RerankReq,
    RerankResp,
    RetrieveHit,
    RetrieveReq,
    RetrieveResp,
    SearchHit,
    SearchReq,
    SearchResp,
    Subgraph,
    SubgraphEdge,
    SubgraphNode,
    VersionResp,
    WhoAmIResp,
)
from .routers.meta import health as health
from .routers.meta import metrics as metrics
from .routers.meta import router as meta_router
from .routers.meta import version as version
from .routers.meta import whoami as whoami
from .utils import dedup_merge_nodes as _dedup_merge_nodes
from .utils import ensure_json_hint as _ensure_json_hint
from .utils import extract_json_obj as _extract_json_obj
from .utils import kvize as _kvize
from .utils import normalize_graph_shape as _normalize_graph_shape
from .utils import prune_graph as _prune_graph
from .utils import retry_once_429 as _retry_once_429
from .utils import sha1 as _sha1

# 新增：抽離的資料模型與工具函式

# === 環境變數與全域參數 ===
LITELLM_BASE = os.environ.get("LITELLM_BASE", "http://litellm:4000/v1").rstrip("/")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "sk-admin")
RERANKER_URL = os.environ.get("RERANKER_URL", "http://reranker:8080")
QDRANT_URL = os.environ.get("QDRANT_URL")  # e.g., http://qdrant:6333
NEO4J_URI = os.environ.get("NEO4J_URI")  # e.g., bolt://neo4j:7687
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")

# 統一路徑：容器內掛載到 /app/schemas/graph_schema.json
GRAPH_SCHEMA_PATH = os.environ.get("GRAPH_SCHEMA_PATH", "/app/schemas/graph_schema.json")


# Graph 工作流程參數（可環境覆蓋）
GRAPH_MIN_NODES = int(os.environ.get("GRAPH_MIN_NODES", "1"))
GRAPH_MIN_EDGES = int(os.environ.get("GRAPH_MIN_EDGES", "1"))
GRAPH_ALLOW_EMPTY = os.environ.get("GRAPH_ALLOW_EMPTY", "false").lower() == "true"
GRAPH_MAX_ATTEMPTS = int(os.environ.get("GRAPH_MAX_ATTEMPTS", "2"))
DEFAULT_PROVIDER_CHAIN = ["graph-extractor", "graph-extractor-o1mini", "graph-extractor-gemini"]
ENV_PROVIDER_CHAIN = [
    x.strip() for x in os.environ.get("GRAPH_PROVIDER_CHAIN", ",".join(DEFAULT_PROVIDER_CHAIN)).split(",") if x.strip()
]
PROVIDER_CHAIN = ENV_PROVIDER_CHAIN if ENV_PROVIDER_CHAIN else DEFAULT_PROVIDER_CHAIN

APP_VERSION = os.environ.get("APP_VERSION", "v0.1.0")


# === OpenAI 客戶端 ===
client = OpenAI(base_url=LITELLM_BASE, api_key=LITELLM_KEY)


## === 工具函式 ===
def _load_graph_schema(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise RuntimeError(f"[FATAL] graph_schema.json not found at: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        raise RuntimeError(f"[FATAL] graph_schema.json load failed: {e}")
    if not isinstance(schema, dict) or "type" not in schema:
        raise RuntimeError("[FATAL] graph_schema.json invalid: missing top-level 'type'")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as e:
        raise RuntimeError(f"[FATAL] graph_schema.json is not a valid JSON Schema: {e}")
    return schema


GRAPH_JSON_SCHEMA = _load_graph_schema(GRAPH_SCHEMA_PATH)
with open(GRAPH_SCHEMA_PATH, "rb") as _f:
    GRAPH_SCHEMA_HASH = hashlib.sha256(_f.read()).hexdigest()


# === FastAPI 應用 ===
app = FastAPI(title="FreeRoute RAG Infra – API Gateway", version=APP_VERSION)


# basic structured logging (可被 uvicorn 設定覆蓋)
logger = logging.getLogger("gateway")
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())


# === Middleware ===
app.middleware("http")(add_request_id)


app.middleware("http")(prometheus_middleware)


# === 請求上下文與日誌 ===
try:
    f = RequestContextFilter()
    logger.addFilter(f)
    for h in logger.handlers:
        try:
            h.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s [req:%(request_id)s] [ip:%(client_ip)s] [evt:%(event)s] [dur:%(duration_ms)dms] %(message)s"
                )
            )
        except Exception:
            pass
except Exception:
    pass


## require_key 已移至 services.gateway.deps 並於頂部匯入


# === 請求/回應資料模型 ===
## 已移至 services.gateway.models


# ---------- Response Models (keep existing fields; purely descriptive) ----------


## 已移至 services.gateway.models


# ========== Index/Search (Vector) 請求/回應模型 ==========
## 已移至 services.gateway.models


# ========== Graph Upsert/Query 請求/回應模型 ==========
## 已移至 services.gateway.models


# ========== Hybrid Retrieval 請求/回應模型 ==========
## 已移至 services.gateway.models


ENTRYPOINTS = {"rag-answer", "graph-extractor"}
DEFAULTS = {"chat": "rag-answer", "graph": "graph-extractor"}


def _normalize_model(model: Optional[str], kind: str = "chat") -> str:
    if not model:
        return DEFAULTS[kind]
    m = model.strip()
    return m if m in ENTRYPOINTS else DEFAULTS[kind]


def _is_single_error_node(d: Dict[str, Any]) -> bool:
    try:
        if not isinstance(d, dict):
            return False
        ns = d.get("nodes", [])
        es = d.get("edges", [])
        if isinstance(ns, list) and isinstance(es, list) and len(ns) == 1:
            n0 = ns[0]
            return isinstance(n0, dict) and n0.get("type") == "error"
        return False
    except Exception:
        return False


## 已移至 services.gateway.utils（以 _prune_graph 名稱 import）


# ========== 可選整合：Qdrant（lazy import） ==========
def _get_qdrant_client():
    if not QDRANT_URL:
        raise RuntimeError("qdrant_unavailable: missing QDRANT_URL env")
    try:
        qdc_mod = importlib.import_module("qdrant_client")
        QdrantClient = getattr(qdc_mod, "QdrantClient")
        return QdrantClient(url=QDRANT_URL)
    except Exception as e:
        raise RuntimeError(f"qdrant_unavailable: {e}")


def _ensure_qdrant_collection(client, name: str, dim: int) -> None:
    try:
        models_mod = importlib.import_module("qdrant_client.models")
        Distance = getattr(models_mod, "Distance")
        VectorParams = getattr(models_mod, "VectorParams")
        client.get_collection(name)
    except Exception:
        client.recreate_collection(
            collection_name=name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
        )


# ========== 可選整合：Neo4j（lazy import） ==========
def _get_neo4j_driver():
    if not (NEO4J_URI and NEO4J_PASSWORD):
        raise RuntimeError("neo4j_unavailable: missing NEO4J_URI/NEO4J_PASSWORD env")
    try:
        neo4j_mod = importlib.import_module("neo4j")
        GraphDatabase = getattr(neo4j_mod, "GraphDatabase")
        return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    except Exception as e:
        raise RuntimeError(f"neo4j_unavailable: {e}")


# === API 路由 ===
app.include_router(meta_router)
## metrics/health/version/whoami 已移至 routers.meta 並在頂部 re-export


# ========== 新增：Index/Vector 檢索 API ==========
@app.post("/index/chunks", dependencies=[Depends(require_key)], response_model=IndexChunksResp, tags=["index"])
def index_chunks(req: IndexChunksReq) -> Dict[str, Any]:
    if not req.chunks:
        raise HTTPException(status_code=400, detail="chunks must be non-empty")
    # 1) 取得向量
    texts = [c.text for c in req.chunks]
    try:
        emb = client.embeddings.create(model="local-embed", input=texts)
        vectors = [d.embedding for d in emb.data]
    except Exception as e:
        logger.exception("/index/chunks embed error")
        raise HTTPException(status_code=502, detail=f"embed_error: {e}")

    dim = len(vectors[0]) if vectors else 0
    # 2) 寫入 Qdrant
    try:
        qc = _get_qdrant_client()
        _ensure_qdrant_collection(qc, req.collection, dim)
        models_mod = importlib.import_module("qdrant_client.models")
        PointStruct = getattr(models_mod, "PointStruct")

        points = []
        for c, vec in zip(req.chunks, vectors):
            # Qdrant 只接受 UUID 或 uint 作為 id
            pid = None
            if c.chunk_id:
                try:
                    # 驗證是否為合法 UUID
                    pid = str(uuidlib.UUID(str(c.chunk_id)))
                except Exception:
                    pid = None
            if not pid:
                pid = str(uuidlib.uuid4())
            payload = {
                "doc_id": c.doc_id,
                "text": c.text,
                "metadata": c.metadata or {},
                "hash": _sha1(c.text),
            }
            points.append(PointStruct(id=pid, vector=vec, payload=payload))
        qc.upsert(collection_name=req.collection, points=points)
        return {"ok": True, "upserted": len(points), "dim": dim, "collection": req.collection}
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        logger.exception("/index/chunks qdrant error")
        raise HTTPException(status_code=502, detail=f"qdrant_error: {e}")


@app.post("/search", dependencies=[Depends(require_key)], response_model=SearchResp, tags=["search"])
def search(req: SearchReq) -> Dict[str, Any]:
    try:
        emb = client.embeddings.create(model="local-embed", input=[req.query])
        qvec = emb.data[0].embedding
    except Exception as e:
        logger.exception("/search embed error")
        raise HTTPException(status_code=502, detail=f"embed_error: {e}")

    try:
        qc = _get_qdrant_client()
        models_mod = importlib.import_module("qdrant_client.models")
        Filter = getattr(models_mod, "Filter")

        flt = None
        if req.filters:
            # 簡化：直接傳遞 dict 給 Filter.from_dict
            flt = Filter.from_dict(req.filters)
        results = qc.search(collection_name=req.collection, query_vector=qvec, limit=req.top_k, query_filter=flt)
        hits = []
        for r in results:
            hits.append({"id": getattr(r, "id", None), "score": r.score, "payload": r.payload or {}})
        return {"ok": True, "hits": hits}
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        logger.exception("/search qdrant error")
        raise HTTPException(status_code=502, detail=f"qdrant_error: {e}")


@app.post("/retrieve", dependencies=[Depends(require_key)], response_model=RetrieveResp, tags=["retrieve"])
def retrieve(req: RetrieveReq) -> Dict[str, Any]:
    """混合檢索：結合向量搜尋與圖譜鄰域展開"""
    start_time = time.time()

    # 1) 向量檢索
    vector_hits = []
    try:
        emb = client.embeddings.create(model="local-embed", input=[req.query])
        qvec = emb.data[0].embedding

        qc = _get_qdrant_client()
        models_mod = importlib.import_module("qdrant_client.models")
        Filter = getattr(models_mod, "Filter")

        flt = None
        if req.filters:
            flt = Filter.from_dict(req.filters)

        results = qc.search(collection_name=req.collection, query_vector=qvec, limit=req.top_k, query_filter=flt)

        for r in results:
            payload = r.payload or {}
            citation = Citation(source="vector", doc_id=payload.get("doc_id"), score=r.score)
            hit = RetrieveHit(
                text=payload.get("text", ""), metadata=payload.get("metadata", {}), citations=[citation], score=r.score
            )
            vector_hits.append(hit)

    except Exception:
        logger.exception("/retrieve vector search error")
        # 繼續執行，不因向量檢索失敗而中斷

    # 2) 圖譜檢索（根據 query 中的關鍵實體）
    subgraph_data = None
    if req.include_subgraph:
        try:
            driver = _get_neo4j_driver()

            # 簡單策略：查找名稱包含 query 關鍵字的節點及其鄰域
            query_keywords = [kw.strip() for kw in req.query.lower().split() if len(kw.strip()) > 2]

            with driver.session() as session:
                # 查找相關節點
                match_nodes = []
                for keyword in query_keywords[:3]:  # 限制關鍵字數量
                    rs = session.run(
                        """
                        MATCH (n)
                        WHERE toLower(n.id) CONTAINS $keyword
                           OR ANY(prop IN keys(n) WHERE toLower(toString(n[prop])) CONTAINS $keyword)
                        RETURN DISTINCT n.id as id, n.type as type, properties(n) as props
                        LIMIT 5
                    """,
                        keyword=keyword,
                    )
                    match_nodes.extend([record.data() for record in rs])

                # 去重
                seen_ids = set()
                unique_nodes = []
                for node in match_nodes:
                    if node["id"] not in seen_ids:
                        unique_nodes.append(node)
                        seen_ids.add(node["id"])

                # 擴展鄰域
                all_nodes = []
                all_edges = []

                for node in unique_nodes[:3]:  # 限制種子節點數量
                    node_id = node["id"]

                    # 獲取鄰域
                    rs = session.run(
                        f"""
                        MATCH (a {{id: $id}})-[r]-(b)
                        RETURN
                            a.id as src_id, a.type as src_type, properties(a) as src_props,
                            type(r) as rel_type, properties(r) as rel_props,
                            b.id as dst_id, b.type as dst_type, properties(b) as dst_props,
                            startNode(r).id = $id as is_outgoing
                        LIMIT {req.max_hops * 10}
                    """,
                        id=node_id,
                    )

                    for record in rs:
                        data = record.data()

                        # 添加節點
                        src_node = SubgraphNode(
                            id=data["src_id"], type=data["src_type"] or "Entity", props=data["src_props"] or {}
                        )
                        dst_node = SubgraphNode(
                            id=data["dst_id"], type=data["dst_type"] or "Entity", props=data["dst_props"] or {}
                        )

                        if src_node not in all_nodes:
                            all_nodes.append(src_node)
                        if dst_node not in all_nodes:
                            all_nodes.append(dst_node)

                        # 添加邊
                        if data["is_outgoing"]:
                            edge = SubgraphEdge(
                                src=data["src_id"],
                                dst=data["dst_id"],
                                type=data["rel_type"],
                                props=data["rel_props"] or {},
                            )
                        else:
                            edge = SubgraphEdge(
                                src=data["dst_id"],
                                dst=data["src_id"],
                                type=data["rel_type"],
                                props=data["rel_props"] or {},
                            )

                        if edge not in all_edges:
                            all_edges.append(edge)

                if all_nodes:
                    subgraph_data = Subgraph(nodes=all_nodes, edges=all_edges)

        except Exception:
            logger.exception("/retrieve graph expansion error")
            # 繼續執行，不因圖檢索失敗而中斷

    query_time = int((time.time() - start_time) * 1000)

    return {
        "ok": True,
        "hits": vector_hits,
        "subgraph": subgraph_data.dict() if subgraph_data else None,
        "query_time_ms": query_time,
    }


@app.post("/chat", dependencies=[Depends(require_key)], response_model=ChatResp, tags=["chat"])
def chat(req: ChatReq, request: Request) -> Dict[str, Any]:
    model = _normalize_model(req.model, kind="chat")
    messages = req.messages
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty array")

    extra: Dict[str, Any] = {}
    if req.json_mode:
        messages = _ensure_json_hint(messages)
        extra["response_format"] = {"type": "json_object"}

    def _call():
        return client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=req.temperature,
            extra_headers={"X-Client-IP": request.client.host},
            **extra,
        )

    try:
        resp = _retry_once_429(_call)
    except Exception as e:
        logger.exception("/chat upstream error")
        raise HTTPException(status_code=502, detail=f"upstream_chat_error: {e}")

    out = resp.choices[0].message.content
    meta = {"model": resp.model}
    try:
        return {"ok": True, "data": json.loads(out), "meta": meta}
    except Exception:
        return {"ok": True, "data": out, "meta": meta}


@app.post("/embed", dependencies=[Depends(require_key)], response_model=EmbedResp, tags=["embed"])
def embed(req: EmbedReq) -> Dict[str, Any]:
    try:
        r = client.embeddings.create(model="local-embed", input=req.texts)
        vecs = [d.embedding for d in r.data]
        return {"ok": True, "vectors": vecs, "dim": (len(vecs[0]) if vecs else 0)}
    except Exception as e:
        logger.exception("/embed upstream error")
        raise HTTPException(status_code=502, detail=f"embed_error: {e}")


@app.post("/rerank", dependencies=[Depends(require_key)], response_model=RerankResp, tags=["rerank"])
def rerank(req: RerankReq) -> Dict[str, Any]:
    try:
        r = requests.post(
            f"{RERANKER_URL}/rerank",
            json={"query": req.query, "documents": req.documents, "top_n": req.top_n},
            timeout=30,
        )
        r.raise_for_status()
        return {"ok": True, "results": r.json().get("results", [])}
    except Exception as e:
        logger.exception("/rerank upstream error")
        raise HTTPException(status_code=502, detail=f"rerank_error: {e}")


# ========== 新增：Graph Upsert/Query API ==========
@app.post("/graph/upsert", dependencies=[Depends(require_key)], response_model=GraphUpsertResp, tags=["graph"])
def graph_upsert(req: GraphUpsertReq) -> Dict[str, Any]:
    data = req.data
    try:
        driver = _get_neo4j_driver()
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))

    def _props_json(props: List[KV]) -> str:
        return json.dumps([{"key": p.key, "value": p.value} for p in (props or [])], ensure_ascii=False)

    n_count = 0
    e_count = 0
    try:
        with driver.session() as session:
            # upsert nodes
            for n in data.nodes:
                session.run(
                    """
                    MERGE (x:Entity:`%s` {id: $id})
                    ON CREATE SET x.created_at = timestamp()
                    SET x.updated_at = timestamp(), x.type = $type, x.props_json = $props
                    """
                    % n.type,
                    id=n.id,
                    type=n.type,
                    props=_props_json(n.props),
                )
                n_count += 1
            # upsert edges
            for e in data.edges:
                session.run(
                    """
                    MATCH (a {id: $src})
                    MATCH (b {id: $dst})
                    MERGE (a)-[r:`%s`]->(b)
                    ON CREATE SET r.created_at = timestamp()
                    SET r.updated_at = timestamp(), r.type = $type, r.props_json = $props
                    """
                    % e.type,
                    src=e.src,
                    dst=e.dst,
                    type=e.type,
                    props=_props_json(e.props),
                )
                e_count += 1
        return {"ok": True, "nodes": n_count, "edges": e_count}
    except Exception as e:
        logger.exception("/graph/upsert neo4j error")
        raise HTTPException(status_code=502, detail=f"neo4j_error: {e}")


@app.post("/graph/query", dependencies=[Depends(require_key)], response_model=GraphQueryResp, tags=["graph"])
def graph_query(req: GraphQueryReq) -> Dict[str, Any]:
    q = (req.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query is required")
    # 簡單安全守門：拒絕資料修改關鍵字（非萬全，實務應做白名單）
    lowered = q.lower()
    forbidden = ["delete ", "remove ", "drop ", "create ", "set ", "merge ", "load ", "call db."]
    if any(tok in lowered for tok in forbidden):
        raise HTTPException(status_code=400, detail="write_or_unsafe_query_not_allowed")
    try:
        driver = _get_neo4j_driver()
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    try:
        with driver.session() as session:
            rs = session.run(q, **(req.params or {}))
            records = [r.data() for r in rs]
        return {"ok": True, "records": records}
    except Exception as e:
        logger.exception("/graph/query neo4j error")
        raise HTTPException(status_code=502, detail=f"neo4j_error: {e}")


@app.post(
    "/graph/probe",
    dependencies=[Depends(require_key)],
    response_model=GraphProbeResp,
    tags=["graph"],
)
def graph_probe(req: GraphProbeReq, request: Request) -> Dict[str, Any]:
    messages = req.messages or [
        {"role": "system", "content": "你是資訊抽取引擎，只輸出 JSON（若無法則輸出簡短文字）。"},
        {"role": "user", "content": "Bob 於2022年加入 Acme 擔任工程師；Acme 總部位於台北。"},
    ]
    if req.strict_json:
        has_json_word = any(
            isinstance(m, dict) and isinstance(m.get("content"), str) and ("json" in m["content"].lower())
            for m in messages
        )
        if not has_json_word:
            messages = [{"role": "system", "content": "請以 JSON 物件回覆（JSON only）。"}] + messages

    extra = {}
    if req.strict_json:
        extra["response_format"] = {"type": "json_object"}

    def _call():
        return client.chat.completions.create(
            model=req.model,
            messages=messages,
            temperature=req.temperature,
            timeout=req.timeout,
            extra_headers={"X-Client-IP": request.client.host},
            **extra,
        )

    try:
        resp = _retry_once_429(_call)
        txt = resp.choices[0].message.content or ""
        provider = resp.model
        if req.strict_json:
            try:
                data = json.loads(txt)
                if isinstance(data, dict):
                    return {"ok": True, "mode": "json", "data": data, "provider": provider}
                return {
                    "ok": False,
                    "mode": "json",
                    "error": "JSON not an object",
                    "provider": provider,
                    "raw": txt,
                }
            except Exception as je:
                return {
                    "ok": False,
                    "mode": "json",
                    "error": f"json_parse_error: {je}",
                    "provider": provider,
                    "raw": txt,
                }
        else:
            return {"ok": True, "mode": "text", "text": txt, "provider": provider}
    except Exception as e:
        logger.exception("/graph/probe upstream error")
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_probe_error", "model": req.model, "message": str(e)},
        )


@app.post(
    "/graph/extract",
    dependencies=[Depends(require_key)],
    response_model=GraphExtractResp,
    tags=["graph"],
)
def graph_extract(req: GraphReq, request: Request) -> Dict[str, Any]:
    min_nodes = int(req.min_nodes) if req.min_nodes is not None else GRAPH_MIN_NODES
    min_edges = int(req.min_edges) if req.min_edges is not None else GRAPH_MIN_EDGES
    allow_empty = bool(req.allow_empty) if req.allow_empty is not None else GRAPH_ALLOW_EMPTY
    max_attempts = int(req.max_attempts) if req.max_attempts is not None else GRAPH_MAX_ATTEMPTS
    provider_chain = req.provider_chain if req.provider_chain else PROVIDER_CHAIN

    if not req.context or not isinstance(req.context, str) or not req.context.strip():
        raise HTTPException(status_code=400, detail="context must be a non-empty string")

    SYS_BASE = (
        "你是資訊抽取引擎，將中文文本轉為圖譜資料（nodes/edges）。"
        "規則：僅根據【context】抽取，不得捏造；每個節點/關係需附 props（key/value 列表）。"
        "若資訊不足，可輸出低置信候選，並以 {'key':'low_confidence','value':true} 標記。"
        "必須輸出至少一條關係（例如『就職於/創立/位於』等）。"
        "只輸出 JSON，並嚴格符合系統 Schema。"
    )
    USER_TMPL = (
        "【context】\n{ctx}\n\n"
        "【任務】抽取 nodes/edges，並盡量補充 props（日期/金額/地點/職稱/URL 等）。\n"
        "建議關係類型示例：\n"
        "- EMPLOYED_AT: props 包含 role（職稱）、start_date（起始時間）、location（地點）\n"
        "- FOUNDED_BY: props 可含 year（年份）\n"
        "- HEADQUARTERED_IN: props 可含 city（城市）\n"
        "禁止輸出非 JSON、禁止空白字串、禁止 Markdown。"
    )

    def _call_once(entrypoint: str, mode: str) -> Dict[str, Any]:
        sys_prompt = SYS_BASE
        if mode == "strict":
            sys_prompt += " 回覆不得回傳完全空陣列。"
        elif mode == "nudge":
            sys_prompt += " 若資訊不足，請輸出低置信候選並以 low_confidence=true 標記。"

        user_msg = USER_TMPL.format(ctx=req.context)

        rf = {"type": "json_object"}
        if entrypoint == "graph-extractor-gemini":
            rf = None

        resp = client.chat.completions.create(
            model=entrypoint,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            **({"response_format": rf} if rf else {}),
        )

        raw = resp.choices[0].message.content or ""
        try:
            obj = json.loads(raw)
        except Exception:
            obj = _extract_json_obj(raw)

        data = _normalize_graph_shape(obj)

        if req.strict:
            data = _prune_graph(data)
            validate(instance=data, schema=GRAPH_JSON_SCHEMA)

        if os.environ.get("DEBUG_GRAPH", "false").lower() == "true":
            print(
                f"[GraphExtract] normalized data: nodes={len(data.get('nodes', []))}, edges={len(data.get('edges', []))}"
            )

        return {"data": data, "provider": resp.model, "raw": raw}

    attempts: List[Dict[str, Any]] = []

    for provider in provider_chain:
        # middleware already populated request_ctx; add attempt-level event
        log_event("trying provider", event="graph.extract.try", provider=provider)
        for attempt in range(1, max_attempts + 1):
            mode = "strict" if attempt == 1 else "nudge"
            try:
                result = _retry_once_429(_call_once, provider, mode)
                data = result["data"]
                log_event(
                    "attempt finished",
                    event="graph.extract.attempt",
                    attempt=attempt,
                    provider=provider,
                    mode=mode,
                    nodes=len(data.get("nodes", [])),
                    edges=len(data.get("edges", [])),
                )

                if _is_single_error_node(data):
                    log_event(
                        "single error node produced",
                        event="graph.extract.error_node",
                        attempt=attempt,
                        provider=provider,
                        mode=mode,
                        level=logging.WARNING,
                    )
                    attempts.append(
                        {
                            "provider": result["provider"],
                            "attempt": attempt,
                            "mode": mode,
                            "reason": "single_error_node",
                        }
                    )
                    continue

                nodes = data.get("nodes", []) if isinstance(data, dict) else []
                edges = data.get("edges", []) if isinstance(data, dict) else []

                if allow_empty or (len(nodes) >= min_nodes and len(edges) >= min_edges):
                    return {
                        "ok": True,
                        "data": data,
                        "provider": result["provider"],
                        "schema_hash": GRAPH_SCHEMA_HASH,
                    }

                attempts.append(
                    {
                        "provider": result["provider"],
                        "attempt": attempt,
                        "mode": mode,
                        "reason": f"below_threshold (nodes={len(nodes)}, edges={len(edges)})",
                    }
                )

            except Exception as e:
                log_event(
                    "attempt failed",
                    event="graph.extract.failed",
                    attempt=attempt,
                    provider=provider,
                    mode=mode,
                    error=str(e),
                    level=logging.WARNING,
                )
                if not req.repair_if_invalid:
                    attempts.append(
                        {
                            "provider": provider,
                            "attempt": attempt,
                            "mode": mode,
                            "error": f"{type(e).__name__}: {e}",
                        }
                    )
                    continue

                FIX_SYS = "請把下列輸出修正成『合法 JSON』且符合 Schema；不得改動語意；只回傳 JSON 本體。"
                FIX_USER = (
                    f"【schema】\n{json.dumps(GRAPH_JSON_SCHEMA, ensure_ascii=False)}\n\n【llm_output】\n{str(e)}"
                )

                try:
                    resp2 = client.chat.completions.create(
                        model=provider,
                        messages=[
                            {"role": "system", "content": FIX_SYS},
                            {"role": "user", "content": FIX_USER},
                        ],
                        temperature=0.0,
                    )
                    fixed = resp2.choices[0].message.content or ""
                    try:
                        data2 = json.loads(fixed)
                    except Exception:
                        data2 = _extract_json_obj(fixed)

                    if req.strict:
                        validate(instance=data2, schema=GRAPH_JSON_SCHEMA)

                    if _is_single_error_node(data2):
                        attempts.append(
                            {
                                "provider": resp2.model,
                                "attempt": f"{attempt} (repair)",
                                "mode": mode,
                                "reason": "single_error_node",
                            }
                        )
                        continue

                    n2 = len(data2.get("nodes", [])) if isinstance(data2, dict) else 0
                    e2 = len(data2.get("edges", [])) if isinstance(data2, dict) else 0
                    if allow_empty or (n2 >= min_nodes and e2 >= min_edges):
                        return {
                            "ok": True,
                            "data": data2,
                            "provider": resp2.model,
                            "schema_hash": GRAPH_SCHEMA_HASH,
                        }

                    attempts.append(
                        {
                            "provider": resp2.model,
                            "attempt": f"{attempt} (repair)",
                            "mode": mode,
                            "reason": f"below_threshold (nodes={n2}, edges={e2})",
                        }
                    )

                except Exception as e2:
                    attempts.append(
                        {
                            "provider": provider,
                            "attempt": f"{attempt} (repair)",
                            "mode": mode,
                            "error": f"{type(e2).__name__}: {e2}",
                        }
                    )
        log_event(
            "provider exhausted",
            event="graph.extract.provider_exhausted",
            provider=provider,
            level=logging.INFO,
        )

    log_event(
        "all providers exhausted",
        event="graph.extract.exhausted",
        attempts=len(attempts),
        level=logging.ERROR,
    )
    raise HTTPException(
        status_code=422,
        detail={
            "error": "graph_extraction_failed",
            "message": "no provider produced acceptable output",
            "min_nodes": min_nodes,
            "min_edges": min_edges,
            "allow_empty": allow_empty,
            "max_attempts": max_attempts,
            "provider_chain": provider_chain,
            "attempts": attempts[:50],
            "schema_hash": GRAPH_SCHEMA_HASH,
        },
    )
