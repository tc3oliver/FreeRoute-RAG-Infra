"""
Reranker service HTTP client.
"""

import asyncio
from typing import Any, Dict, List

import httpx

from ..config import RERANKER_URL


async def call_reranker_async(
    query: str, documents: List[str], top_n: int = 6, timeout: float = 30.0
) -> Dict[str, Any]:
    """
    Call the reranker service to rerank documents (asynchronous).

    This is the preferred function for all new code.

    Args:
        query: Search query
        documents: List of document texts to rerank
        top_n: Number of top results to return
        timeout: Request timeout in seconds

    Returns:
        Dict with 'results' key containing reranked items

    Raises:
        httpx.HTTPError: If the HTTP request fails
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{RERANKER_URL}/rerank",
            json={"query": query, "documents": documents, "top_n": top_n},
        )
        response.raise_for_status()
        return response.json()
