import asyncio
import hashlib
import json
import os
import time
from typing import Any, Awaitable, Callable, Dict, List, TypeVar

T = TypeVar("T")


def retry_once_429(func, *args, **kwargs):
    """
    Retry a function once if it fails with a 429 error (synchronous).

    DEPRECATED: Use retry_once_429_async() for async operations.
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if "429" in str(e):
            time.sleep(0.3)
            return func(*args, **kwargs)
        raise


async def retry_once_429_async(func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
    """
    Retry an async function once if it fails with a 429 error.

    This is the preferred function for all async code.
    """
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        if "429" in str(e):
            await asyncio.sleep(0.3)
            return await func(*args, **kwargs)
        raise


def ensure_json_hint(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
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


def extract_json_obj(text: str) -> Dict[str, Any]:
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


def kvize(obj: Any) -> List[Dict[str, Any]]:
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


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def dedup_merge_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id = {}
    for n in nodes:
        k = n["id"]
        if k in by_id:
            seen = {(p["key"], json.dumps(p["value"], ensure_ascii=False)) for p in by_id[k]["props"]}
            for p in n["props"]:
                sig = (p["key"], json.dumps(p["value"], ensure_ascii=False))
                if sig not in seen:
                    by_id[k]["props"].append(p)
                    seen.add(sig)
        else:
            by_id[k] = n
    return list(by_id.values())


def normalize_graph_shape(data: Any) -> Dict[str, Any]:
    from .utils import dedup_merge_nodes, kvize  # local import to avoid cycle in type hints

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
                or (n.get("labels")[0] if isinstance(n.get("labels"), list) and n.get("labels") else None)
                or "Entity"
            )
            props = kvize(n.get("props"))
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
            props = kvize(e.get("props"))
            if all(isinstance(x, str) and x for x in (src, dst, etype)):
                edges.append({"src": src, "dst": dst, "type": etype, "props": props})

    nodes = dedup_merge_nodes(nodes)
    return {"nodes": nodes, "edges": edges}


def prune_graph(data: Dict[str, Any]) -> Dict[str, Any]:
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
