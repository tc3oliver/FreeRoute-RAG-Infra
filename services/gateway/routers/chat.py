"""
Chat and embedding routers.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ..deps import require_key
from ..models import ChatReq, ChatResp, EmbedReq, EmbedResp, RerankReq, RerankResp
from ..repositories import call_reranker
from ..services import ChatService

router = APIRouter(tags=["chat", "embed"])


def get_chat_service() -> ChatService:
    """Dependency injection for ChatService."""
    return ChatService()


@router.post("/chat", dependencies=[Depends(require_key)], response_model=ChatResp)
def chat(req: ChatReq, request: Request, service: ChatService = Depends(get_chat_service)) -> Dict[str, Any]:
    """Process a chat completion request."""
    messages = req.messages
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty array")

    try:
        return service.chat(req, request.client.host)
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/chat upstream error")
        raise HTTPException(status_code=502, detail=f"upstream_chat_error: {e}")


@router.post("/embed", dependencies=[Depends(require_key)], response_model=EmbedResp)
def embed(req: EmbedReq, service: ChatService = Depends(get_chat_service)) -> Dict[str, Any]:
    """Generate embeddings for texts."""
    try:
        return service.embed(req)
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/embed upstream error")
        raise HTTPException(status_code=502, detail=f"embed_error: {e}")


@router.post("/rerank", dependencies=[Depends(require_key)], response_model=RerankResp)
def rerank(req: RerankReq) -> Dict[str, Any]:
    """Rerank documents using the reranker service."""
    try:
        result = call_reranker(req.query, req.documents, req.top_n)
        return {"ok": True, "results": result.get("results", [])}
    except Exception as e:
        import logging

        logging.getLogger("gateway").exception("/rerank upstream error")
        raise HTTPException(status_code=502, detail=f"rerank_error: {e}")
