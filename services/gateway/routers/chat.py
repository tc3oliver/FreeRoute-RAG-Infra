"""
Chat and embedding routers.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ..deps import require_key
from ..models import ChatReq, ChatResp, EmbedReq, EmbedResp, RerankReq, RerankResp
from ..repositories import call_reranker_async, get_async_litellm_client
from ..services import AsyncChatService

router = APIRouter(tags=["chat", "embed"])


async def get_async_chat_service() -> AsyncChatService:
    """Dependency injection for AsyncChatService."""
    return AsyncChatService()


@router.post("/chat", dependencies=[Depends(require_key)], response_model=ChatResp)
async def chat(
    req: ChatReq, request: Request, service: AsyncChatService = Depends(get_async_chat_service)
) -> Dict[str, Any]:
    """Process a chat completion request (asynchronous)."""
    messages = req.messages
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty array")

    try:
        return await service.chat(req, request.client.host)
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/chat upstream error")
        raise HTTPException(status_code=502, detail=f"upstream_chat_error: {e}")


@router.post("/embed", dependencies=[Depends(require_key)], response_model=EmbedResp)
async def embed(req: EmbedReq, service: AsyncChatService = Depends(get_async_chat_service)) -> Dict[str, Any]:
    """Generate embeddings for texts (asynchronous)."""
    try:
        return await service.embed(req)
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/embed upstream error")
        raise HTTPException(status_code=502, detail=f"embed_error: {e}")


@router.post("/rerank", dependencies=[Depends(require_key)], response_model=RerankResp)
async def rerank(req: RerankReq) -> Dict[str, Any]:
    """Rerank documents using the reranker service (asynchronous)."""
    try:
        result = await call_reranker_async(req.query, req.documents, req.top_n)
        return {"ok": True, "results": result.get("results", [])}
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/rerank upstream error")
        raise HTTPException(status_code=502, detail=f"rerank_error: {e}")


# === OpenAI-compatible proxy endpoints ===
@router.post("/v1/chat/completions", dependencies=[Depends(require_key)])
async def openai_chat_completions(request: Request) -> Dict[str, Any]:
    """OpenAI-compatible chat completions proxy to LiteLLM.

    Expects the OpenAI Chat Completions body (model, messages, temperature, etc.).
    Forwards the payload to the configured LiteLLM (via AsyncOpenAI client) and
    returns the upstream response unmodified where possible.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")

    if "messages" not in payload or not isinstance(payload.get("messages"), list) or not payload.get("messages"):
        raise HTTPException(status_code=400, detail="messages must be a non-empty array")

    try:
        client = await get_async_litellm_client()
        client_ip = getattr(getattr(request, "client", None), "host", "")
        # Forward all fields from payload to litellm client. Add client IP header.
        resp = await client.chat.completions.create(**payload, extra_headers={"X-Client-IP": client_ip})
        # Try to convert to plain dict if possible
        if hasattr(resp, "model_dump"):
            return resp.model_dump()
        if hasattr(resp, "to_dict"):
            return resp.to_dict()
        return resp
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/v1/chat/completions upstream error")
        raise HTTPException(status_code=502, detail=f"upstream_chat_error: {e}")


@router.post("/v1/embeddings", dependencies=[Depends(require_key)])
async def openai_embeddings(request: Request) -> Dict[str, Any]:
    """OpenAI-compatible embeddings proxy to LiteLLM.

    Accepts OpenAI style body: {"model": "...", "input": "..." or ["...", ...]}
    Returns the upstream embeddings response as-is where possible.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json body")

    # normalize input name differences: OpenAI uses 'input', internal embed uses 'texts'
    model = payload.get("model", "local-embed")
    inp = payload.get("input")
    if inp is None:
        raise HTTPException(status_code=400, detail="missing 'input' field")

    try:
        client = await get_async_litellm_client()
        # litellm client's embeddings.create accepts model=..., input=...
        resp = await client.embeddings.create(model=model, input=inp)
        if hasattr(resp, "model_dump"):
            return resp.model_dump()
        if hasattr(resp, "to_dict"):
            return resp.to_dict()
        return resp
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/v1/embeddings upstream error")
        raise HTTPException(status_code=502, detail=f"upstream_embed_error: {e}")
