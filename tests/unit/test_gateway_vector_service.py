# 頂層 mock class定義與所有 import
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import services.gateway.services.async_vector_service as vector_service_mod
from services.gateway.models import ChunkItem, IndexChunksReq, RetrieveReq, SearchReq


class MockEmbeddings:
    async def create(self, model, input):
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3]) for _ in range(2)])


class MockLitellm:
    embeddings = MockEmbeddings()


# 設定 schema 路徑必須在 import gateway modules 之前
ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))


@pytest.mark.asyncio
async def test_multi_tenant_collection_isolation():
    from services.gateway.repositories import get_tenant_collection_name

    tenant_a = "tenantA"
    tenant_b = "tenantB"
    base_collection = "testcol"
    col_a = get_tenant_collection_name(tenant_a, base_collection)
    col_b = get_tenant_collection_name(tenant_b, base_collection)
    assert col_a != col_b


@pytest.mark.asyncio
async def test_delete_vector(monkeypatch):
    svc = vector_service_mod.AsyncVectorService()

    # Mock Qdrant delete_collection
    class MockQdrant:
        def __init__(self):
            self.deleted = None

        async def delete_collection(self, collection_name):
            self.deleted = collection_name
            return None

    async def get_async_qdrant_client():
        return MockQdrant()

    monkeypatch.setattr(vector_service_mod, "get_async_qdrant_client", get_async_qdrant_client)
    # 執行刪除並驗證
    await svc.delete_vector("testcol")


@pytest.fixture(autouse=True)
def patch_external(monkeypatch):
    async def get_async_litellm_client():
        return MockLitellm()

    monkeypatch.setattr(vector_service_mod, "get_async_litellm_client", get_async_litellm_client)

    class MockQdrant:
        async def upsert(self, collection_name, points):
            self.last_upsert = (collection_name, points)

        async def search(self, collection_name, query_vector, limit, query_filter=None):
            MockResult = SimpleNamespace
            return [MockResult(id="id1", score=0.99, payload={"doc_id": "d1", "text": "t1", "metadata": {}})]

        async def delete_collection(self, collection_name):
            self.deleted = collection_name
            return None

    async def get_async_qdrant_client():
        return MockQdrant()

    monkeypatch.setattr(vector_service_mod, "get_async_qdrant_client", get_async_qdrant_client)

    async def ensure_qdrant_collection_async(qc, name, dim, **kwargs):
        return None

    monkeypatch.setattr(vector_service_mod, "ensure_qdrant_collection_async", ensure_qdrant_collection_async)

    mock_models = SimpleNamespace(PointStruct=lambda **kwargs: kwargs, Filter=SimpleNamespace(from_dict=lambda d: d))
    sys.modules["qdrant_client.models"] = mock_models

    class MockSession:
        async def run(self, *args, **kwargs):
            if "MATCH (n)" in args[0]:

                class NodeRecord:
                    def data(self):
                        return {"id": "n1", "type": "Entity", "props": {}}

                async def gen():
                    yield NodeRecord()

                return gen()
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

                async def gen():
                    yield EdgeRecord()

                return gen()
            else:

                async def gen():
                    return
                    yield  # never yields

                return gen()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockDriver:
        def session(self):
            return MockSession()

    async def get_async_neo4j_driver():
        return MockDriver()

    monkeypatch.setattr(vector_service_mod, "get_async_neo4j_driver", get_async_neo4j_driver)


@pytest.mark.asyncio
async def test_index_chunks_value_error():
    svc = vector_service_mod.AsyncVectorService()
    req = None  # 或者根據實際情境給予不合法的 req
    with pytest.raises(Exception):
        await svc.index_chunks(req)


@pytest.mark.asyncio
async def test_index_chunks_success():
    svc = vector_service_mod.AsyncVectorService()
    req = IndexChunksReq(
        collection="testcol",
        chunks=[
            ChunkItem(doc_id="d1", text="abc", chunk_id=None, metadata=None),
            ChunkItem(doc_id="d2", text="def", chunk_id=None, metadata=None),
        ],
    )
    result = await svc.index_chunks(req)
    assert "ok" in result
    assert "upserted" in result
    assert "collection" in result


@pytest.mark.asyncio
async def test_index_chunks_empty():
    svc = vector_service_mod.AsyncVectorService()
    req = IndexChunksReq(collection="c", chunks=[])
    with pytest.raises(ValueError):
        await svc.index_chunks(req)


@pytest.mark.asyncio
async def test_search_success():
    svc = vector_service_mod.AsyncVectorService()
    req = SearchReq(collection="testcol", query="hello", filters=None, top_k=1)
    result = await svc.search(req)
    assert result["ok"] is True
    assert len(result["hits"]) == 1
    assert result["hits"][0]["id"] == "id1"


@pytest.mark.asyncio
async def test_retrieve_success():
    svc = vector_service_mod.AsyncVectorService()
    req = RetrieveReq(collection="testcol", query="hello", filters=None, top_k=1, include_subgraph=True, max_hops=1)
    result = await svc.retrieve(req)
    assert result["ok"] is True
    assert isinstance(result["hits"], list)
    assert result["subgraph"] is None or ("nodes" in result["subgraph"] and "edges" in result["subgraph"])


@pytest.mark.asyncio
async def test_retrieve_no_vector_results(monkeypatch):
    svc = vector_service_mod.AsyncVectorService()

    # 讓 embeddings.create raise exception
    class BadLitellm:
        class embeddings:
            @staticmethod
            async def create(*a, **k):
                raise Exception("fail")

    async def _get_bad_llm():
        return BadLitellm()

    monkeypatch.setattr(vector_service_mod, "get_async_litellm_client", _get_bad_llm)

    # 讓 Qdrant search 回傳空 list
    class EmptyQdrant:
        async def search(self, *a, **k):
            return []

        async def upsert(self, *a, **k):
            pass

    async def _get_empty_qdrant():
        return EmptyQdrant()

    monkeypatch.setattr(vector_service_mod, "get_async_qdrant_client", _get_empty_qdrant)
    req = RetrieveReq(collection="testcol", query="hello", filters=None, top_k=1, include_subgraph=False, max_hops=1)
    result = await svc.retrieve(req)
    assert result["ok"] is True
    assert result["hits"] == []
    assert result["subgraph"] is None


@pytest.mark.asyncio
async def test_search_empty_query():
    """Test that empty query raises ValueError."""
    svc = vector_service_mod.AsyncVectorService()
    req = SearchReq(collection="testcol", query="", top_k=5)
    with pytest.raises(ValueError, match="query must be non-empty"):
        await svc.search(req)


@pytest.mark.asyncio
async def test_search_whitespace_query():
    """Test that whitespace-only query raises ValueError."""
    svc = vector_service_mod.AsyncVectorService()
    req = SearchReq(collection="testcol", query="   ", top_k=5)
    with pytest.raises(ValueError, match="query must be non-empty"):
        await svc.search(req)


@pytest.mark.asyncio
async def test_retrieve_empty_query():
    """Test that empty query raises ValueError."""
    svc = vector_service_mod.AsyncVectorService()
    req = RetrieveReq(collection="testcol", query="", top_k=5)
    with pytest.raises(ValueError, match="query must be non-empty"):
        await svc.retrieve(req)


@pytest.mark.asyncio
async def test_retrieve_whitespace_query():
    """Test that whitespace-only query raises ValueError."""
    svc = vector_service_mod.AsyncVectorService()
    req = RetrieveReq(collection="testcol", query="  \n\t  ", top_k=5)
    with pytest.raises(ValueError, match="query must be non-empty"):
        await svc.retrieve(req)
