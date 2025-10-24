import os
from pathlib import Path

import pytest
from fastapi import HTTPException

# Setup schema path before any gateway imports
ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))


@pytest.mark.asyncio
async def test_valid_api_key_in_header(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "test-key-1,test-key-2")
    importlib.reload(deps)
    result = await deps.require_key(x_api_key="test-key-1", authorization=None)
    assert result == "default"


@pytest.mark.asyncio
async def test_valid_api_key_with_whitespace(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "test-key")
    importlib.reload(deps)
    result = await deps.require_key(x_api_key="  test-key  ", authorization=None)
    assert result == "default"


@pytest.mark.asyncio
async def test_valid_bearer_token(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "secret-token")
    importlib.reload(deps)
    result = await deps.require_key(x_api_key=None, authorization="Bearer secret-token")
    assert result == "default"


@pytest.mark.asyncio
async def test_valid_bearer_token_with_whitespace(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "secret-token")
    importlib.reload(deps)
    result = await deps.require_key(x_api_key=None, authorization="Bearer  secret-token  ")
    assert result == "default"


@pytest.mark.asyncio
async def test_bearer_token_case_insensitive(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "token123")
    importlib.reload(deps)
    result = await deps.require_key(x_api_key=None, authorization="bearer token123")
    assert result == "default"
    result = await deps.require_key(x_api_key=None, authorization="BEARER token123")
    assert result == "default"
    result = await deps.require_key(x_api_key=None, authorization="BeArEr token123")
    assert result == "default"


@pytest.mark.asyncio
async def test_invalid_api_key(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "valid-key")
    importlib.reload(deps)
    with pytest.raises(HTTPException) as exc:
        await deps.require_key(x_api_key="invalid-key", authorization=None)
    assert exc.value.status_code == 401
    assert "Invalid API key" in exc.value.detail


@pytest.mark.asyncio
async def test_missing_api_key(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "some-key")
    importlib.reload(deps)
    with pytest.raises(HTTPException) as exc:
        await deps.require_key(x_api_key=None, authorization=None)
    assert exc.value.status_code == 401
    assert "Missing API key" in exc.value.detail


@pytest.mark.asyncio
async def test_empty_api_key(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "valid-key")
    importlib.reload(deps)
    with pytest.raises(HTTPException) as exc:
        await deps.require_key(x_api_key="", authorization=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_empty_bearer_token(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "valid-key")
    importlib.reload(deps)
    with pytest.raises(HTTPException) as exc:
        await deps.require_key(x_api_key=None, authorization="Bearer ")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_malformed_authorization_header(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "valid-key")
    importlib.reload(deps)
    with pytest.raises(HTTPException) as exc:
        await deps.require_key(x_api_key=None, authorization="Basic some-token")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_x_api_key_takes_precedence(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "key-from-x-api-key,key-from-bearer")
    importlib.reload(deps)
    with pytest.raises(HTTPException) as exc:
        await deps.require_key(x_api_key="key-from-x-api-key", authorization="Bearer wrong-token")
    assert exc.value.status_code == 401
    assert "Invalid API key" in exc.value.detail


@pytest.mark.asyncio
async def test_multiple_valid_keys(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "key1,key2,key3")
    importlib.reload(deps)
    assert await deps.require_key(x_api_key="key1", authorization=None) == "default"
    assert await deps.require_key(x_api_key="key2", authorization=None) == "default"
    assert await deps.require_key(x_api_key="key3", authorization=None) == "default"


@pytest.mark.asyncio
async def test_keys_with_commas_and_spaces(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", " key1 , key2 , key3 ")
    importlib.reload(deps)
    assert await deps.require_key(x_api_key="key1", authorization=None) == "default"
    assert await deps.require_key(x_api_key="key2", authorization=None) == "default"
    assert await deps.require_key(x_api_key="key3", authorization=None) == "default"


@pytest.mark.asyncio
async def test_default_dev_key(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.delenv("API_GATEWAY_KEYS", raising=False)
    importlib.reload(deps)
    result = await deps.require_key(x_api_key="dev-key", authorization=None)
    assert result == "default"


@pytest.mark.asyncio
async def test_empty_keys_config(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "")
    importlib.reload(deps)
    with pytest.raises(HTTPException) as exc:
        await deps.require_key(x_api_key="any-key", authorization=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_only_whitespace_keys(monkeypatch):
    import importlib

    from services.gateway import deps

    importlib.reload(deps)
    monkeypatch.setenv("API_GATEWAY_KEYS", "  ,  ,  ")
    importlib.reload(deps)
    with pytest.raises(HTTPException) as exc:
        await deps.require_key(x_api_key="any-key", authorization=None)
    assert exc.value.status_code == 401
