"""
Chat and embedding service.
"""

import json
from typing import Any, Dict, List

from ..config import DEFAULTS
from ..models import ChatReq, EmbedReq
from ..repositories import get_litellm_client
from ..utils import ensure_json_hint, retry_once_429


class ChatService:
    """Service for chat completions and embeddings via LiteLLM."""

    def __init__(self):
        self.client = get_litellm_client()

    def chat(self, req: ChatReq, client_ip: str) -> Dict[str, Any]:
        """
        Process a chat completion request.

        Args:
            req: Chat request with messages and settings
            client_ip: Client IP address for tracking

        Returns:
            Dict with 'ok', 'data', and 'meta' keys
        """
        model = self._normalize_model(req.model, kind="chat")
        messages = req.messages

        extra: Dict[str, Any] = {}
        if req.json_mode:
            messages = ensure_json_hint(messages)
            extra["response_format"] = {"type": "json_object"}

        def _call():
            return self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=req.temperature,
                extra_headers={"X-Client-IP": client_ip},
                **extra,
            )

        resp = retry_once_429(_call)
        out = resp.choices[0].message.content
        meta = {"model": resp.model}

        # Try to parse as JSON if possible
        try:
            return {"ok": True, "data": json.loads(out), "meta": meta}
        except Exception:
            return {"ok": True, "data": out, "meta": meta}

    def embed(self, req: EmbedReq) -> Dict[str, Any]:
        """
        Generate embeddings for texts.

        Args:
            req: Embed request with list of texts

        Returns:
            Dict with 'ok', 'vectors', and 'dim' keys
        """
        r = self.client.embeddings.create(model="local-embed", input=req.texts)
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
