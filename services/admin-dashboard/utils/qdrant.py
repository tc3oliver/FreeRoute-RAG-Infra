"""
Async Qdrant helper wrapper for admin-dashboard.

Provides basic collection and point management functions used by routers/rag.py.
This wrapper lazily imports the official qdrant-client AsyncQdrantClient and
exposes a small, opinionated API with simple error mapping.
"""

import importlib
import json
import os
import uuid
from typing import Any, Dict, List, Optional

QDRANT_URL = os.getenv("QDRANT_URL")

_async_client: Optional[Any] = None


async def get_async_qdrant_client() -> Any:
    global _async_client
    if not QDRANT_URL:
        raise RuntimeError("qdrant_unavailable: missing QDRANT_URL env")
    if _async_client is None:
        try:
            qdc_mod = importlib.import_module("qdrant_client")
            AsyncQdrantClient = getattr(qdc_mod, "AsyncQdrantClient")
            _async_client = AsyncQdrantClient(url=QDRANT_URL)
        except Exception as e:
            raise RuntimeError(f"qdrant_unavailable: {e}")
    return _async_client


async def list_collections(client: Any) -> List[Dict[str, Any]]:
    try:
        # qdrant-client exposes get_collections or get_collection depending on version
        info = await client.get_collections()
        # info may be a model or dict-like
        if hasattr(info, "collections"):
            cols = info.collections
        else:
            cols = info
        return [c if isinstance(c, dict) else c.__dict__ for c in cols]
    except Exception as e:
        raise RuntimeError(f"qdrant_list_error: {e}")


async def ensure_collection(client: Any, name: str, dim: int, distance: str = "Cosine") -> str:
    try:
        models_mod = importlib.import_module("qdrant_client.models")
        Distance = getattr(models_mod, "Distance")
        VectorParams = getattr(models_mod, "VectorParams")
        # attempt to get collection; if missing, recreate
        try:
            await client.get_collection(name)
        except Exception:
            # create with default HNSW config via recreate_collection
            dist_enum = getattr(Distance, distance.upper(), Distance.COSINE)
            await client.recreate_collection(
                collection_name=name, vectors_config=VectorParams(size=dim, distance=dist_enum)
            )
        return name
    except Exception as e:
        raise RuntimeError(f"qdrant_ensure_error: {e}")


async def delete_collection(client: Any, name: str) -> bool:
    try:
        await client.delete_collection(name)
        return True
    except Exception:
        return False


async def upsert_points(
    client: Any, collection_name: str, points: List[Dict[str, Any]], batch_size: int = 500
) -> Dict[str, Any]:
    """Upsert points (list of dicts with id/vector/payload). Returns summary."""
    try:
        # Normalize point ids: Qdrant accepts unsigned integers or UUIDs.
        normalized: List[Dict[str, Any]] = []
        for p in points:
            np = dict(p)
            if "id" in np and np["id"] is not None:
                pid = np["id"]
                # allow integers
                if isinstance(pid, int):
                    np["id"] = pid
                else:
                    # if it's a string, try to parse as UUID; otherwise generate a namespaced UUID
                    try:
                        parsed = uuid.UUID(str(pid))
                        np["id"] = str(parsed)
                    except Exception:
                        # deterministic uuid5 so repeated upserts use same id
                        np["id"] = str(uuid.uuid5(uuid.NAMESPACE_OID, str(pid)))
            else:
                # no id provided: generate a random uuid
                np["id"] = str(uuid.uuid4())
            normalized.append(np)

        # do simple batching
        total = 0
        for i in range(0, len(normalized), batch_size):
            batch = normalized[i : i + batch_size]
            await client.upsert(collection_name=collection_name, points=batch)
            total += len(batch)
        return {"upserted": total}
    except Exception as e:
        raise RuntimeError(f"qdrant_upsert_error: {e}")


async def search(
    client: Any, collection_name: str, vector: List[float], top_k: int = 10, with_payload: bool = True
) -> List[Dict[str, Any]]:
    try:
        res = await client.search(
            collection_name=collection_name, query_vector=vector, limit=top_k, with_payload=with_payload
        )
        # result items may be model instances; normalize to dict
        out = []
        for item in res:
            if hasattr(item, "to_dict"):
                out.append(item.to_dict())
            elif hasattr(item, "dict"):
                out.append(item.dict())
            else:
                # fallback: try __dict__
                out.append(item.__dict__ if hasattr(item, "__dict__") else dict(item))
        return out
    except Exception as e:
        raise RuntimeError(f"qdrant_search_error: {e}")


async def list_points(client: Any, collection_name: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    """Return paginated points from a collection. Normalizes result into dict with 'points' list and 'next' optional cursor."""
    try:
        # qdrant-client historically provides scroll(collection_name, limit, offset, with_payload)
        if hasattr(client, "scroll"):
            res = await client.scroll(collection_name=collection_name, offset=offset, limit=limit, with_payload=True)
            # res may be a model with 'points' attr or a list
            if hasattr(res, "points"):
                pts = res.points
            else:
                pts = res
        else:
            # fallback: try export or get_points (older/newer clients differ)
            # try client.get_points
            if hasattr(client, "get_points"):
                pts = await client.get_points(collection_name=collection_name, limit=limit, offset=offset)
            else:
                # last resort: attempt search with empty vector (not ideal) -> raise
                raise RuntimeError("qdrant_client_missing_scroll")

        # Some qdrant-client versions return a nested container like ([Record(...), Record(...)],)
        # or a single list as an element. Flatten common nested list/tuple wrappers so we
        # iterate actual record items.
        def _flatten_items(seq):
            for itm in seq:
                # skip Nones early
                if itm is None:
                    continue
                # if itm looks like a plain list/tuple of records, yield its members
                if isinstance(itm, (list, tuple)) and not isinstance(itm, dict):
                    for inner in itm:
                        yield inner
                else:
                    yield itm

        flat_pts = list(_flatten_items(pts))

        out = []
        for p in flat_pts:
            pid = None
            payload = None

            # 1) try to coerce to dict via to_dict()/dict()
            item = None
            try:
                if hasattr(p, "to_dict"):
                    item = p.to_dict()
                elif hasattr(p, "dict"):
                    item = p.dict()
            except Exception:
                item = None

            if isinstance(item, dict):
                pid = item.get("id") or item.get("point_id") or item.get("id_")
                payload = item.get("payload") or item.get("payload")

            # 2) if still missing, check mapping protocol
            if pid is None and isinstance(p, dict):
                pid = p.get("id") or p.get("point_id") or p.get("id_")
                payload = p.get("payload") or p.get("payload")

            # 3) attribute access
            if pid is None:
                pid = getattr(p, "id", None) or getattr(p, "point_id", None) or getattr(p, "pointId", None)
            if payload is None:
                payload = getattr(p, "payload", None) or getattr(p, "payload", None)

            # 4) sequence/tuple fallback
            if (pid is None or payload is None) and isinstance(p, (list, tuple)):
                try:
                    if len(p) >= 1 and pid is None:
                        pid = p[0]
                    if len(p) >= 2 and payload is None:
                        payload = p[1]
                except Exception:
                    pass

            # 5) normalize/unwrap payload:
            # - if payload is a pydantic/model-like object, convert to dict
            try:
                if payload is not None and not isinstance(payload, dict):
                    if hasattr(payload, "to_dict"):
                        payload = payload.to_dict()
                    elif hasattr(payload, "dict"):
                        payload = payload.dict()
            except Exception:
                pass

            # - common wrapper shapes: {'id':..., 'payload': {...}, ...} or {'point': {...}} or {'value': {...}}
            try:
                if isinstance(payload, dict):
                    if "payload" in payload and isinstance(payload["payload"], dict):
                        payload = payload["payload"]
                    elif "point" in payload and isinstance(payload["point"], dict):
                        # point may itself contain payload or be the actual payload
                        pval = payload["point"]
                        payload = pval.get("payload") if isinstance(pval.get("payload"), dict) else pval
                    elif "value" in payload and isinstance(payload["value"], dict):
                        payload = payload["value"]
            except Exception:
                pass

            # 6) normalize pid to a simple string when possible; avoid taking str() of an object that dumps payload
            norm_id = None
            try:
                if pid is None:
                    norm_id = None
                elif isinstance(pid, (int, float)):
                    norm_id = str(pid)
                elif isinstance(pid, str):
                    norm_id = pid
                elif isinstance(pid, dict):
                    nested = pid.get("id") or pid.get("point_id") or pid.get("uuid")
                    norm_id = str(nested) if nested is not None else json.dumps(pid, default=str)
                else:
                    # try to extract common attributes
                    nested = getattr(pid, "id", None) or getattr(pid, "point_id", None) or getattr(pid, "uuid", None)
                    if nested is not None:
                        norm_id = str(nested)
                    else:
                        # last resort: str() but guard against verbose repr containing 'payload='
                        s = str(pid)
                        if "payload=" in s and "id=" in s:
                            # avoid returning entire repr; set to None to let preview show payload
                            norm_id = None
                        else:
                            norm_id = s
            except Exception:
                norm_id = str(pid)

            # skip empty placeholders
            if norm_id is None and payload is None:
                continue
            out.append({"id": norm_id, "payload": payload})

        return {"points": out}
    except Exception as e:
        raise RuntimeError(f"qdrant_list_points_error: {e}")


async def delete_point(client: Any, collection_name: str, point_id: Any) -> bool:
    """Delete a single point by id. Returns True on success."""
    try:
        # qdrant-client provides delete(collection_name=..., points=[...]) in recent versions
        if hasattr(client, "delete"):
            # some clients accept points arg, others accept points param name 'points' or 'point_id'
            await client.delete(collection_name=collection_name, points=[point_id])
            return True
        # fallback: try delete_point method
        if hasattr(client, "delete_point"):
            await client.delete_point(collection_name=collection_name, point_id=point_id)
            return True
        # fallback not available
        raise RuntimeError("qdrant_delete_not_supported")
    except Exception:
        return False


async def health(client: Any) -> Dict[str, Any]:
    try:
        # simple ping by calling get_collections
        cols = await client.get_collections()
        return {"ok": True, "collections": len(cols.collections) if hasattr(cols, "collections") else len(cols)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def close_client() -> None:
    global _async_client
    if _async_client is not None:
        try:
            await _async_client.close()
        finally:
            _async_client = None
