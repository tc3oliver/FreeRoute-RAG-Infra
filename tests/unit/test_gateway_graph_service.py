import os

os.environ["GRAPH_SCHEMA_PATH"] = "/root/projects/free-rag/schemas/graph_schema.json"

import json
import os
from types import SimpleNamespace

import pytest

import services.gateway.services.async_graph_service as async_graph_service_mod
from services.gateway.models import KV, GraphData, GraphProbeReq, GraphQueryReq, GraphReq, GraphUpsertReq


class DummyClient:
    class chat:
        class completions:
            @staticmethod
            async def create(**kwargs):
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


@pytest.mark.asyncio
async def test_probe_json(monkeypatch):
    os.environ["NEO4J_URI"] = "bolt://dummy"
    os.environ["NEO4J_PASSWORD"] = "dummy"
    svc = async_graph_service_mod.AsyncGraphService()
    monkeypatch.setattr(svc, "client", DummyClient())

    async def dummy_driver():
        class Dummy:
            pass

        return Dummy()

    monkeypatch.setattr(async_graph_service_mod, "get_async_neo4j_driver", dummy_driver)
    req = GraphProbeReq(model="dummy", messages=None, strict_json=True, temperature=0.1, timeout=1)
    out = await svc.probe(req, "127.0.0.1")
    assert out["ok"]
    assert out["mode"] == "json"


@pytest.mark.asyncio
async def test_probe_text(monkeypatch):
    os.environ["NEO4J_URI"] = "bolt://dummy"
    os.environ["NEO4J_PASSWORD"] = "dummy"
    svc = async_graph_service_mod.AsyncGraphService()
    monkeypatch.setattr(svc, "client", DummyClient())

    async def dummy_driver():
        class Dummy:
            pass

        return Dummy()

    monkeypatch.setattr(async_graph_service_mod, "get_async_neo4j_driver", dummy_driver)
    req = GraphProbeReq(model="dummy", messages=None, strict_json=False, temperature=0.1, timeout=1)
    out = await svc.probe(req, "127.0.0.1")
    assert out["ok"]
    assert out["mode"] == "text"


@pytest.mark.asyncio
async def test_upsert(monkeypatch):
    svc = async_graph_service_mod.AsyncGraphService()

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def run(self, *a, **k):
            return None

    class DummyDriver:
        def session(self):
            return DummySession()

    async def dummy_driver():
        return DummyDriver()

    monkeypatch.setattr(async_graph_service_mod, "get_async_neo4j_driver", dummy_driver)
    data = GraphData(
        nodes=[{"id": "n1", "type": "Person", "props": []}],
        edges=[{"src": "n1", "dst": "n2", "type": "EMPLOYED_AT", "props": []}],
    )
    req = GraphUpsertReq(data=data)
    out = await svc.upsert(req)
    assert out["ok"]
    assert out["nodes"] == 1
    assert out["edges"] == 1


@pytest.mark.asyncio
async def test_query(monkeypatch):
    svc = async_graph_service_mod.AsyncGraphService()

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def run(self, q, **params):
            class R:
                def data(self):
                    return {"foo": 1}

            async def gen():
                yield R()

            return gen()

    class DummyDriver:
        def session(self):
            return DummySession()

    async def dummy_driver():
        return DummyDriver()

    monkeypatch.setattr(async_graph_service_mod, "get_async_neo4j_driver", dummy_driver)
    req = GraphQueryReq(query="MATCH (n) RETURN n", params={})
    out = await svc.query(req)
    assert out["ok"]
    assert isinstance(out["records"], list)


@pytest.mark.asyncio
async def test_query_invalid(monkeypatch):
    svc = async_graph_service_mod.AsyncGraphService()
    req = GraphQueryReq(query="CREATE (n)", params={})
    with pytest.raises(ValueError):
        await svc.query(req)


def test_is_single_error_node():
    d = {"nodes": [{"id": "err", "type": "error"}], "edges": []}
    assert async_graph_service_mod.AsyncGraphService._is_single_error_node(d)
    d2 = {"nodes": [{"id": "n1", "type": "Person"}], "edges": []}
    assert not async_graph_service_mod.AsyncGraphService._is_single_error_node(d2)
