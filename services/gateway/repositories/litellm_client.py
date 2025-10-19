"""
LiteLLM client wrapper for chat completion and embeddings.
"""

from types import SimpleNamespace

from openai import AsyncOpenAI

from ..config import LITELLM_BASE, LITELLM_KEY

_async_client: AsyncOpenAI | None = None


async def get_async_litellm_client() -> AsyncOpenAI:
    """
    Get or create the async OpenAI-compatible LiteLLM client.

    This is the preferred client for all new code.
    Configured with reasonable defaults for production use.
    """
    global _async_client
    if _async_client is None:
        _async_client = AsyncOpenAI(
            base_url=LITELLM_BASE,
            api_key=LITELLM_KEY,
            timeout=30.0,  # 30 second timeout
            max_retries=2,  # Retry twice on failure
        )
    return _async_client


async def close_async_client() -> None:
    """Close the async client and cleanup resources."""
    global _async_client, _sync_singleton
    if _async_client is not None:
        await _async_client.close()
        _async_client = None
    _sync_singleton = None
