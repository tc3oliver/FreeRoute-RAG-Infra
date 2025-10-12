import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))

app = importlib.import_module("services.gateway.app")


class _FakeChoice:
    def __init__(self, content: str):
        self.message = SimpleNamespace(content=content)


class _FakeResp:
    def __init__(self, model: str, content: str):
        self.choices = [_FakeChoice(content)]
        self.model = model


def _req_ctx():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))


def test_graph_extract_success_minimal(monkeypatch):
    # Return minimal valid graph meeting thresholds
    payload = {
        "nodes": [
            {"id": "n1", "type": "Person", "props": {"name": "Bob"}},
        ],
        "edges": [
            {"src": "n1", "dst": "n2", "type": "EMPLOYED_AT", "props": {"role": "dev"}},
        ],
    }

    def fake_create(*args, **kwargs):
        return _FakeResp("graph-extractor", json.dumps(payload))

    monkeypatch.setattr(app.client.chat.completions, "create", fake_create)
    req = app.GraphReq(context="Alice joined Acme in 2022", strict=True)
    out = app.graph_extract(req, _req_ctx())
    assert out["ok"] is True
    assert out["data"]["nodes"] and out["data"]["edges"]


def test_graph_extract_below_threshold_422(monkeypatch):
    payload = {"nodes": [], "edges": []}

    def fake_create(*args, **kwargs):
        return _FakeResp("graph-extractor", json.dumps(payload))

    monkeypatch.setattr(app.client.chat.completions, "create", fake_create)
    req = app.GraphReq(
        context="Nick joined in 2024",
        strict=True,
        min_nodes=1,
        min_edges=1,
        max_attempts=1,
        provider_chain=["graph-extractor"],
    )
    with pytest.raises(app.HTTPException) as ei:
        app.graph_extract(req, _req_ctx())
    assert ei.value.status_code == 422
    assert isinstance(ei.value.detail, dict)
    assert ei.value.detail.get("error") == "graph_extraction_failed"


def test_graph_extract_single_error_node(monkeypatch):
    payload = {"nodes": [{"id": "err", "type": "error", "props": []}], "edges": []}

    def fake_create(*args, **kwargs):
        return _FakeResp("graph-extractor", json.dumps(payload))

    monkeypatch.setattr(app.client.chat.completions, "create", fake_create)
    req = app.GraphReq(
        context="Text",
        strict=True,
        max_attempts=1,
        provider_chain=["graph-extractor"],
    )
    with pytest.raises(app.HTTPException) as ei:
        app.graph_extract(req, _req_ctx())
    assert ei.value.status_code == 422


def test_graph_extract_repair_flow_success(monkeypatch):
    # First call returns invalid JSON; repair call returns valid graph
    responses = [
        _FakeResp("graph-extractor", "<<<not json>>>"),
        _FakeResp(
            "graph-extractor",
            json.dumps(
                {
                    "nodes": [
                        {
                            "id": "n1",
                            "type": "Person",
                            "props": [{"key": "name", "value": "Alice"}],
                        }
                    ],
                    "edges": [
                        {
                            "src": "n1",
                            "dst": "n2",
                            "type": "EMPLOYED_AT",
                            "props": [{"key": "role", "value": "eng"}],
                        }
                    ],
                }
            ),
        ),
    ]

    def fake_create(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(app.client.chat.completions, "create", fake_create)
    req = app.GraphReq(
        context="Alice joined Acme in 2022",
        strict=True,
        repair_if_invalid=True,
        max_attempts=1,
        provider_chain=["graph-extractor"],
    )
    out = app.graph_extract(req, _req_ctx())
    assert out["ok"] is True
    assert out["data"]["nodes"] and out["data"]["edges"]
