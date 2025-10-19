# === 標準函式庫 ===
import logging
import os
from contextlib import asynccontextmanager

# === 第三方套件 ===
# For backward compatibility with tests (re-export commonly used imports)
from fastapi import HTTPException  # noqa: F401
from fastapi import FastAPI

# --- Local module imports ---
from .config import APP_VERSION
from .middleware import METRICS_ENABLED  # noqa: F401
from .middleware import RequestContextFilter, add_request_id, prometheus_middleware
from .models import ChatReq, ChatResp, EmbedReq, EmbedResp, GraphProbeReq, GraphProbeResp, GraphReq  # noqa: F401
from .repositories import (
    close_async_litellm_client,
    close_async_neo4j_driver,
    close_async_qdrant_client,
    get_async_litellm_client,
)
from .routers import chat, graph, meta, vector
from .routers.meta import health, version, whoami  # noqa: F401
from .utils import dedup_merge_nodes as _dedup_merge_nodes  # noqa: F401
from .utils import ensure_json_hint as _ensure_json_hint
from .utils import extract_json_obj as _extract_json_obj
from .utils import kvize as _kvize
from .utils import normalize_graph_shape as _normalize_graph_shape
from .utils import prune_graph as _prune_graph
from .utils import retry_once_429 as _retry_once_429
from .utils import sha1 as _sha1


# === FastAPI lifespan：確保關閉非同步客戶端資源 ===
@asynccontextmanager
async def _lifespan(_app: FastAPI):
    try:
        yield
    finally:
        # 儘管路由已全面改為非同步，仍可能有背景資源需要釋放
        try:
            await close_async_litellm_client()
        except Exception:
            pass
        try:
            await close_async_qdrant_client()
        except Exception:
            pass
        try:
            await close_async_neo4j_driver()
        except Exception:
            pass


# === FastAPI 應用 ===
app = FastAPI(title="FreeRoute RAG Infra – API Gateway", version=APP_VERSION, lifespan=_lifespan)

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

# === API 路由 ===
app.include_router(meta.router)
app.include_router(chat.router)
app.include_router(vector.router)
app.include_router(graph.router)

# === Backward compatibility: Re-export route handlers for tests ===
# Alias handlers from already-imported router modules to avoid late imports
_chat_handler = chat.chat  # noqa: F401
_embed_handler = chat.embed  # noqa: F401
_graph_extract_handler = graph.graph_extract  # noqa: F401
_graph_probe_handler = graph.graph_probe  # noqa: F401
