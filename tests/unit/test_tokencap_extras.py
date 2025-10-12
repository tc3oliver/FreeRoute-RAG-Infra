import importlib
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"


def _import_tokencap_with_env():
    os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))
    from integrations.litellm.plugins import token_cap as tc

    importlib.reload(tc)
    return tc


def test_looks_like_graph_call_via_response_format():
    tc = _import_tokencap_with_env()
    data = {
        "model": "graph-extractor",
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "graph",
                "schema": json.loads(Path(SCHEMA_PATH).read_text()),
                "strict": True,
            },
        },
    }
    assert tc._looks_like_graph_call(data) is True


def test_looks_like_graph_call_via_messages():
    tc = _import_tokencap_with_env()
    data = {"model": "rag-answer", "messages": [{"role": "user", "content": "nodes and edges"}]}
    assert tc._looks_like_graph_call(data) is True


def test_pick_reroute_defaults():
    tc = _import_tokencap_with_env()
    assert tc.pick_reroute("rag-answer") == "rag-answer-gemini"
    assert tc.pick_reroute("graph-extractor") == "graph-extractor-gemini"
    # graph-extractor-* 前綴 → 視為 graph 類型
    assert tc.pick_reroute("graph-extractor-o1mini") == "graph-extractor-gemini"
    # 其他未知 → rag 默認
    assert tc.pick_reroute("unknown-model") == "rag-answer-gemini"


@pytest.mark.asyncio
async def test_schema_injection_for_graph_entrypoint(monkeypatch):
    tc = _import_tokencap_with_env()

    # 避免 redis 依賴
    async def fake_try_redis_connect(url, retries=3, delay=0.5):
        return None

    monkeypatch.setattr(tc, "_try_redis_connect", fake_try_redis_connect)

    plugin = tc.TokenCap()
    data = {
        "model": "graph-extractor",
        "messages": [{"role": "user", "content": "extract graph from text"}],
    }

    out = await plugin.async_pre_call_hook({}, {}, data, "completion", request_data={"path": "/v1/chat"})

    assert out["temperature"] == 0
    assert isinstance(out.get("response_format"), dict)
    rf = out["response_format"]
    assert rf.get("type") == "json_schema"
    assert "json_schema" in rf
    # 應插入 JSON-only 系統提示
    assert isinstance(out.get("messages"), list) and out["messages"]
    assert out["messages"][0]["role"] == "system"
    assert "JSON" in out["messages"][0]["content"].upper()
