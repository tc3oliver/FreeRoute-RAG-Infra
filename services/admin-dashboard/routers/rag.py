from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.db.models import AuditLog

from ..db import get_db
from ..schemas.rag import CollectionSpec, SearchRequest, UpsertRequest
from ..utils.auth import require_admin_token
from ..utils.qdrant import (
    delete_collection,
    delete_point,
    ensure_collection,
    get_async_qdrant_client,
    health,
    list_collections,
    list_points,
    search,
    upsert_points,
)

router = APIRouter(prefix="/admin/rag")


@router.get("/collections")
async def get_collections(_: bool = Depends(require_admin_token)):
    client = await get_async_qdrant_client()
    try:
        cols = await list_collections(client)
        return {"collections": cols}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collections")
async def create_collection(
    payload: CollectionSpec, db: AsyncSession = Depends(get_db), _: bool = Depends(require_admin_token)
):
    client = await get_async_qdrant_client()
    try:
        name = payload.name
        await ensure_collection(client, name, payload.vector_size, payload.distance or "Cosine")
        # audit
        audit = AuditLog(
            tenant_id=None, action="create_qdrant_collection", actor="admin-dashboard", details={"collection": name}
        )
        db.add(audit)
        await db.commit()
        return {"created": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collections/{name}")
async def remove_collection(name: str, db: AsyncSession = Depends(get_db), _: bool = Depends(require_admin_token)):
    client = await get_async_qdrant_client()
    try:
        deleted = await delete_collection(client, name)
        audit = AuditLog(
            tenant_id=None,
            action="delete_qdrant_collection",
            actor="admin-dashboard",
            details={"collection": name, "deleted": deleted},
        )
        db.add(audit)
        await db.commit()
        return {"deleted": deleted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collections/{name}/upsert")
async def upsert_collection_points(
    name: str, payload: UpsertRequest, db: AsyncSession = Depends(get_db), _: bool = Depends(require_admin_token)
):
    client = await get_async_qdrant_client()
    try:
        pts = [p.dict(exclude_none=True) for p in payload.points]
        res = await upsert_points(client, name, pts)
        audit = AuditLog(
            tenant_id=None,
            action="qdrant_upsert",
            actor="admin-dashboard",
            details={"collection": name, "count": res.get("upserted")},
        )
        db.add(audit)
        await db.commit()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collections/{name}/search")
async def search_collection(name: str, payload: SearchRequest, _: bool = Depends(require_admin_token)):
    client = await get_async_qdrant_client()
    try:
        results = await search(client, name, payload.vector, payload.top_k, payload.with_payload)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def qdrant_health(_: bool = Depends(require_admin_token)):
    client = await get_async_qdrant_client()
    try:
        return await health(client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{name}/points")
async def get_collection_points(
    name: str,
    limit: int = 100,
    offset: int = 0,
    raw: bool = False,
    _: bool = Depends(require_admin_token),
):
    """List points from a Qdrant collection.

    If `raw=true` is provided, the endpoint will return the raw items as returned
    by the Qdrant client (attempting a best-effort conversion to JSON-able types).
    This is a debug aid to inspect varying client return shapes.
    """
    client = await get_async_qdrant_client()
    try:
        if limit <= 0 or offset < 0:
            raise HTTPException(status_code=400, detail="invalid pagination")
        if raw:
            # attempt to fetch raw points from client and convert to serializable forms
            if hasattr(client, "scroll"):
                pts_src = await client.scroll(collection_name=name, offset=offset, limit=limit, with_payload=True)
                pts = getattr(pts_src, "points", pts_src)
            elif hasattr(client, "get_points"):
                pts = await client.get_points(collection_name=name, limit=limit, offset=offset)
            else:
                raise HTTPException(status_code=501, detail="qdrant client does not support raw fetching")

            out = []
            for item in pts:
                try:
                    if hasattr(item, "to_dict"):
                        out.append(item.to_dict())
                    elif hasattr(item, "dict"):
                        out.append(item.dict())
                    elif isinstance(item, dict):
                        out.append(item)
                    elif hasattr(item, "__dict__"):
                        out.append(item.__dict__)
                    else:
                        out.append({"repr": repr(item)})
                except Exception:
                    out.append({"error_repr": repr(item)})
            return {"raw_points": out}

        res = await list_points(client, name, limit=limit, offset=offset)
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collections/{name}/points/{point_id}")
async def remove_collection_point(
    name: str, point_id: str, db: AsyncSession = Depends(get_db), _: bool = Depends(require_admin_token)
):
    client = await get_async_qdrant_client()
    try:
        deleted = await delete_point(client, name, point_id)
        audit = AuditLog(
            tenant_id=None,
            action="qdrant_delete_point",
            actor="admin-dashboard",
            details={"collection": name, "point_id": point_id, "deleted": deleted},
        )
        db.add(audit)
        await db.commit()
        return {"deleted": deleted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
