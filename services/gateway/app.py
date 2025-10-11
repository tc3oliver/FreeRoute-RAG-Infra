import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from jsonschema import Draft202012Validator, validate
from openai import OpenAI
from pydantic import BaseModel, Field

# 環境變數
LITELLM_BASE = os.environ.get("LITELLM_BASE", "http://litellm:4000/v1").rstrip("/")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "sk-admin")
RERANKER_URL = os.environ.get("RERANKER_URL", "http://reranker:80")

API_KEYS = {
    k.strip() for k in os.environ.get("API_GATEWAY_KEYS", "dev-key").split(",") if k.strip()
}
# 統一路徑：容器內掛載到 /app/schemas/graph_schema.json
GRAPH_SCHEMA_PATH = os.environ.get("GRAPH_SCHEMA_PATH", "/app/schemas/graph_schema.json")

# Graph 工作流程參數（可環境覆蓋）
GRAPH_MIN_NODES = int(os.environ.get("GRAPH_MIN_NODES", "1"))
GRAPH_MIN_EDGES = int(os.environ.get("GRAPH_MIN_EDGES", "1"))
GRAPH_ALLOW_EMPTY = os.environ.get("GRAPH_ALLOW_EMPTY", "false").lower() == "true"
GRAPH_MAX_ATTEMPTS = int(os.environ.get("GRAPH_MAX_ATTEMPTS", "2"))
DEFAULT_PROVIDER_CHAIN = ["graph-extractor", "graph-extractor-o1mini", "graph-extractor-gemini"]
ENV_PROVIDER_CHAIN = [
    x.strip()
    for x in os.environ.get("GRAPH_PROVIDER_CHAIN", ",".join(DEFAULT_PROVIDER_CHAIN)).split(",")
    if x.strip()
]
PROVIDER_CHAIN = ENV_PROVIDER_CHAIN if ENV_PROVIDER_CHAIN else DEFAULT_PROVIDER_CHAIN

APP_VERSION = os.environ.get("APP_VERSION", "v0.1.0")

client = OpenAI(base_url=LITELLM_BASE, api_key=LITELLM_KEY)


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

app = FastAPI(title="FreeRoute RAG Infra – API Gateway", version=APP_VERSION)


def require_key(
    x_api_key: Optional[str] = Header(None), authorization: Optional[str] = Header(None)
):
    token = None
    if x_api_key:
        token = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or token not in API_KEYS:
        raise HTTPException(status_code=401, detail="missing or invalid API key")
    return True


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


ENTRYPOINTS = {"rag-answer", "graph-extractor"}
DEFAULTS = {"chat": "rag-answer", "graph": "graph-extractor"}


def _normalize_model(model: Optional[str], kind="chat") -> str:
    if not model:
        return DEFAULTS[kind]
    m = model.strip()
    return m if m in ENTRYPOINTS else DEFAULTS[kind]


def _retry_once_429(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if "429" in str(e):
            time.sleep(0.3)
            return func(*args, **kwargs)
        raise


def _ensure_json_hint(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    def _has_json_word(msgs):
        for m in msgs:
            if isinstance(m, dict):
                c = m.get("content") or ""
                if isinstance(c, str) and ("json" in c.lower()):
                    return True
        return False

    if _has_json_word(messages):
        return messages
    hint = {"role": "system", "content": "請以 JSON 物件回覆（JSON only）。"}
    return [hint] + messages


def _extract_json_obj(text: str) -> Dict[str, Any]:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no_json_object_found")
    snippet = t[start : end + 1]
    try:
        return json.loads(snippet)
    except Exception:
        brace = 0
        for i, ch in enumerate(t[start:]):
            if ch == "{":
                brace += 1
            elif ch == "}":
                brace -= 1
                if brace == 0:
                    return json.loads(t[start : start + i + 1])
        raise ValueError("invalid_json_payload")


def _kvize(obj: Any) -> List[Dict[str, Any]]:
    if obj is None:
        return []
    if isinstance(obj, dict):
        out = []
        for k, v in obj.items():
            out.append({"key": str(k), "value": v})
        return out
    if isinstance(obj, list):
        good = []
        for it in obj:
            if isinstance(it, dict) and "key" in it and "value" in it:
                good.append({"key": str(it["key"]), "value": it["value"]})
        return good
    return []


def _dedup_merge_nodes(nodes):
    by_id = {}
    for n in nodes:
        k = n["id"]
        if k in by_id:
            seen = {
                (p["key"], json.dumps(p["value"], ensure_ascii=False)) for p in by_id[k]["props"]
            }
            for p in n["props"]:
                sig = (p["key"], json.dumps(p["value"], ensure_ascii=False))
                if sig not in seen:
                    by_id[k]["props"].append(p)
                    seen.add(sig)
        else:
            by_id[k] = n
    return list(by_id.values())


def _normalize_graph_shape(data: Any) -> Dict[str, Any]:
    nodes, edges = [], []

    if isinstance(data, list):
        raw_nodes = data
        raw_edges = []
    elif isinstance(data, dict):
        raw_nodes = data.get("nodes", [])
        raw_edges = data.get("edges", [])
        if not raw_nodes and isinstance(data.get("items"), list):
            raw_nodes = data["items"]
    else:
        raw_nodes, raw_edges = [], []

    if isinstance(raw_nodes, list):
        for n in raw_nodes:
            if not isinstance(n, dict):
                continue
            nid = n.get("id") or n.get("name") or n.get("node_id") or ""
            ntype = (
                n.get("type")
                or n.get("label")
                or (
                    n.get("labels")[0]
                    if isinstance(n.get("labels"), list) and n.get("labels")
                    else None
                )
                or "Entity"
            )
            props = _kvize(n.get("props"))
            if n.get("name") and not any(p.get("key") == "name" for p in props):
                props.append({"key": "name", "value": n["name"]})
            if isinstance(nid, str) and isinstance(ntype, str) and nid:
                nodes.append({"id": nid, "type": ntype, "props": props})

    if isinstance(raw_edges, list):
        for e in raw_edges:
            if not isinstance(e, dict):
                continue
            src = e.get("src") or e.get("source") or e.get("from") or ""
            dst = e.get("dst") or e.get("target") or e.get("to") or ""
            etype = e.get("type") or e.get("label") or "RELATED_TO"
            props = _kvize(e.get("props"))
            if all(isinstance(x, str) and x for x in (src, dst, etype)):
                edges.append({"src": src, "dst": dst, "type": etype, "props": props})

    nodes = _dedup_merge_nodes(nodes)
    return {"nodes": nodes, "edges": edges}


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


def _prune_graph(data):
    for n in data.get("nodes", []):
        n["props"] = [
            p
            for p in n.get("props", [])
            if isinstance(p.get("key"), str)
            and str(p["key"]).strip()
            and p.get("value") is not None
            and (not isinstance(p["value"], str) or p["value"].strip())
        ]
    for e in data.get("edges", []):
        e["props"] = [
            p
            for p in e.get("props", [])
            if isinstance(p.get("key"), str)
            and str(p["key"]).strip()
            and p.get("value") is not None
            and (not isinstance(p["value"], str) or p["value"].strip())
        ]
    return data


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/whoami", dependencies=[Depends(require_key)])
def whoami():
    return {
        "app_version": APP_VERSION,
        "litellm_base": LITELLM_BASE,
        "entrypoints": sorted(list(ENTRYPOINTS)),
        "json_mode_hint_injection": True,
        "graph_schema_path": GRAPH_SCHEMA_PATH,
        "schema_hash": GRAPH_SCHEMA_HASH,
        "graph_defaults": {
            "min_nodes": GRAPH_MIN_NODES,
            "min_edges": GRAPH_MIN_EDGES,
            "allow_empty": GRAPH_ALLOW_EMPTY,
            "max_attempts": GRAPH_MAX_ATTEMPTS,
            "provider_chain": PROVIDER_CHAIN,
        },
    }


@app.get("/version")
def version():
    return {"version": APP_VERSION}


@app.post("/chat", dependencies=[Depends(require_key)])
def chat(req: ChatReq, request: Request):
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
        raise HTTPException(status_code=502, detail=f"upstream_chat_error: {e}")

    out = resp.choices[0].message.content
    meta = {"model": resp.model}
    try:
        return {"ok": True, "data": json.loads(out), "meta": meta}
    except Exception:
        return {"ok": True, "data": out, "meta": meta}


@app.post("/embed", dependencies=[Depends(require_key)])
def embed(req: EmbedReq):
    try:
        r = client.embeddings.create(model="local-embed", input=req.texts)
        vecs = [d.embedding for d in r.data]
        return {"ok": True, "vectors": vecs, "dim": (len(vecs[0]) if vecs else 0)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"embed_error: {e}")


@app.post("/rerank", dependencies=[Depends(require_key)])
def rerank(req: RerankReq):
    try:
        r = requests.post(
            f"{RERANKER_URL}/rerank",
            json={"query": req.query, "documents": req.documents, "top_n": req.top_n},
            timeout=30,
        )
        r.raise_for_status()
        return {"ok": True, "results": r.json().get("results", [])}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"rerank_error: {e}")


@app.post("/graph/probe", dependencies=[Depends(require_key)])
def graph_probe(req: GraphProbeReq, request: Request):
    messages = req.messages or [
        {"role": "system", "content": "你是資訊抽取引擎，只輸出 JSON（若無法則輸出簡短文字）。"},
        {"role": "user", "content": "Bob 於2022年加入 Acme 擔任工程師；Acme 總部位於台北。"},
    ]
    if req.strict_json:
        has_json_word = any(
            isinstance(m, dict)
            and isinstance(m.get("content"), str)
            and ("json" in m["content"].lower())
            for m in messages
        )
        if not has_json_word:
            messages = [
                {"role": "system", "content": "請以 JSON 物件回覆（JSON only）。"}
            ] + messages

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
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_probe_error", "model": req.model, "message": str(e)},
        )


@app.post("/graph/extract", dependencies=[Depends(require_key)])
def graph_extract(req: GraphReq):
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
        print(f"[GraphExtract] trying provider: {provider}")
        for attempt in range(1, max_attempts + 1):
            mode = "strict" if attempt == 1 else "nudge"
            try:
                result = _retry_once_429(_call_once, provider, mode)
                data = result["data"]
                print(
                    f"[GraphExtract] attempt {attempt} with {provider} ({mode}) produced {len(data.get('nodes', []))} nodes and {len(data.get('edges', []))} edges"
                )

                if _is_single_error_node(data):
                    print(
                        f"[GraphExtract] attempt {attempt} with {provider} ({mode}) produced a single error node"
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
                print(f"[GraphExtract] attempt {attempt} with {provider} ({mode}) failed: {e}")
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

                FIX_SYS = (
                    "請把下列輸出修正成『合法 JSON』且符合 Schema；不得改動語意；只回傳 JSON 本體。"
                )
                FIX_USER = f"【schema】\n{json.dumps(GRAPH_JSON_SCHEMA, ensure_ascii=False)}\n\n【llm_output】\n{str(e)}"

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

        print(f"[GraphExtract] provider {provider} exhausted all attempts, moving to next if any")

    print(f"[GraphExtract] all providers exhausted, total attempts: {len(attempts)}")
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
