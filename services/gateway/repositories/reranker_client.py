"""
Reranker service HTTP client.
"""

from typing import Any, Dict, List

import httpx
import requests

from ..config import RERANKER_URL


def call_reranker(query: str, documents: List[str], top_n: int = 6, timeout: int = 30) -> Dict[str, Any]:
    """
    Call the reranker service to rerank documents (synchronous).

    DEPRECATED: Use call_reranker_async() for async operations.
    This function is kept for backward compatibility during migration.

    Args:
        query: Search query
        documents: List of document texts to rerank
        top_n: Number of top results to return
        timeout: Request timeout in seconds

    Returns:
        Dict with 'results' key containing reranked items

    Raises:
        Exception: If the HTTP request fails
    """
    response = requests.post(
        f"{RERANKER_URL}/rerank",
        json={"query": query, "documents": documents, "top_n": top_n},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


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
