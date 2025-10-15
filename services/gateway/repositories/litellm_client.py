"""
LiteLLM client wrapper for chat completion and embeddings.
"""

from openai import OpenAI

from ..config import LITELLM_BASE, LITELLM_KEY

# Singleton client instance
_client: OpenAI | None = None


def get_litellm_client() -> OpenAI:
    """Get or create the OpenAI-compatible LiteLLM client."""
    global _client
    if _client is None:
        _client = OpenAI(base_url=LITELLM_BASE, api_key=LITELLM_KEY)
    return _client
