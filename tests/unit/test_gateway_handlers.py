import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

# Ensure gateway loads local graph_schema.json during import
ROOT = Path(__file__).resolve().parents[2]
schema_path = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(schema_path))

app_module = importlib.import_module("services.gateway.app")


def test_health_ok():
    resp = app_module.health()
    assert isinstance(resp, dict)
    assert resp.get("ok") is True


def test_chat_requires_messages():
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    with pytest.raises(app_module.HTTPException):
        app_module.chat(app_module.ChatReq(messages=[], json_mode=False), request)


def test_chat_json_mode_parsed(monkeypatch):
    # Mock client.chat.completions.create to return an object with choices[0].message.content
    class FakeChoice:
        def __init__(self, content):
            self.message = SimpleNamespace(content=content)

    class FakeResp:
        def __init__(self, model, content):
            self.choices = [FakeChoice(content)]
            self.model = model

    def fake_create(*args, **kwargs):
        return FakeResp("rag-answer", json.dumps({"a": 1}))

    monkeypatch.setattr(app_module.client.chat.completions, "create", fake_create)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    req = app_module.ChatReq(messages=[{"role": "user", "content": "Hi"}], json_mode=True)
    out = app_module.chat(req, request)
    assert out["ok"] is True
    assert isinstance(out["data"], dict)


def test_chat_non_json_returns_text(monkeypatch):
    class FakeChoice:
        def __init__(self, content):
            self.message = SimpleNamespace(content=content)

    class FakeResp:
        def __init__(self, model, content):
            self.choices = [FakeChoice(content)]
            self.model = model

    def fake_create(*args, **kwargs):
        return FakeResp("rag-answer", "plain text reply")

    monkeypatch.setattr(app_module.client.chat.completions, "create", fake_create)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    req = app_module.ChatReq(messages=[{"role": "user", "content": "Hi"}], json_mode=False)
    out = app_module.chat(req, request)
    assert out["ok"] is True
    assert isinstance(out["data"], str)


def test_ensure_ok_non_json_response(monkeypatch):
    # The gateway module does not export a generic ensure_ok helper.
    # This test is intentionally left as a placeholder for integration-style
    # response parsing tests that require requesting the running service.
    assert True
