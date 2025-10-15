from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Response
from fastapi.responses import PlainTextResponse

from ..config import (
    APP_VERSION,
    ENTRYPOINTS,
    GRAPH_ALLOW_EMPTY,
    GRAPH_JSON_SCHEMA,
    GRAPH_MAX_ATTEMPTS,
    GRAPH_MIN_EDGES,
    GRAPH_MIN_NODES,
    GRAPH_SCHEMA_HASH,
    GRAPH_SCHEMA_PATH,
    LITELLM_BASE,
    PROVIDER_CHAIN,
)
from ..deps import require_key
from ..middleware import CONTENT_TYPE_LATEST
from ..models import HealthResp, VersionResp, WhoAmIResp

try:
    from prometheus_client import generate_latest
except Exception:  # pragma: no cover
    generate_latest = None


router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResp)
def health() -> Dict[str, Any]:
    return {"ok": True}


@router.get("/version", response_model=VersionResp)
def version() -> Dict[str, str]:
    return {"version": APP_VERSION}


@router.get("/whoami", dependencies=[Depends(require_key)], response_model=WhoAmIResp)
def whoami() -> Dict[str, Any]:
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


@router.get("/metrics")
def metrics() -> Response:
    if not generate_latest:
        return Response(status_code=204)
    # resolve flag dynamically to support tests monkeypatching services.gateway.app.METRICS_ENABLED
    try:
        import importlib

        app_mod = importlib.import_module("services.gateway.app")
        m_enabled = getattr(app_mod, "METRICS_ENABLED", None)
    except Exception:
        m_enabled = None
    if m_enabled is None:
        try:
            import importlib

            md = importlib.import_module("services.gateway.middleware")
            m_enabled = getattr(md, "METRICS_ENABLED", False)
        except Exception:
            m_enabled = False
    if not m_enabled:
        return Response(status_code=204)
    try:
        import importlib

        md = importlib.import_module("services.gateway.middleware")
        reg = getattr(md, "METRICS_REG", None)
        if reg is not None:
            data = generate_latest(reg)
        else:
            data = generate_latest()
    except Exception:
        try:
            data = generate_latest()
        except Exception:
            return Response(status_code=204)
    return PlainTextResponse(content=data, media_type=CONTENT_TYPE_LATEST)
