"""TokenCap plugin for LiteLLM.

Responsibilities:
- Enforce daily OpenAI token caps (TPD) and optionally reroute requests when caps hit.
- Inject JSON schema & hints for graph extraction entrypoints.

This module focuses on observability and resiliency: structured logs (event=...),
graceful Redis degradation, and clearer typing/docstrings. Behavioral surface is
kept compatible with the original implementation.
"""

# === 標準函式庫 ===
import asyncio
import datetime
import json
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional

# === 第三方套件 ===
import redis.asyncio as redis

# === 動態/型別檢查 import，允許單元測試 fallback ===
if TYPE_CHECKING:
    from litellm.integrations.custom_logger import CustomLogger as _CustomLogger
else:
    try:
        from litellm.integrations.custom_logger import CustomLogger as _CustomLogger
    except Exception:  # pragma: no cover
        # fallback class for unit test import
        class _CustomLogger:
            def __init__(self, *args, **kwargs): ...


# === 日誌設定 ===
logger = logging.getLogger("tokencap")
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())


# === 環境變數 ===
OPENAI_TPD_LIMIT = int(os.getenv("OPENAI_TPD_LIMIT", "10000000"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TZ_OFFSET_HOURS = int(os.getenv("TZ_OFFSET_HOURS", "8"))
GRAPH_SCHEMA_PATH = os.getenv("GRAPH_SCHEMA_PATH", "/app/schemas/graph_schema.json")


OPENAI_ENTRYPOINTS_EXACT = {"rag-answer", "graph-extractor"}
OPENAI_ENTRYPOINTS_PREFIX = ("graph-extractor",)
OPENAI_REROUTE_REAL = os.getenv("OPENAI_REROUTE_REAL", "true").lower() == "true"


# === reroute 設定 ===
REROUTE_MAP = {
    "rag-answer": "rag-answer-gemini",
    "graph-extractor": "graph-extractor-gemini",
    "graph-extractor-o1mini": "graph-extractor-gemini",
}
DEFAULT_GRAPH_REROUTE = "graph-extractor-gemini"
DEFAULT_RAG_REROUTE = "rag-answer-gemini"


_OPENAI_NAME_PREFIXES = (
    "openai/",
    "gpt-",
    "o1-",
    "o3-",
    "o4-",
    "text-embedding-",
    "whisper-",
    "tts-",
)
_OPENAI_NAME_EXACT = {
    "gpt-5-mini-2025-08-07",
    "gpt-4.1-mini-2025-04-14",
    "o1-mini-2024-09-12",
}


## === 工具函式 ===
def is_openai_model_name(name: str) -> bool:
    if not name:
        return False
    n = name.lower()
    return n in _OPENAI_NAME_EXACT or any(n.startswith(p) for p in _OPENAI_NAME_PREFIXES)


def is_openai_entrypoint(name: str) -> bool:
    if not name:
        return False
    return name in OPENAI_ENTRYPOINTS_EXACT or any(name.startswith(p) for p in OPENAI_ENTRYPOINTS_PREFIX)


def pick_reroute(name: str) -> str:
    if name in REROUTE_MAP:
        return REROUTE_MAP[name]
    if any(name.startswith(p) for p in OPENAI_ENTRYPOINTS_PREFIX):
        return DEFAULT_GRAPH_REROUTE
    return DEFAULT_RAG_REROUTE


def _today_key(prefix: str) -> str:
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=TZ_OFFSET_HOURS)
    return f"{prefix}:{now.strftime('%Y-%m-%d')}"


def _load_graph_schema(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise RuntimeError(f"[FATAL][TokenCap] graph_schema.json not found at: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        raise RuntimeError(f"[FATAL][TokenCap] graph_schema.json load failed: {e}")

    if not isinstance(schema, dict):
        raise RuntimeError("[FATAL][TokenCap] graph_schema.json invalid: not an object")

    if "type" not in schema or "properties" not in schema or "required" not in schema:
        raise RuntimeError("[FATAL][TokenCap] graph_schema.json invalid: missing keys (type/properties/required)")

    props = schema.get("properties", {})
    req = schema.get("required", [])
    if not isinstance(props, dict) or not isinstance(req, list):
        raise RuntimeError("[FATAL][TokenCap] graph_schema.json invalid: properties/required types")

    if "nodes" not in props or "edges" not in props:
        raise RuntimeError("[FATAL][TokenCap] graph_schema.json invalid: missing properties.nodes/edges")

    if "nodes" not in req or "edges" not in req:
        raise RuntimeError("[FATAL][TokenCap] graph_schema.json invalid: required must include nodes/edges")

    return schema


async def _try_redis_connect(url: str, retries: int = 3, delay: float = 0.5) -> Optional[redis.Redis]:
    """Attempt to create a Redis client and verify connectivity.

    Returns a connected Redis client on success, otherwise None after retries.
    """
    for attempt in range(1, retries + 1):
        try:
            # from_url returns a client instance (not a coroutine)
            r: redis.Redis = redis.from_url(url, decode_responses=True)
            # Verify connection
            await r.ping()
            return r
        except Exception as e:
            logger.debug("[TokenCap] redis connect attempt %s failed: %s", attempt, e)
            if attempt < retries:
                await asyncio.sleep(delay * attempt)
    return None


def _looks_like_graph_call(data: Dict[str, Any]) -> bool:
    try:
        rf = data.get("response_format") or {}
        if isinstance(rf, dict) and rf.get("type") == "json_schema":
            js = (rf.get("json_schema") or {}).get("schema") or {}
            props = js.get("properties", {})
            if isinstance(props, dict) and "nodes" in props and "edges" in props:
                return True
    except Exception:
        pass

    try:
        msgs = data.get("messages", [])
        if isinstance(msgs, list):
            joined = " ".join([(m.get("content") or "") for m in msgs if isinstance(m, dict)])
            j = joined.lower()
            if "nodes" in j and "edges" in j:
                return True
            if any(k in joined for k in ("圖譜", "節點", "關係")):
                return True
    except Exception:
        pass

    return False


# === 載入 Graph Schema ===
GRAPH_JSON_SCHEMA = _load_graph_schema(GRAPH_SCHEMA_PATH)


## === 主流程 TokenCap 類別 ===
class TokenCap(_CustomLogger):
    def __init__(self):
        self._r: Optional[redis.Redis] = None

    async def _redis(self) -> Optional[redis.Redis]:
        """Return a cached redis client or try to connect. Returns None if unavailable."""
        if self._r is not None:
            return self._r
        r: Optional[redis.Redis] = await _try_redis_connect(REDIS_URL)
        if r is not None:
            self._r = r
        return self._r

    async def async_pre_call_hook(
        self,
        user_api_key_dict,
        cache,
        data: Dict[str, Any],
        call_type: Literal[
            "completion",
            "text_completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
        ],
        **kwargs,
    ):
        path = ""
        req = kwargs.get("request_data")
        try:
            if isinstance(req, dict):
                path = req.get("path") or ""
            else:
                path = getattr(req, "path", "") or ""
        except Exception:
            path = ""

        if path.endswith("/health") or not isinstance(data, dict) or not data.get("model"):
            return data

        model = data.get("model") or ""
        # structured pre-call log
        logger.info("[TokenCap] pre model=%s", model, extra={"event": "pre", "model": model})

        # check TPD usage if redis available
        r = await self._redis()
        if r is None:
            # Redis not available: graceful degradation
            logger.warning(
                "[TokenCap] redis_unavailable skipping TPD enforcement",
                extra={"event": "redis_unavailable"},
            )
            used = 0
        else:
            try:
                tpd_key = _today_key("tpd:openai")
                used = int(await r.get(tpd_key) or 0)
                logger.debug(
                    "[TokenCap] tpd_status used=%s limit=%s",
                    used,
                    OPENAI_TPD_LIMIT,
                    extra={"event": "tpd_status", "used": used, "limit": OPENAI_TPD_LIMIT},
                )
            except Exception as e:
                logger.warning(
                    "[TokenCap] redis_error %s skipping TPD enforcement",
                    e,
                    extra={"event": "redis_error", "error": str(e)},
                )
                used = 0

        if used >= OPENAI_TPD_LIMIT:
            hops = 0
            MAX_HOPS = 3

            def _needs_reroute(m: str) -> bool:
                if is_openai_entrypoint(m):
                    return True
                if OPENAI_REROUTE_REAL and (m.lower().startswith("openai/") or is_openai_model_name(m)):
                    return True
                return False

            while _needs_reroute(model) and hops < MAX_HOPS:
                if is_openai_entrypoint(model):
                    new_model = pick_reroute(model)
                else:
                    new_model = DEFAULT_GRAPH_REROUTE if _looks_like_graph_call(data) else DEFAULT_RAG_REROUTE

                if not new_model or new_model == model:
                    break

                data["model"] = new_model
                model = new_model
                hops += 1
                logger.info(
                    "[TokenCap] reroute hop=%s new_model=%s",
                    hops,
                    new_model,
                    extra={"event": "reroute", "hop": hops, "new_model": new_model},
                )

            if (model.lower().startswith("openai/") or is_openai_model_name(model)) and not OPENAI_REROUTE_REAL:
                from fastapi import HTTPException

                raise HTTPException(status_code=429, detail={"error": "OpenAI daily token cap reached"})

        if is_openai_entrypoint(model) and any(model.startswith(p) for p in OPENAI_ENTRYPOINTS_PREFIX):
            data.setdefault(
                "response_format",
                {
                    "type": "json_schema",
                    "json_schema": {"name": "graph", "schema": GRAPH_JSON_SCHEMA, "strict": True},
                },
            )
            data["temperature"] = 0

            if model.startswith("gemini/"):
                data.setdefault("extra_body", {}).setdefault("response_mime_type", "application/json")

            for k in ("generation_config", "max_output_tokens", "response_mime_type"):
                data.pop(k, None)

            if isinstance(data.get("messages"), list):
                msgs = data["messages"]
                has_json_word = False
                for m in msgs:
                    try:
                        c = m.get("content") or ""
                        if isinstance(c, str) and ("json" in c.lower()):
                            has_json_word = True
                            break
                    except Exception:
                        continue
                if not has_json_word:
                    msgs.insert(
                        0,
                        {
                            "role": "system",
                            "content": "只輸出 JSON，必須符合 JSON Schema，不得包含文字或 Markdown。",
                        },
                    )
            logger.info(
                "[TokenCap] schema_inject model=%s",
                model,
                extra={"event": "schema_inject", "model": model},
            )

        return data

    async def async_post_call_success_hook(self, *args, **kwargs):
        try:
            response = args[2] if len(args) >= 3 else kwargs.get("response")
            model = getattr(response, "model", "") or ""
            if not is_openai_model_name(model):
                return

            usage = getattr(response, "usage", {}) or {}
            total = int(usage.get("total_tokens") or 0)
            if total <= 0:
                total = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)

            logger.info(
                "[TokenCap] usage model=%s tokens=%s",
                model,
                total,
                extra={"event": "usage", "model": model, "tokens": total},
            )

            if total > 0:
                r = await self._redis()
                if r is None:
                    logger.warning(
                        "[TokenCap] redis_unavailable while recording usage",
                        extra={"event": "redis_unavailable"},
                    )
                    return
                key = _today_key("tpd:openai")
                p = r.pipeline()
                p.incrby(key, total)
                p.expire(key, 60 * 60 * 36)
                await p.execute()
        except Exception as e:
            logger.exception(
                "[TokenCap] post_call_success_error %s",
                e,
                extra={"event": "post_call_success_error", "error": str(e)},
            )
            return

    async def async_post_call_failure_hook(self, *args, **kwargs):
        """Called when an upstream call failed. Log failure metadata for observability."""
        try:
            response = args[2] if len(args) >= 3 else kwargs.get("response")
            err = kwargs.get("error") or getattr(response, "error", None) or "unknown"
            logger.warning(
                "[TokenCap] call_failure error=%s",
                err,
                extra={"event": "call_failure", "error": str(err)},
            )
        except Exception:
            logger.exception("[TokenCap] unexpected error in failure hook")
        return


# === Plugin 實例 ===
proxy_handler_instance = TokenCap()
