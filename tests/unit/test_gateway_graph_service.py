import os

os.environ["GRAPH_SCHEMA_PATH"] = "/root/projects/free-rag/schemas/graph_schema.json"

import json
from types import SimpleNamespace

import pytest

from services.gateway.models import KV, GraphData, GraphProbeReq, GraphQueryReq, GraphReq, GraphUpsertReq
from services.gateway.services.graph_service import GraphService


class DummyClient:
    class chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                # 模擬 LLM 回傳
                if kwargs.get("model") == "fail-model":
                    raise Exception("fail")
                if kwargs.get("messages") and "請以 JSON 物件回覆" in kwargs["messages"][0]["content"]:
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"foo": 1})))],
                        model="dummy",
                    )
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=json.dumps(
                                    {
                                        "nodes": [{"id": "n1", "type": "Person", "props": []}],
                                        "edges": [{"src": "n1", "dst": "n2", "type": "EMPLOYED_AT", "props": []}],
                                    }
                                )
                            )
                        )
                    ],
                    model="dummy",
                )


def test_probe_json(monkeypatch):
    svc = GraphService()
    monkeypatch.setattr(svc, "client", DummyClient())
    req = GraphProbeReq(model="dummy", messages=None, strict_json=True, temperature=0.1, timeout=1)
    out = svc.probe(req, "127.0.0.1")
    assert out["ok"]
    assert out["mode"] == "json"


def test_probe_text(monkeypatch):
    svc = GraphService()
    monkeypatch.setattr(svc, "client", DummyClient())
    req = GraphProbeReq(model="dummy", messages=None, strict_json=False, temperature=0.1, timeout=1)
    out = svc.probe(req, "127.0.0.1")
    assert out["ok"]
    assert out["mode"] == "text"


def test_upsert(monkeypatch):
    svc = GraphService()

    class DummyDriver:
        def session(self):
            class S:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    pass

                def run(self, *a, **k):
                    return None

            return S()

    monkeypatch.setattr("services.gateway.services.graph_service.get_neo4j_driver", lambda: DummyDriver())
    data = GraphData(
        nodes=[{"id": "n1", "type": "Person", "props": []}],
        edges=[{"src": "n1", "dst": "n2", "type": "EMPLOYED_AT", "props": []}],
    )
    req = GraphUpsertReq(data=data)
    out = svc.upsert(req)
    assert out["ok"]
    assert out["nodes"] == 1
    assert out["edges"] == 1


def test_query(monkeypatch):
    svc = GraphService()

    class DummyDriver:
        def session(self):
            class S:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    pass

                def run(self, q, **params):
                    class R:
                        def data(self):
                            return {"foo": 1}

                    return [R()]

            return S()

    monkeypatch.setattr("services.gateway.services.graph_service.get_neo4j_driver", lambda: DummyDriver())
    req = GraphQueryReq(query="MATCH (n) RETURN n", params={})
    out = svc.query(req)
    assert out["ok"]
    assert isinstance(out["records"], list)


def test_query_invalid(monkeypatch):
    svc = GraphService()
    req = GraphQueryReq(query="CREATE (n)", params={})
    with pytest.raises(ValueError):
        svc.query(req)


def test_is_single_error_node():
    d = {"nodes": [{"id": "err", "type": "error"}], "edges": []}
    assert GraphService._is_single_error_node(d)
    d2 = {"nodes": [{"id": "n1", "type": "Person"}], "edges": []}
    assert not GraphService._is_single_error_node(d2)
