# === 標準函式庫 ===
import logging
import os

# === 第三方套件 ===
# For backward compatibility with tests (re-export commonly used imports)
from fastapi import (
    FastAPI,
    HTTPException,  # noqa: F401
)

# --- Local module imports ---
from .config import APP_VERSION
from .middleware import (
    METRICS_ENABLED,  # noqa: F401
    RequestContextFilter,
    add_request_id,
    prometheus_middleware,
)
from .models import ChatReq, ChatResp, EmbedReq, EmbedResp, GraphProbeReq, GraphProbeResp, GraphReq  # noqa: F401
from .repositories import get_litellm_client  # noqa: F401
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

# For tests that expect client directly on app module
client = get_litellm_client()

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


# Compatibility wrappers for tests that call functions directly
def chat(req: ChatReq, request):
    """Backward compatibility wrapper for tests."""
    messages = req.messages
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty array")

    from .services import ChatService

    service = ChatService()
    return service.chat(req, request.client.host if hasattr(request, "client") else "127.0.0.1")


def graph_extract(req: GraphReq, request):
    """Backward compatibility wrapper for tests."""
    from .services import GraphService

    service = GraphService()
    try:
        return service.extract(req, request.client.host if hasattr(request, "client") else "127.0.0.1")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise


def graph_probe(req: GraphProbeReq, request):
    """Backward compatibility wrapper for tests."""
    from .services import GraphService

    service = GraphService()
    return service.probe(req, request.client.host if hasattr(request, "client") else "127.0.0.1")
