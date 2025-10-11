# plugins/token_cap.py
import datetime
import json
import os
from typing import Literal

try:
    from litellm.integrations.custom_logger import CustomLogger
except Exception:

    class CustomLogger:  # fallback
        pass


import redis.asyncio as redis

# ─────────────────────────────────────────────────────────
# 環境變數
# ─────────────────────────────────────────────────────────
OPENAI_TPD_LIMIT = int(os.getenv("OPENAI_TPD_LIMIT", "10000000"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TZ_OFFSET_HOURS = int(os.getenv("TZ_OFFSET_HOURS", "8"))
GRAPH_SCHEMA_PATH = os.getenv("GRAPH_SCHEMA_PATH", "/app/schemas/graph_schema.json")

# 入口名與改道路由（僅針對「入口名」生效）
OPENAI_ENTRYPOINTS_EXACT = {"rag-answer", "graph-extractor"}
OPENAI_ENTRYPOINTS_PREFIX = ("graph-extractor",)

OPENAI_REROUTE_REAL = os.getenv("OPENAI_REROUTE_REAL", "true").lower() == "true"


REROUTE_MAP = {
    "rag-answer": "rag-answer-gemini",
    "graph-extractor": "graph-extractor-gemini",
    "graph-extractor-o1mini": "graph-extractor-gemini",
}

DEFAULT_GRAPH_REROUTE = "graph-extractor-gemini"
DEFAULT_RAG_REROUTE = "rag-answer-gemini"

# 用來辨識「真實 OpenAI 模型名」→ 直接 429（禁止繞付費名）
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


# ─────────────────────────────────────────────────────────
# 共用工具
# ─────────────────────────────────────────────────────────
def is_openai_model_name(name: str) -> bool:
    if not name:
        return False
    n = name.lower()
    return n in _OPENAI_NAME_EXACT or any(n.startswith(p) for p in _OPENAI_NAME_PREFIXES)


def is_openai_entrypoint(name: str) -> bool:
    if not name:
        return False
    return name in OPENAI_ENTRYPOINTS_EXACT or any(
        name.startswith(p) for p in OPENAI_ENTRYPOINTS_PREFIX
    )


def pick_reroute(name: str) -> str:
    if name in REROUTE_MAP:
        return REROUTE_MAP[name]
    if any(name.startswith(p) for p in OPENAI_ENTRYPOINTS_PREFIX):
        return DEFAULT_GRAPH_REROUTE
    return DEFAULT_RAG_REROUTE


def _today_key(prefix: str) -> str:
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=TZ_OFFSET_HOURS)
    return f"{prefix}:{now.strftime('%Y-%m-%d')}"


def _load_graph_schema(path: str) -> dict:
    """
    Fail-Fast：讀不到或結構不合理即 raise，讓容器啟動失敗，避免 Schema 漂移。
    為了避免在 litellm 容器內要求安裝 jsonschema，這裡做「基本結構」檢查即可。
    """
    if not os.path.exists(path):
        raise RuntimeError(f"[FATAL][TokenCap] graph_schema.json not found at: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        raise RuntimeError(f"[FATAL][TokenCap] graph_schema.json load failed: {e}")

    # 基礎檢查：必須是物件、具有 type/properties/required，且至少包含 nodes/edges
    if not isinstance(schema, dict):
        raise RuntimeError("[FATAL][TokenCap] graph_schema.json invalid: not an object")

    if "type" not in schema or "properties" not in schema or "required" not in schema:
        raise RuntimeError(
            "[FATAL][TokenCap] graph_schema.json invalid: missing keys (type/properties/required)"
        )

    props = schema.get("properties", {})
    req = schema.get("required", [])
    if not isinstance(props, dict) or not isinstance(req, list):
        raise RuntimeError("[FATAL][TokenCap] graph_schema.json invalid: properties/required types")

    if "nodes" not in props or "edges" not in props:
        raise RuntimeError(
            "[FATAL][TokenCap] graph_schema.json invalid: missing properties.nodes/edges"
        )

    if "nodes" not in req or "edges" not in req:
        raise RuntimeError(
            "[FATAL][TokenCap] graph_schema.json invalid: required must include nodes/edges"
        )

    return schema


def _looks_like_graph_call(data: dict) -> bool:
    """
    粗判定：這次 chat 是否是「圖譜抽取」任務
    條件一：response_format 是 json_schema，且 schema 包含 nodes/edges
    條件二（備援）：messages 內文含 nodes/edges/圖譜/節點/關係 等關鍵字
    """
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


# 在匯入時就讀檔（Fail-Fast）
GRAPH_JSON_SCHEMA = _load_graph_schema(GRAPH_SCHEMA_PATH)


# ─────────────────────────────────────────────────────────
# TokenCap 實作
# ─────────────────────────────────────────────────────────
class TokenCap(CustomLogger):
    def __init__(self):
        self._r = None

    async def _redis(self):
        if self._r is None:
            self._r = await redis.from_url(REDIS_URL, decode_responses=True)
        return self._r

    async def async_pre_call_hook(
        self,
        user_api_key_dict,
        cache,
        data: dict,
        call_type: Literal[
            "completion",
            "text_completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
        ],
        **kwargs,  # e.g. request_data
    ):
        # ---- 跳過 /health、缺 model 的請求 ----
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
        print("[TokenCap] pre model =", model)

        # ---- OpenAI TPD 檢查（UTC+8 按日）----
        r = await self._redis()
        tpd_key = _today_key("tpd:openai")
        used = int(await r.get(tpd_key) or 0)

        if used >= OPENAI_TPD_LIMIT:
            # 允許多跳 reroute，直到不是 OpenAI（或達到安全上限）
            hops = 0
            MAX_HOPS = 3

            def _needs_reroute(m: str) -> bool:
                # 入口名屬於 graph-extractor* / rag-answer* 等（OpenAI 入口）→ 需要改道
                if is_openai_entrypoint(m):
                    return True
                # 真實 OpenAI 型號也需要改道（若開啟 OPENAI_REROUTE_REAL）
                if OPENAI_REROUTE_REAL and (
                    m.lower().startswith("openai/") or is_openai_model_name(m)
                ):
                    return True
                return False

            while _needs_reroute(model) and hops < MAX_HOPS:
                # 入口名：用路由表；真實型號：依任務型態選預設改道
                if is_openai_entrypoint(model):
                    new_model = pick_reroute(model)
                else:
                    # 真實 OpenAI 型號：圖抽取 → graph；否則 → rag
                    new_model = (
                        DEFAULT_GRAPH_REROUTE
                        if _looks_like_graph_call(data)
                        else DEFAULT_RAG_REROUTE
                    )

                # 若沒變化就中止（避免死循環）
                if not new_model or new_model == model:
                    break

                data["model"] = new_model
                model = new_model
                hops += 1
                print(f"[TokenCap] reroute(hop {hops}) ->", new_model)

            # 多跳後仍是 OpenAI 且不允許改道 → 429
            if (
                model.lower().startswith("openai/") or is_openai_model_name(model)
            ) and not OPENAI_REROUTE_REAL:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=429, detail={"error": "OpenAI daily token cap reached"}
                )

        # ---- Graph 入口：強制 JSON Schema 回覆（跨供應商）----
        if is_openai_entrypoint(model) and any(
            model.startswith(p) for p in OPENAI_ENTRYPOINTS_PREFIX
        ):
            # 設定 JSON Schema（由本檔讀取）
            data.setdefault(
                "response_format",
                {
                    "type": "json_schema",
                    "json_schema": {"name": "graph", "schema": GRAPH_JSON_SCHEMA, "strict": True},
                },
            )
            # 生成設定
            data["temperature"] = 0

            # Gemini 的 JSON MIME 放在 extra_body，OpenAI 看不到
            if model.startswith("gemini/"):
                data.setdefault("extra_body", {}).setdefault(
                    "response_mime_type", "application/json"
                )

            # 移除會造成特定供應商 400 的鍵
            for k in ("generation_config", "max_output_tokens", "response_mime_type"):
                data.pop(k, None)

            # 訊息內若沒有任何包含 "json" 的文字，補上最小 system 提示
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

        return data

    async def async_post_call_success_hook(self, *args, **kwargs):
        """
        成功回來才記帳；且只記 OpenAI 的使用量。
        """
        try:
            response = args[2] if len(args) >= 3 else kwargs.get("response")
            model = getattr(response, "model", "") or ""
            if not is_openai_model_name(model):
                return

            usage = getattr(response, "usage", {}) or {}
            total = int(usage.get("total_tokens") or 0)
            if total <= 0:
                total = int(usage.get("prompt_tokens") or 0) + int(
                    usage.get("completion_tokens") or 0
                )

            if total > 0:
                r = await self._redis()
                key = _today_key("tpd:openai")
                p = r.pipeline()
                p.incrby(key, total)
                p.expire(key, 60 * 60 * 36)  # 保留 36h
                await p.execute()
        except Exception:
            # 靜默忽略，避免非阻斷錯誤
            return

    async def async_post_call_failure_hook(self, *args, **kwargs):
        # 忽略所有失敗回呼，避免 /health 或第三方差異造成的噪音
        return


proxy_handler_instance = TokenCap()
