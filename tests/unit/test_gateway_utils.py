import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))

app_module = importlib.import_module("services.gateway.app")


def test_extract_json_obj_basic():
    text = """
    ```json
    {"a":1, "b": 2}
    ```
    """
    out = app_module._extract_json_obj(text)
    assert out == {"a": 1, "b": 2}


def test_extract_json_obj_brace_scan():
    text = 'prefix {"x": 3, "y": {"z": 9}} suffix'
    out = app_module._extract_json_obj(text)
    assert out["x"] == 3 and out["y"]["z"] == 9


def test_kvize_and_dedup():
    kvs = app_module._kvize({"name": "Alice", "age": 18})
    assert {k["key"] for k in kvs} == {"name", "age"}

    nodes = [
        {"id": "1", "type": "Person", "props": [{"key": "name", "value": "Alice"}]},
        {"id": "1", "type": "Person", "props": [{"key": "age", "value": 18}]},
    ]
    merged = app_module._dedup_merge_nodes(nodes)
    assert len(merged) == 1
    keys = {p["key"] for p in merged[0]["props"]}
    assert keys == {"name", "age"}


def test_normalize_graph_shape_and_prune():
    data = {
        "nodes": [
            {"id": "n1", "type": "Person", "props": {"name": "Bob", "unused": ""}},
        ],
        "edges": [
            {"src": "n1", "dst": "n2", "type": "EMPLOYED_AT", "props": {"role": "dev", "empty": ""}},
        ],
    }
    norm = app_module._normalize_graph_shape(data)
    pruned = app_module._prune_graph(norm)
    assert pruned["nodes"][0]["props"] and pruned["edges"][0]["props"]
    # 確保空字串的值會被移除
    assert not any(p["key"] == "unused" for p in pruned["nodes"][0]["props"])
    assert not any(p["key"] == "empty" for p in pruned["edges"][0]["props"])


@pytest.mark.asyncio
async def test_chat_rejects_empty_messages_async():
    """非同步：空 messages 應被 400 拒絕。"""
    # 使用 app_module 內已 re-export 的 ChatReq 與 _chat_handler
    req = app_module.ChatReq(messages=[])
    dummy_request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    with pytest.raises(app_module.HTTPException) as exc:
        await app_module._chat_handler(req, dummy_request)
    assert exc.value.status_code == 400
    assert "messages must be a non-empty array" in str(exc.value.detail)


# ===== Additional utility function tests =====


def test_retry_once_429_no_retry_on_success():
    """Test retry_once_429 doesn't retry on success."""
    from services.gateway import utils as utils_module

    call_count = []

    def func():
        call_count.append(1)
        return "success"

    result = utils_module.retry_once_429(func)
    assert result == "success"
    assert len(call_count) == 1


def test_retry_once_429_retries_on_429():
    """Test retry_once_429 retries on 429 error."""
    from services.gateway import utils as utils_module

    call_count = []

    def func():
        call_count.append(1)
        if len(call_count) == 1:
            raise Exception("429 RateLimitError")
        return "success"

    result = utils_module.retry_once_429(func)
    assert result == "success"
    assert len(call_count) == 2


def test_retry_once_429_raises_non_429_error():
    """Test retry_once_429 raises non-429 errors immediately."""
    from services.gateway import utils as utils_module

    def func():
        raise ValueError("some error")

    with pytest.raises(ValueError):
        utils_module.retry_once_429(func)


def test_ensure_json_hint_adds_hint_when_missing():
    """Test ensure_json_hint adds hint when missing."""
    from services.gateway import utils as utils_module

    messages = [
        {"role": "user", "content": "Extract entities"},
        {"role": "assistant", "content": "Sure"},
    ]

    result = utils_module.ensure_json_hint(messages)
    # Should prepend a system message with JSON hint
    assert len(result) == 3
    assert result[0]["role"] == "system"
    assert "JSON" in result[0]["content"]


def test_ensure_json_hint_preserves_existing_hint():
    """Test ensure_json_hint preserves existing JSON hint."""
    from services.gateway import utils as utils_module

    messages = [
        {"role": "user", "content": "Extract entities"},
        {"role": "user", "content": "Reply with valid JSON"},
    ]

    result = utils_module.ensure_json_hint(messages)
    # Should not add another hint since 'json' already exists
    assert len(result) == 2


def test_extract_json_obj_with_markdown():
    """Test extracting JSON from markdown code blocks."""
    text = """
    Here's the data:
    ```json
    {"name": "Alice", "age": 30}
    ```
    """
    result = app_module._extract_json_obj(text)
    assert result == {"name": "Alice", "age": 30}


def test_extract_json_obj_with_uppercase_json():
    """Test extracting JSON with uppercase JSON marker."""
    text = '```JSON\n{"status": "ok"}\n```'
    result = app_module._extract_json_obj(text)
    assert result == {"status": "ok"}


def test_extract_json_obj_no_braces():
    """Test error when no JSON object found."""
    text = "This is just plain text without any JSON"
    with pytest.raises(ValueError, match="no_json_object_found"):
        app_module._extract_json_obj(text)


def test_extract_json_obj_nested_braces():
    """Test extracting JSON with nested objects."""
    text = 'Some text {"outer": {"inner": {"value": 42}}} more text'
    result = app_module._extract_json_obj(text)
    assert result["outer"]["inner"]["value"] == 42


def test_sha1_hash():
    """Test SHA1 hashing utility."""
    from services.gateway import utils as utils_module

    text = "test string"
    result = utils_module.sha1(text)
    assert isinstance(result, str)
    assert len(result) == 40  # SHA1 produces 40-character hex string


def test_sha1_consistency():
    """Test SHA1 produces consistent results."""
    from services.gateway import utils as utils_module

    text = "consistent data"
    hash1 = utils_module.sha1(text)
    hash2 = utils_module.sha1(text)
    assert hash1 == hash2


def test_dedup_merge_nodes_no_duplicates():
    """Test dedup_merge_nodes with no duplicate nodes."""
    nodes = [
        {"id": "n1", "type": "Person", "props": [{"key": "name", "value": "Alice"}]},
        {"id": "n2", "type": "Company", "props": [{"key": "name", "value": "Acme"}]},
    ]
    result = app_module._dedup_merge_nodes(nodes)
    assert len(result) == 2


def test_dedup_merge_nodes_merges_props():
    """Test that dedup_merge_nodes merges properties from duplicate nodes."""
    nodes = [
        {"id": "n1", "type": "Person", "props": [{"key": "name", "value": "Alice"}]},
        {"id": "n1", "type": "Person", "props": [{"key": "age", "value": 30}]},
        {"id": "n1", "type": "Person", "props": [{"key": "city", "value": "NYC"}]},
    ]
    result = app_module._dedup_merge_nodes(nodes)
    assert len(result) == 1
    assert len(result[0]["props"]) == 3
    prop_keys = {p["key"] for p in result[0]["props"]}
    assert prop_keys == {"name", "age", "city"}


def test_dedup_merge_nodes_deduplicates_same_props():
    """Test that identical props are not duplicated."""
    nodes = [
        {"id": "n1", "type": "Person", "props": [{"key": "name", "value": "Alice"}]},
        {"id": "n1", "type": "Person", "props": [{"key": "name", "value": "Alice"}]},
    ]
    result = app_module._dedup_merge_nodes(nodes)
    assert len(result) == 1
    assert len(result[0]["props"]) == 1


def test_prune_graph_removes_empty_string_props():
    """Test that prune_graph removes empty string values."""
    data = {
        "nodes": [
            {"id": "n1", "type": "Person", "props": [{"key": "name", "value": "Bob"}, {"key": "empty", "value": ""}]}
        ],
        "edges": [
            {
                "src": "n1",
                "dst": "n2",
                "type": "KNOWS",
                "props": [{"key": "since", "value": 2020}, {"key": "blank", "value": ""}],
            }
        ],
    }
    result = app_module._prune_graph(data)

    node_keys = {p["key"] for p in result["nodes"][0]["props"]}
    assert "name" in node_keys
    assert "empty" not in node_keys

    edge_keys = {p["key"] for p in result["edges"][0]["props"]}
    assert "since" in edge_keys
    assert "blank" not in edge_keys


def test_prune_graph_removes_none_values():
    """Test that prune_graph removes None values."""
    data = {
        "nodes": [
            {"id": "n1", "type": "Person", "props": [{"key": "name", "value": "Bob"}, {"key": "null", "value": None}]}
        ],
        "edges": [],
    }
    result = app_module._prune_graph(data)

    node_keys = {p["key"] for p in result["nodes"][0]["props"]}
    assert "name" in node_keys
    assert "null" not in node_keys


def test_prune_graph_removes_whitespace_only():
    """Test that prune_graph removes whitespace-only strings."""
    data = {
        "nodes": [
            {
                "id": "n1",
                "type": "Person",
                "props": [{"key": "name", "value": "Bob"}, {"key": "spaces", "value": "   "}],
            }
        ],
        "edges": [],
    }
    result = app_module._prune_graph(data)

    node_keys = {p["key"] for p in result["nodes"][0]["props"]}
    assert "name" in node_keys
    assert "spaces" not in node_keys


def test_prune_graph_keeps_zero_values():
    """Test that prune_graph keeps zero values (not considered empty)."""
    data = {
        "nodes": [
            {"id": "n1", "type": "Person", "props": [{"key": "count", "value": 0}, {"key": "score", "value": 0.0}]}
        ],
        "edges": [],
    }
    result = app_module._prune_graph(data)

    node_keys = {p["key"] for p in result["nodes"][0]["props"]}
    assert "count" in node_keys
    assert "score" in node_keys


def test_normalize_graph_shape_list_input():
    """Test normalize_graph_shape with list of nodes."""
    data = [
        {"id": "n1", "type": "Person", "props": {"name": "Alice"}},
        {"id": "n2", "type": "Company", "props": {"name": "Acme"}},
    ]
    result = app_module._normalize_graph_shape(data)

    assert "nodes" in result
    assert "edges" in result
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 0


def test_normalize_graph_shape_dict_input():
    """Test normalize_graph_shape with dict containing nodes and edges."""
    data = {
        "nodes": [{"id": "n1", "type": "Person", "props": {"name": "Bob"}}],
        "edges": [{"src": "n1", "dst": "n2", "type": "KNOWS", "props": {}}],
    }
    result = app_module._normalize_graph_shape(data)

    assert len(result["nodes"]) == 1
    assert len(result["edges"]) == 1


def test_normalize_graph_shape_alternative_field_names():
    """Test normalize_graph_shape handles alternative field names."""
    data = {
        "nodes": [
            {"node_id": "n1", "label": "Person", "props": {"name": "Charlie"}},
            {"name": "n2", "labels": ["Company"], "props": {}},
        ],
        "edges": [{"source": "n1", "target": "n2", "label": "WORKS_AT", "props": {}}],
    }
    result = app_module._normalize_graph_shape(data)

    assert len(result["nodes"]) == 2
    assert result["nodes"][0]["id"] == "n1"
    assert result["nodes"][0]["type"] == "Person"
    assert result["nodes"][1]["id"] == "n2"
    assert result["nodes"][1]["type"] == "Company"

    assert len(result["edges"]) == 1
    assert result["edges"][0]["src"] == "n1"
    assert result["edges"][0]["dst"] == "n2"
    assert result["edges"][0]["type"] == "WORKS_AT"


def test_normalize_graph_shape_kvize_props():
    """Test that normalize_graph_shape converts props to key-value format."""
    data = {"nodes": [{"id": "n1", "type": "Person", "props": {"name": "Dave", "age": 25}}], "edges": []}

    result = app_module._normalize_graph_shape(data)

    props = result["nodes"][0]["props"]
    assert isinstance(props, list)
    assert len(props) == 2
    prop_dict = {p["key"]: p["value"] for p in props}
    assert prop_dict["name"] == "Dave"
    assert prop_dict["age"] == 25
