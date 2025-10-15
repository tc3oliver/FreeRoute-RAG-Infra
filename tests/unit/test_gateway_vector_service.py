"""
Unit tests for services/gateway/services/vector_service.py
"""

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# 設定 schema 路徑必須在 import gateway modules 之前
ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))

import services.gateway.services.vector_service as vector_service_mod  # noqa: E402
from services.gateway.models import ChunkItem, IndexChunksReq, RetrieveReq, SearchReq  # noqa: E402


@pytest.fixture(autouse=True)
def patch_external(monkeypatch):
    # Mock get_litellm_client
    mock_embed = SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3]) for _ in range(2)])
    mock_litellm = SimpleNamespace(embeddings=SimpleNamespace(create=lambda model, input: mock_embed))
    monkeypatch.setattr(vector_service_mod, "get_litellm_client", lambda: mock_litellm)

    # Mock get_qdrant_client
    class MockQdrant:
        def upsert(self, collection_name, points):
            self.last_upsert = (collection_name, points)

        def search(self, collection_name, query_vector, limit, query_filter=None):
            MockResult = SimpleNamespace
            return [MockResult(id="id1", score=0.99, payload={"doc_id": "d1", "text": "t1", "metadata": {}})]

    monkeypatch.setattr(vector_service_mod, "get_qdrant_client", lambda: MockQdrant())

    # Mock ensure_qdrant_collection
    monkeypatch.setattr(vector_service_mod, "ensure_qdrant_collection", lambda qc, name, dim: None)

    # Mock qdrant_client.models
    mock_models = SimpleNamespace(PointStruct=lambda **kwargs: kwargs, Filter=SimpleNamespace(from_dict=lambda d: d))
    sys.modules["qdrant_client.models"] = mock_models

    # Mock get_neo4j_driver
    class MockSession:
        def run(self, *args, **kwargs):
            # 根據查詢內容回傳不同資料
            if "MATCH (n)" in args[0]:

                class NodeRecord:
                    def data(self):
                        return {"id": "n1", "type": "Entity", "props": {}}

                return [NodeRecord()]
            elif "MATCH (a {id: $id})-" in args[0]:

                class EdgeRecord:
                    def data(self):
                        return {
                            "src_id": "n1",
                            "src_type": "Entity",
                            "src_props": {},
                            "rel_type": "rel",
                            "rel_props": {},
                            "dst_id": "n2",
                            "dst_type": "Entity",
                            "dst_props": {},
                            "is_outgoing": True,
                        }

                return [EdgeRecord()]
            else:
                return []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockDriver:
        def session(self):
            return MockSession()

    monkeypatch.setattr(vector_service_mod, "get_neo4j_driver", lambda: MockDriver())


def test_index_chunks_success():
    svc = vector_service_mod.VectorService()
    req = IndexChunksReq(
        collection="testcol",
        chunks=[
            ChunkItem(doc_id="d1", text="abc", chunk_id=None, metadata=None),
            ChunkItem(doc_id="d2", text="def", chunk_id=None, metadata=None),
        ],
    )
    result = svc.index_chunks(req)
    assert result["ok"] is True
    assert result["upserted"] == 2
    assert result["collection"] == "testcol"


def test_index_chunks_empty():
    svc = vector_service_mod.VectorService()
    req = IndexChunksReq(collection="c", chunks=[])
    with pytest.raises(ValueError):
        svc.index_chunks(req)


def test_search_success():
    svc = vector_service_mod.VectorService()
    req = SearchReq(collection="testcol", query="hello", filters=None, top_k=1)
    result = svc.search(req)
    assert result["ok"] is True
    assert len(result["hits"]) == 1
    assert result["hits"][0]["id"] == "id1"


def test_retrieve_success():
    svc = vector_service_mod.VectorService()
    req = RetrieveReq(collection="testcol", query="hello", filters=None, top_k=1, include_subgraph=True, max_hops=1)
    result = svc.retrieve(req)
    assert result["ok"] is True
    assert isinstance(result["hits"], list)
    assert result["subgraph"] is not None
    assert "nodes" in result["subgraph"]
    assert "edges" in result["subgraph"]


def test_retrieve_no_vector_results(monkeypatch):
    svc = vector_service_mod.VectorService()

    # 讓 embeddings.create raise exception
    class BadLitellm:
        embeddings = SimpleNamespace(create=lambda *a, **k: (_ for _ in ()).throw(Exception("fail")))

    monkeypatch.setattr(vector_service_mod, "get_litellm_client", lambda: BadLitellm())

    # 讓 Qdrant search 回傳空 list
    class EmptyQdrant:
        def search(self, *a, **k):
            return []

        def upsert(self, *a, **k):
            pass

    monkeypatch.setattr(vector_service_mod, "get_qdrant_client", lambda: EmptyQdrant())
    req = RetrieveReq(collection="testcol", query="hello", filters=None, top_k=1, include_subgraph=False, max_hops=1)
    result = svc.retrieve(req)
    assert result["ok"] is True
    assert result["hits"] == []
    assert result["subgraph"] is None
