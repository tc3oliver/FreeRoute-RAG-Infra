"""
Reranker service HTTP client.
"""

from typing import Any, Dict, List

import requests

from ..config import RERANKER_URL


def call_reranker(query: str, documents: List[str], top_n: int = 6, timeout: int = 30) -> Dict[str, Any]:
    """
    Call the reranker service to rerank documents.

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
