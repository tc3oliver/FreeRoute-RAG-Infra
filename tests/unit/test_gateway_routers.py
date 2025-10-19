"""
Unit tests for services/gateway/routers/
Testing router endpoint logic and error handling
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

# Setup schema path before any gateway imports
ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))


class TestChatRouter:
    """Test chat router endpoints."""

    @pytest.mark.asyncio
    async def test_chat_endpoint_success(self, monkeypatch):
        """Test successful chat request."""
        from services.gateway.models import ChatReq
        from services.gateway.routers.chat import chat
        from services.gateway.services import AsyncChatService

        async def mock_chat(req, client_ip):
            return {"ok": True, "data": "response", "meta": {"model": "gpt-4"}}

        mock_service = SimpleNamespace(chat=mock_chat)

        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        req = ChatReq(messages=[{"role": "user", "content": "Hello"}])

        result = await chat(req, request, service=mock_service)

        assert result["ok"] is True
        assert result["data"] == "response"

    @pytest.mark.asyncio
    async def test_chat_endpoint_empty_messages(self, monkeypatch):
        """Test chat with empty messages raises 400."""
        from services.gateway.models import ChatReq
        from services.gateway.routers.chat import chat

        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        req = ChatReq(messages=[])

        with pytest.raises(HTTPException) as exc:
            await chat(req, request, service=None)

        assert exc.value.status_code == 400
        assert "messages must be a non-empty array" in exc.value.detail

    @pytest.mark.asyncio
    async def test_chat_endpoint_service_exception(self, monkeypatch):
        """Test chat service exception raises 502."""
        from services.gateway.models import ChatReq
        from services.gateway.routers.chat import chat

        async def mock_chat(req, client_ip):
            raise Exception("upstream error")

        mock_service = SimpleNamespace(chat=mock_chat)

        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        req = ChatReq(messages=[{"role": "user", "content": "Hi"}])

        with pytest.raises(HTTPException) as exc:
            await chat(req, request, service=mock_service)

        assert exc.value.status_code == 502
        assert "upstream_chat_error" in exc.value.detail

    @pytest.mark.asyncio
    async def test_embed_endpoint_success(self):
        """Test successful embed request."""
        from services.gateway.models import EmbedReq
        from services.gateway.routers.chat import embed

        async def mock_embed(req):
            return {"ok": True, "vectors": [[0.1, 0.2]], "dim": 2}

        mock_service = SimpleNamespace(embed=mock_embed)

        req = EmbedReq(texts=["hello", "world"])
        result = await embed(req, service=mock_service)

        assert result["ok"] is True
        assert len(result["vectors"]) == 1
        assert result["dim"] == 2

    @pytest.mark.asyncio
    async def test_embed_endpoint_service_exception(self):
        """Test embed service exception raises 502."""
        from services.gateway.models import EmbedReq
        from services.gateway.routers.chat import embed

        async def mock_embed(req):
            raise Exception("embed error")

        mock_service = SimpleNamespace(embed=mock_embed)

        req = EmbedReq(texts=["test"])

        with pytest.raises(HTTPException) as exc:
            await embed(req, service=mock_service)

        assert exc.value.status_code == 502
        assert "embed_error" in exc.value.detail

    @pytest.mark.asyncio
    async def test_rerank_endpoint_success(self, monkeypatch):
        """Test successful rerank request."""
        from services.gateway.models import RerankReq
        from services.gateway.routers import chat

        async def mock_call_reranker(query, documents, top_n):
            return {"results": [{"index": 0, "score": 0.9, "text": "doc1"}]}

        monkeypatch.setattr("services.gateway.routers.chat.call_reranker_async", mock_call_reranker)

        req = RerankReq(query="test", documents=["doc1", "doc2"])
        result = await chat.rerank(req)

        assert result["ok"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["score"] == 0.9

    @pytest.mark.asyncio
    async def test_rerank_endpoint_exception(self, monkeypatch):
        """Test rerank exception raises 502."""
        from services.gateway.models import RerankReq
        from services.gateway.routers import chat

        async def mock_call_reranker(query, documents, top_n):
            raise Exception("reranker unavailable")

        monkeypatch.setattr("services.gateway.routers.chat.call_reranker_async", mock_call_reranker)

        req = RerankReq(query="test", documents=["doc"])

        with pytest.raises(HTTPException) as exc:
            await chat.rerank(req)

        assert exc.value.status_code == 502
        assert "rerank_error" in exc.value.detail


class TestGraphRouter:
    """Test graph router endpoints."""

    @pytest.mark.asyncio
    async def test_graph_probe_success(self):
        """Test successful graph probe."""
        from services.gateway.models import GraphProbeReq
        from services.gateway.routers.graph import graph_probe

        async def mock_probe(req, client_ip):
            return {"ok": True, "mode": "json", "data": {"test": "data"}, "provider": "gpt-4"}

        mock_service = SimpleNamespace(probe=mock_probe)

        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        req = GraphProbeReq(model="graph-extractor")

        result = await graph_probe(req, request, service=mock_service)

        assert result["ok"] is True
        assert result["mode"] == "json"

    @pytest.mark.asyncio
    async def test_graph_probe_exception(self):
        """Test graph probe exception raises 502."""
        from services.gateway.models import GraphProbeReq
        from services.gateway.routers.graph import graph_probe

        async def mock_probe(req, client_ip):
            raise Exception("probe failed")

        mock_service = SimpleNamespace(probe=mock_probe)

        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        req = GraphProbeReq(model="test-model")

        with pytest.raises(HTTPException) as exc:
            await graph_probe(req, request, service=mock_service)

        assert exc.value.status_code == 502
        assert exc.value.detail["error"] == "upstream_probe_error"

    @pytest.mark.asyncio
    async def test_graph_extract_success(self):
        """Test successful graph extraction."""
        from services.gateway.models import GraphData, GraphReq
        from services.gateway.routers.graph import graph_extract

        mock_data = GraphData(nodes=[], edges=[])

        async def mock_extract(req, client_ip):
            return {"ok": True, "data": mock_data, "provider": "gpt-4", "schema_hash": "abc"}

        mock_service = SimpleNamespace(extract=mock_extract)

        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        req = GraphReq(context="Some text")

        result = await graph_extract(req, request, service=mock_service)

        assert result["ok"] is True
        assert result["provider"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_graph_extract_value_error(self):
        """Test graph extract with ValueError raises 400."""
        from services.gateway.models import GraphReq
        from services.gateway.routers.graph import graph_extract

        async def mock_extract(req, client_ip):
            raise ValueError("invalid input")

        mock_service = SimpleNamespace(extract=mock_extract)

        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        req = GraphReq(context="text")

        with pytest.raises(HTTPException) as exc:
            await graph_extract(req, request, service=mock_service)

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_graph_upsert_success(self):
        """Test successful graph upsert."""
        from services.gateway.models import GraphData, GraphUpsertReq
        from services.gateway.routers.graph import graph_upsert

        async def mock_upsert(req):
            return {"ok": True, "nodes": 5, "edges": 3}

        mock_service = SimpleNamespace(upsert=mock_upsert)

        req = GraphUpsertReq(data=GraphData(nodes=[], edges=[]))
        result = await graph_upsert(req, service=mock_service)

        assert result["ok"] is True
        assert result["nodes"] == 5
        assert result["edges"] == 3

    @pytest.mark.asyncio
    async def test_graph_upsert_runtime_error(self):
        """Test graph upsert with RuntimeError raises 503."""
        from services.gateway.models import GraphData, GraphUpsertReq
        from services.gateway.routers.graph import graph_upsert

        async def mock_upsert(req):
            raise RuntimeError("neo4j unavailable")

        mock_service = SimpleNamespace(upsert=mock_upsert)

        req = GraphUpsertReq(data=GraphData(nodes=[], edges=[]))

        with pytest.raises(HTTPException) as exc:
            await graph_upsert(req, service=mock_service)

        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_graph_query_success(self):
        """Test successful graph query."""
        from services.gateway.models import GraphQueryReq
        from services.gateway.routers.graph import graph_query

        async def mock_query(req):
            return {"ok": True, "records": [{"n": {"id": "1"}}]}

        mock_service = SimpleNamespace(query=mock_query)

        req = GraphQueryReq(query="MATCH (n) RETURN n")
        result = await graph_query(req, service=mock_service)

        assert result["ok"] is True
        assert len(result["records"]) == 1

    @pytest.mark.asyncio
    async def test_graph_query_value_error(self):
        """Test graph query with ValueError raises 400."""
        from services.gateway.models import GraphQueryReq
        from services.gateway.routers.graph import graph_query

        async def mock_query(req):
            raise ValueError("invalid query")

        mock_service = SimpleNamespace(query=mock_query)

        req = GraphQueryReq(query="INVALID")

        with pytest.raises(HTTPException) as exc:
            await graph_query(req, service=mock_service)

        assert exc.value.status_code == 400


class TestVectorRouter:
    """Test vector router endpoints."""

    @pytest.mark.asyncio
    async def test_index_chunks_success(self):
        """Test successful chunk indexing."""
        from services.gateway.models import ChunkItem, IndexChunksReq
        from services.gateway.routers.vector import index_chunks

        async def mock_index_chunks(req):
            return {"ok": True, "upserted": 2, "dim": 768, "collection": "chunks"}

        mock_service = SimpleNamespace(index_chunks=mock_index_chunks)

        req = IndexChunksReq(chunks=[ChunkItem(doc_id="doc1", text="text1"), ChunkItem(doc_id="doc2", text="text2")])

        result = await index_chunks(req, service=mock_service)

        assert result["ok"] is True
        assert result["upserted"] == 2
        assert result["dim"] == 768

    @pytest.mark.asyncio
    async def test_index_chunks_value_error(self):
        """Test index chunks with ValueError raises 400."""
        from services.gateway.models import IndexChunksReq
        from services.gateway.routers.vector import index_chunks

        async def mock_index_chunks(req):
            raise ValueError("chunks required")

        mock_service = SimpleNamespace(index_chunks=mock_index_chunks)

        req = IndexChunksReq(chunks=[])

        with pytest.raises(HTTPException) as exc:
            await index_chunks(req, service=mock_service)

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_index_chunks_runtime_error(self):
        """Test index chunks with RuntimeError raises 503."""
        from services.gateway.models import ChunkItem, IndexChunksReq
        from services.gateway.routers.vector import index_chunks

        async def mock_index_chunks(req):
            raise RuntimeError("qdrant unavailable")

        mock_service = SimpleNamespace(index_chunks=mock_index_chunks)

        req = IndexChunksReq(chunks=[ChunkItem(doc_id="doc1", text="text")])

        with pytest.raises(HTTPException) as exc:
            await index_chunks(req, service=mock_service)

        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_search_success(self):
        """Test successful vector search."""
        from services.gateway.models import SearchReq
        from services.gateway.routers.vector import search

        async def mock_search(req):
            return {"ok": True, "hits": [{"id": "1", "score": 0.9, "payload": {}}]}

        mock_service = SimpleNamespace(search=mock_search)

        req = SearchReq(query="test query")
        result = await search(req, service=mock_service)

        assert result["ok"] is True
        assert len(result["hits"]) == 1

    @pytest.mark.asyncio
    async def test_search_runtime_error(self):
        """Test search with RuntimeError raises 503."""
        from services.gateway.models import SearchReq
        from services.gateway.routers.vector import search

        async def mock_search(req):
            raise RuntimeError("qdrant down")

        mock_service = SimpleNamespace(search=mock_search)

        req = SearchReq(query="test")

        with pytest.raises(HTTPException) as exc:
            await search(req, service=mock_service)

        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_retrieve_success(self):
        """Test successful hybrid retrieval."""
        from services.gateway.models import RetrieveReq
        from services.gateway.routers.vector import retrieve

        async def mock_retrieve(req):
            return {"ok": True, "hits": [], "subgraph": None, "query_time_ms": 100}

        mock_service = SimpleNamespace(retrieve=mock_retrieve)

        req = RetrieveReq(query="test")
        result = await retrieve(req, service=mock_service)

        assert result["ok"] is True
        assert result["query_time_ms"] == 100

    @pytest.mark.asyncio
    async def test_retrieve_exception(self):
        """Test retrieve exception raises 500."""
        from services.gateway.models import RetrieveReq
        from services.gateway.routers.vector import retrieve

        async def mock_retrieve(req):
            raise Exception("retrieval failed")

        mock_service = SimpleNamespace(retrieve=mock_retrieve)

        req = RetrieveReq(query="test")

        with pytest.raises(HTTPException) as exc:
            await retrieve(req, service=mock_service)

        assert exc.value.status_code == 500


class TestMetaRouter:
    """Test meta router endpoints."""

    def test_health_endpoint(self):
        """Test health endpoint."""
        from services.gateway.routers.meta import health

        result = health()

        assert result["ok"] is True

    def test_version_endpoint(self):
        """Test version endpoint."""
        from services.gateway.routers.meta import version

        result = version()

        assert "version" in result
        assert isinstance(result["version"], str)

    def test_whoami_endpoint(self):
        """Test whoami endpoint."""
        from services.gateway.routers.meta import whoami

        result = whoami()

        assert "app_version" in result
        assert "litellm_base" in result
        assert "entrypoints" in result
        assert "schema_hash" in result
        assert "graph_defaults" in result
        assert isinstance(result["entrypoints"], list)
        assert isinstance(result["graph_defaults"], dict)

    def test_metrics_endpoint_disabled(self, monkeypatch):
        """Test metrics endpoint when disabled."""
        monkeypatch.setattr("services.gateway.routers.meta.generate_latest", None)

        from services.gateway.routers.meta import metrics

        result = metrics()

        assert result.status_code == 204

    def test_metrics_endpoint_enabled_but_flag_false(self, monkeypatch):
        """Test metrics endpoint when generate_latest exists but metrics disabled."""

        def mock_generate():
            return b"metrics data"

        monkeypatch.setattr("services.gateway.routers.meta.generate_latest", mock_generate)

        # Mock the module loading to return METRICS_ENABLED=False
        import sys
        from types import ModuleType

        mock_app_module = ModuleType("services.gateway.app")
        mock_app_module.METRICS_ENABLED = False
        sys.modules["services.gateway.app"] = mock_app_module

        from services.gateway.routers.meta import metrics

        result = metrics()

        assert result.status_code == 204
