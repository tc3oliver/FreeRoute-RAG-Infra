from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_chat_v1_success(monkeypatch):
    """Happy path: POST /v1/chat/completions forwards payload to litellm client and returns dict."""
    from services.gateway.routers import chat as chat_router

    async def mock_create(**kwargs):
        # mimic AsyncOpenAI response object with model_dump
        class Resp:
            def model_dump(self):
                return {"id": "resp1", "choices": [{"message": {"content": "ok"}}], "model": "rag-answer"}

        return Resp()

    async def mock_get_client():
        ns = SimpleNamespace()
        ns.chat = SimpleNamespace(completions=SimpleNamespace(create=mock_create))
        return ns

    monkeypatch.setattr("services.gateway.routers.chat.get_async_litellm_client", mock_get_client)

    # build a fake request object with json() and client.host
    class Req:
        def __init__(self):
            self.client = SimpleNamespace(host="127.0.0.1")

        async def json(self):
            return {"model": "rag-answer", "messages": [{"role": "user", "content": "hi"}]}

    req = Req()
    resp = await chat_router.openai_chat_completions(req)
    assert isinstance(resp, dict)
    assert resp.get("id") == "resp1"


@pytest.mark.asyncio
async def test_chat_v1_forward_ip_and_to_dict(monkeypatch):
    """Verify X-Client-IP header forwarded and response with to_dict handled."""
    from services.gateway.routers import chat as chat_router

    async def mock_create(**kwargs):
        # assert extra_headers forwarded
        assert "extra_headers" in kwargs
        assert kwargs["extra_headers"].get("X-Client-IP") == "10.0.0.5"

        class Resp:
            def to_dict(self):
                return {"id": "resp2", "choices": [{"message": {"content": "ok2"}}], "model": "rag-answer"}

        return Resp()

    async def mock_get_client():
        ns = SimpleNamespace()
        ns.chat = SimpleNamespace(completions=SimpleNamespace(create=mock_create))
        return ns

    monkeypatch.setattr("services.gateway.routers.chat.get_async_litellm_client", mock_get_client)

    class Req:
        def __init__(self):
            self.client = SimpleNamespace(host="10.0.0.5")

        async def json(self):
            return {"model": "rag-answer", "messages": [{"role": "user", "content": "hi"}]}

    req = Req()
    resp = await chat_router.openai_chat_completions(req)
    assert isinstance(resp, dict)
    assert resp.get("id") == "resp2"


@pytest.mark.asyncio
async def test_chat_v1_bad_payload():
    from services.gateway.routers import chat as chat_router

    class Req:
        async def json(self):
            return {"model": "rag-answer", "messages": []}

    with pytest.raises(HTTPException) as exc:
        await chat_router.openai_chat_completions(Req())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_embeddings_v1(monkeypatch):
    from services.gateway.routers import chat as chat_router

    async def mock_create(model, input):
        class Resp:
            def model_dump(self):
                return {"data": [{"embedding": [0.1, 0.2], "index": 0}], "model": model}

        return Resp()

    async def mock_get_client():
        ns = SimpleNamespace()
        ns.embeddings = SimpleNamespace(create=mock_create)
        return ns

    monkeypatch.setattr("services.gateway.routers.chat.get_async_litellm_client", mock_get_client)

    class Req:
        async def json(self):
            return {"model": "local-embed", "input": ["a", "b"]}

    req = Req()
    resp = await chat_router.openai_embeddings(req)
    assert isinstance(resp, dict)
    assert "data" in resp

    # missing input -> 400
    class BadReq:
        async def json(self):
            return {"model": "local-embed"}

    with pytest.raises(HTTPException) as exc:
        await chat_router.openai_embeddings(BadReq())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_embeddings_input_string_and_to_dict(monkeypatch):
    from services.gateway.routers import chat as chat_router

    async def mock_create(model, input):
        # input can be a string
        assert isinstance(input, (str, list))

        class Resp:
            def to_dict(self):
                return {"data": [{"embedding": [0.3], "index": 0}], "model": model}

        return Resp()

    async def mock_get_client():
        ns = SimpleNamespace()
        ns.embeddings = SimpleNamespace(create=mock_create)
        return ns

    monkeypatch.setattr("services.gateway.routers.chat.get_async_litellm_client", mock_get_client)

    class Req:
        async def json(self):
            return {"model": "local-embed", "input": "single string"}

    resp = await chat_router.openai_embeddings(Req())
    assert isinstance(resp, dict)
    assert "data" in resp
