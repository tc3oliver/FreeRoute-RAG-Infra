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
from typing import TYPE_CHECKING, Any, Awaitable, Dict, Literal, Optional, cast

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


OPENAI_ENTRYPOINTS_EXACT = {"rag-answer", "rag-answer-pro", "graph-extractor"}
OPENAI_ENTRYPOINTS_PREFIX = ("graph-extractor",)
OPENAI_REROUTE_REAL = os.getenv("OPENAI_REROUTE_REAL", "true").lower() == "true"


# === reroute 設定 ===
REROUTE_MAP = {
    "rag-answer": "rag-answer-gemini",
    "rag-answer-pro": "rag-answer",  # First fallback to mini before Gemini
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
    "gpt-5-2025-08-07",
    "gpt-5.1",
    "gpt-5.1-2025-11-13",
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


def _sanitize_env_key(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name).upper()


def _get_tpd_limit_for_group(group: Optional[str]) -> int:
    """Return per-group TPD limit if configured, else the global OPENAI_TPD_LIMIT.

    Env var pattern: OPENAI_TPD_LIMIT__<GROUP>, GROUP uses sanitized name e.g. OPENAI_GPT_5, OPENAI_GPT_5_MINI
    """
    if group:
        key = f"OPENAI_TPD_LIMIT__{_sanitize_env_key(group)}"
        v = os.getenv(key)
        if v and v.isdigit():
            try:
                return int(v)
            except Exception:
                pass
    return OPENAI_TPD_LIMIT


def _tpd_redis_key(group: Optional[str]) -> str:
    if group:
        return _today_key(f"tpd:openai:group:{group}")
    return _today_key("tpd:openai")


def _cap_group_from_model_string(model_name: str) -> Optional[str]:
    """Map concrete OpenAI model name to a logical cap group.

    Example: gpt-5-2025-08-07 -> openai.gpt-5
             gpt-5-mini-2025-08-07 -> openai.gpt-5-mini
    Returns None if not an OpenAI gpt-5 family we care about.
    """
    if not model_name:
        return None
    n = model_name.lower()
    # strip provider prefix if present
    if n.startswith("openai/"):
        n = n.split("/", 1)[1]
    # CRITICAL: check mini BEFORE non-mini to avoid false positives
    if n.startswith("gpt-5-mini-") or n == "gpt-5-mini":
        return "openai.gpt-5-mini"
    if n.startswith("gpt-5.") or n.startswith("gpt-5-") or n == "gpt-5":
        return "openai.gpt-5"
    return None


def _cap_group_for_request_model(alias_or_model: str) -> Optional[str]:
    """Infer cap group from the requested model alias or full name before routing.

    We know our aliases: rag-answer -> gpt-5-mini, rag-answer-pro -> gpt-5
    Also handle direct openai model names when passed through.
    """
    if not alias_or_model:
        return None
    name = alias_or_model.lower()
    if name == "rag-answer":
        return "openai.gpt-5-mini"
    if name == "rag-answer-pro":
        return "openai.gpt-5"
    # direct model path
    grp = _cap_group_from_model_string(name)
    return grp


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
            # Verify connection. Some redis client implementations may expose
            # `ping()` as either a coroutine or a synchronous function that
            # returns bool. To satisfy static typing we check the return value
            # and only await when it's awaitable.
            ping_result = r.ping()
            if isinstance(ping_result, bool):
                # if the synchronous ping returned False, treat as failure
                if not ping_result:
                    raise RuntimeError("redis ping returned False")
            else:
                await cast(Awaitable[bool], ping_result)
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
        # Remember cap group for post-hook accounting
        cap_group = _cap_group_for_request_model(model)
        # structured pre-call log
        logger.info("[TokenCap] pre model=%s", model, extra={"event": "pre", "model": model, "cap_group": cap_group})

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
                # Prefer per-group limit if configured; else use global
                per_limit = _get_tpd_limit_for_group(cap_group)
                use_per = cap_group is not None
                tpd_key = _tpd_redis_key(cap_group) if use_per else _tpd_redis_key(None)
                used = int(await r.get(tpd_key) or 0)
                logger.debug(
                    "[TokenCap] tpd_status used=%s limit=%s",
                    used,
                    per_limit if use_per else OPENAI_TPD_LIMIT,
                    extra={
                        "event": "tpd_status",
                        "used": used,
                        "limit": per_limit if use_per else OPENAI_TPD_LIMIT,
                        "scope": cap_group if use_per else "global",
                    },
                )
            except Exception as e:
                logger.warning(
                    "[TokenCap] redis_error %s skipping TPD enforcement",
                    e,
                    extra={"event": "redis_error", "error": str(e)},
                )
                used = 0

        # Determine effective limit and whether to enforce per-group
        eff_limit = _get_tpd_limit_for_group(cap_group)
        if used >= eff_limit:
            hops = 0
            MAX_HOPS = 3

            def _needs_reroute(m: str) -> bool:
                if is_openai_entrypoint(m):
                    return True
                if OPENAI_REROUTE_REAL and (m.lower().startswith("openai/") or is_openai_model_name(m)):
                    return True
                return False

            async def _check_alternative_quota(alternative_model: str) -> bool:
                """Check if alternative model still has quota available."""
                alt_cap_group = _cap_group_for_request_model(alternative_model)
                if not alt_cap_group:
                    return True  # Non-OpenAI models always available

                if r is None:
                    return True  # Redis unavailable, allow fallback

                try:
                    alt_limit = _get_tpd_limit_for_group(alt_cap_group)
                    alt_tpd_key = _tpd_redis_key(alt_cap_group)
                    alt_used = int(await r.get(alt_tpd_key) or 0)
                    logger.info(
                        "[TokenCap] checking_alternative model=%s used=%s limit=%s",
                        alternative_model,
                        alt_used,
                        alt_limit,
                        extra={
                            "event": "checking_alternative",
                            "model": alternative_model,
                            "used": alt_used,
                            "limit": alt_limit,
                        },
                    )
                    return alt_used < alt_limit
                except Exception as e:
                    logger.warning("[TokenCap] error checking alternative quota: %s", e)
                    return True

            while _needs_reroute(model) and hops < MAX_HOPS:
                if is_openai_entrypoint(model):
                    # For rag-answer-pro (gpt-5), first try rag-answer (gpt-5-mini)
                    if model == "rag-answer-pro":
                        mini_alternative = "rag-answer"
                        if await _check_alternative_quota(mini_alternative):
                            new_model = mini_alternative
                            logger.info(
                                "[TokenCap] gpt-5 quota exceeded, trying gpt-5-mini alternative",
                                extra={"event": "try_mini_alternative", "from": model, "to": new_model},
                            )
                        else:
                            # Both gpt-5 and gpt-5-mini exceeded, fallback to Gemini
                            new_model = pick_reroute(model)
                            logger.info(
                                "[TokenCap] both gpt-5 and gpt-5-mini quota exceeded, fallback to Gemini",
                                extra={"event": "all_openai_exceeded", "fallback": new_model},
                            )
                    else:
                        new_model = pick_reroute(model)
                else:
                    new_model = DEFAULT_GRAPH_REROUTE if _looks_like_graph_call(data) else DEFAULT_RAG_REROUTE

                if not new_model or new_model == model:
                    break

                data["model"] = new_model
                model = new_model
                cap_group = _cap_group_for_request_model(model)
                hops += 1
                logger.info(
                    "[TokenCap] reroute hop=%s new_model=%s cap_group=%s",
                    hops,
                    new_model,
                    cap_group,
                    extra={"event": "reroute", "hop": hops, "new_model": new_model, "cap_group": cap_group},
                )

                # Re-check quota for the new model
                if cap_group and r is not None:
                    try:
                        new_limit = _get_tpd_limit_for_group(cap_group)
                        new_tpd_key = _tpd_redis_key(cap_group)
                        new_used = int(await r.get(new_tpd_key) or 0)
                        if new_used >= new_limit:
                            logger.info(
                                "[TokenCap] fallback model also exceeded quota, continuing reroute",
                                extra={
                                    "event": "fallback_exceeded",
                                    "model": model,
                                    "used": new_used,
                                    "limit": new_limit,
                                },
                            )
                            continue
                        else:
                            # Quota available, stop rerouting
                            break
                    except Exception as e:
                        logger.warning("[TokenCap] error checking new model quota: %s", e)
                        break

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

        # Attach cap group hint for post-hook accounting
        try:
            md = data.setdefault("metadata", {})
            if isinstance(md, dict):
                md.setdefault("tokencap_group", cap_group)
        except Exception:
            pass
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
                # Compute cap group from actual upstream model
                cap_group_resp = _cap_group_from_model_string(model)

                p = r.pipeline()
                # Always increment global counter for observability
                gkey = _tpd_redis_key(None)
                p.incrby(gkey, total)
                p.expire(gkey, 60 * 60 * 36)
                # Increment per-group if we can resolve one
                if cap_group_resp:
                    ekey = _tpd_redis_key(cap_group_resp)
                    p.incrby(ekey, total)
                    p.expire(ekey, 60 * 60 * 36)
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
