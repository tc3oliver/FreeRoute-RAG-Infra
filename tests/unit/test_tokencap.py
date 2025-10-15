import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

with patch(
    "integrations.litellm.plugins.token_cap._load_graph_schema",
    return_value={"type": "object", "properties": {"nodes": {}, "edges": {}}, "required": ["nodes", "edges"]},
):
    from integrations.litellm.plugins import token_cap


def test_is_openai_model_name_and_entrypoint():
    assert token_cap.is_openai_model_name("gpt-5-mini-2025-08-07")
    assert token_cap.is_openai_entrypoint("rag-answer") is True or token_cap.is_openai_entrypoint("graph-extractor")


@pytest.mark.asyncio
async def test_pre_call_hook_redis_unavailable(monkeypatch):
    # Simulate redis.from_url returning None (connect failure)
    async def fake_try_redis_connect(url, retries=3, delay=0.5):
        return None

    monkeypatch.setattr(token_cap, "_try_redis_connect", fake_try_redis_connect)

    tc = token_cap.TokenCap()
    # data with minimal fields
    data = {"model": "rag-answer", "messages": [{"role": "user", "content": "hi"}]}

    # Should not raise even if redis unavailable
    out = await tc.async_pre_call_hook({}, {}, data, "completion", request_data={"path": "/v1/chat"})
    assert out.get("model") is not None


@pytest.mark.asyncio
async def test_pre_call_hook_reroute(monkeypatch):
    # Simulate redis returning a used amount >= limit
    class FakeRedis:
        def __init__(self):
            self.store = {}

        async def ping(self):
            return True

        async def get(self, k):
            return "10000000"

    async def fake_try_redis_connect(url, retries=3, delay=0.5):
        return FakeRedis()

    monkeypatch.setattr(token_cap, "_try_redis_connect", fake_try_redis_connect)
    # force a small limit for test
    monkeypatch.setenv("OPENAI_TPD_LIMIT", "1")

    tc = token_cap.TokenCap()
    data = {
        "model": "rag-answer",
        "messages": [{"role": "user", "content": "graph nodes and edges"}],
    }

    out = await tc.async_pre_call_hook({}, {}, data, "completion", request_data={"path": "/v1/chat"})
    # model should be rerouted if over limit
    assert out.get("model") != "rag-answer"
