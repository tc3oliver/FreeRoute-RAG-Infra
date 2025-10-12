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


def test_chat_rejects_empty_messages():
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    with pytest.raises(app_module.HTTPException):
        app_module.chat(app_module.ChatReq(messages=[], json_mode=False), request)
