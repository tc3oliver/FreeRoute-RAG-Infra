"""
Chat and embedding service.
"""

import json
import warnings
from typing import Any, Dict

from openai import AsyncOpenAI

from ..config import DEFAULTS
from ..models import ChatReq, EmbedReq
from ..repositories import get_async_litellm_client
from ..utils import ensure_json_hint, retry_once_429, retry_once_429_async


class AsyncChatService:
    """
    Service for chat completions and embeddings via LiteLLM (asynchronous).

    This is the preferred service for all new code.
    Provides better performance through non-blocking I/O.
    """

    def __init__(self):
        self.client: AsyncOpenAI | None = None

    async def _ensure_client(self) -> None:
        """Lazy initialization of the async client (async-only)."""
        if self.client is None:
            self.client = await get_async_litellm_client()

    async def chat(self, req: ChatReq, client_ip: str) -> Dict[str, Any]:
        """
        Process a chat completion request (asynchronous).

        Args:
            req: Chat request with messages and settings
            client_ip: Client IP address for tracking

        Returns:
            Dict with 'ok', 'data', and 'meta' keys
        """
        await self._ensure_client()
        model = self._normalize_model(req.model, kind="chat")
        messages = req.messages

        extra: Dict[str, Any] = {}
        if req.json_mode:
            messages = ensure_json_hint(messages)
            extra["response_format"] = {"type": "json_object"}

        async def _call():
            return await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=req.temperature,
                extra_headers={"X-Client-IP": client_ip},
                **extra,
            )

        resp = await retry_once_429_async(_call)
        out = resp.choices[0].message.content
        meta = {"model": resp.model}

        # Try to parse as JSON if possible
        try:
            return {"ok": True, "data": json.loads(out), "meta": meta}
        except Exception:
            return {"ok": True, "data": out, "meta": meta}

    async def embed(self, req: EmbedReq) -> Dict[str, Any]:
        """
        Generate embeddings for texts (asynchronous).

        Args:
            req: Embed request with list of texts

        Returns:
            Dict with 'ok', 'vectors', and 'dim' keys
        """
        await self._ensure_client()
        r = await self.client.embeddings.create(model="local-embed", input=req.texts)
        vecs = [d.embedding for d in r.data]
        return {"ok": True, "vectors": vecs, "dim": (len(vecs[0]) if vecs else 0)}

    @staticmethod
    def _normalize_model(model: str | None, kind: str = "chat") -> str:
        """Normalize model name to a valid entrypoint."""
        if not model:
            return DEFAULTS[kind]
        m = model.strip()
        from ..config import ENTRYPOINTS

        return m if m in ENTRYPOINTS else DEFAULTS[kind]
