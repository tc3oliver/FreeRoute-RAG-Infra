"""
Unit tests for Async Services.

Tests AsyncChatService, AsyncVectorService, and AsyncGraphService.
"""

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set GRAPH_SCHEMA_PATH environment variable before any imports
_test_dir = Path(__file__).parent.parent.parent
_schema_path = _test_dir / "schemas" / "graph_schema.json"

# Create a temporary schema if it doesn't exist (for pre-commit environment)
if not _schema_path.exists():
    import tempfile

    _schema_path = Path(tempfile.mktemp(suffix=".json"))
    _schema_path.write_text(json.dumps({"type": "object", "properties": {}}))

os.environ["GRAPH_SCHEMA_PATH"] = str(_schema_path)

# Import after setting environment variable
from services.gateway.models import (  # noqa: E402
    ChatReq,
    ChunkItem,
    EmbedReq,
    GraphData,
    GraphProbeReq,
    GraphQueryReq,
    GraphReq,
    GraphUpsertReq,
    IndexChunksReq,
    RetrieveReq,
    SearchReq,
)
from services.gateway.services import AsyncChatService  # noqa: E402
from services.gateway.services.async_graph_service import AsyncGraphService  # noqa: E402
from services.gateway.services.async_vector_service import AsyncVectorService  # noqa: E402


class TestAsyncChatService:
    """Test suite for AsyncChatService."""

    @pytest.fixture
    def chat_service(self):
        """Create an AsyncChatService instance for testing."""
        return AsyncChatService()

    @pytest.fixture
    def mock_async_litellm_client(self):
        """Mock async LiteLLM client."""
        client = MagicMock()
        client.chat = MagicMock()
        client.chat.completions = MagicMock()
        client.chat.completions.create = AsyncMock()
        client.embeddings = MagicMock()
        client.embeddings.create = AsyncMock()
        return client

    # =========================================================================
    # Test: chat() - 基本聊天功能
    # =========================================================================

    @pytest.mark.asyncio
    async def test_chat_success(self, chat_service, mock_async_litellm_client):
        """Test successful chat completion."""
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello!"))]
        mock_response.model = "gpt-4"
        mock_async_litellm_client.chat.completions.create.return_value = mock_response

        with patch(
            "services.gateway.services.chat_service.get_async_litellm_client",
            return_value=mock_async_litellm_client,
        ):
            req = ChatReq(messages=[{"role": "user", "content": "Hi"}])
            result = await chat_service.chat(req, client_ip="127.0.0.1")

        assert result["ok"] is True
        assert result["data"] == "Hello!"
        assert result["meta"]["model"] == "gpt-4"
        mock_async_litellm_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_with_custom_model(self, chat_service, mock_async_litellm_client):
        """Test chat with custom model."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
        mock_response.model = "claude-3"
        mock_async_litellm_client.chat.completions.create.return_value = mock_response

        with patch(
            "services.gateway.services.chat_service.get_async_litellm_client",
            return_value=mock_async_litellm_client,
        ):
            req = ChatReq(messages=[{"role": "user", "content": "Test"}], model="claude-3")
            result = await chat_service.chat(req, client_ip="127.0.0.1")

        assert result["ok"] is True
        assert result["meta"]["model"] == "claude-3"

    @pytest.mark.asyncio
    async def test_chat_exception_handling(self, chat_service, mock_async_litellm_client):
        """Test chat exception handling."""
        mock_async_litellm_client.chat.completions.create.side_effect = Exception("API Error")

        with patch(
            "services.gateway.services.chat_service.get_async_litellm_client",
            return_value=mock_async_litellm_client,
        ):
            req = ChatReq(messages=[{"role": "user", "content": "Test"}])

            with pytest.raises(Exception, match="API Error"):
                await chat_service.chat(req, client_ip="127.0.0.1")

    # =========================================================================
    # Test: embed() - 嵌入生成
    # =========================================================================

    @pytest.mark.asyncio
    async def test_embed_success(self, chat_service, mock_async_litellm_client):
        """Test successful embedding generation."""
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_async_litellm_client.embeddings.create.return_value = mock_response

        with patch(
            "services.gateway.services.chat_service.get_async_litellm_client",
            return_value=mock_async_litellm_client,
        ):
            req = EmbedReq(texts=["Hello world"])
            result = await chat_service.embed(req)

        assert result["ok"] is True
        assert result["vectors"] == [[0.1, 0.2, 0.3]]
        assert result["dim"] == 3

    @pytest.mark.asyncio
    async def test_embed_multiple_texts(self, chat_service, mock_async_litellm_client):
        """Test embedding multiple texts."""
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2]),
            MagicMock(embedding=[0.3, 0.4]),
        ]
        mock_async_litellm_client.embeddings.create.return_value = mock_response

        with patch(
            "services.gateway.services.chat_service.get_async_litellm_client",
            return_value=mock_async_litellm_client,
        ):
            req = EmbedReq(texts=["Text 1", "Text 2"])
            result = await chat_service.embed(req)

        assert result["ok"] is True
        assert len(result["vectors"]) == 2
        assert result["dim"] == 2


class TestAsyncVectorService:
    """Test suite for AsyncVectorService."""

    @pytest.fixture
    def vector_service(self):
        """Create an AsyncVectorService instance for testing."""
        return AsyncVectorService()

    @pytest.fixture
    def mock_async_clients(self):
        """Mock async clients for vector service."""
        llm_client = MagicMock()
        llm_client.embeddings = MagicMock()
        llm_client.embeddings.create = AsyncMock()

        qdrant_client = MagicMock()
        qdrant_client.upsert = AsyncMock()
        qdrant_client.search = AsyncMock()

        neo4j_driver = MagicMock()

        return {
            "llm": llm_client,
            "qdrant": qdrant_client,
            "neo4j": neo4j_driver,
        }

    # =========================================================================
    # Test: index_chunks() - 批量索引
    # =========================================================================

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not importlib.util.find_spec("qdrant_client"),
        reason="qdrant_client not installed in test environment",
    )
    async def test_index_chunks_success(self, vector_service, mock_async_clients):
        """Test successful chunk indexing."""
        # Mock embedding response
        mock_embed_response = MagicMock()
        mock_embed_response.data = [
            MagicMock(embedding=[0.1, 0.2, 0.3]),
            MagicMock(embedding=[0.4, 0.5, 0.6]),
        ]
        mock_async_clients["llm"].embeddings.create.return_value = mock_embed_response

        with (
            patch(
                "services.gateway.services.async_vector_service.get_async_litellm_client",
                return_value=mock_async_clients["llm"],
            ),
            patch(
                "services.gateway.services.async_vector_service.get_async_qdrant_client",
                return_value=mock_async_clients["qdrant"],
            ),
            patch(
                "services.gateway.services.async_vector_service.get_async_neo4j_driver",
                return_value=mock_async_clients["neo4j"],
            ),
            patch(
                "services.gateway.services.async_vector_service.ensure_qdrant_collection_async",
                new_callable=AsyncMock,
            ),
        ):
            req = IndexChunksReq(
                chunks=[
                    ChunkItem(doc_id="doc1", chunk_id="c1", text="Text 1"),
                    ChunkItem(doc_id="doc1", chunk_id="c2", text="Text 2"),
                ]
            )
            result = await vector_service.index_chunks(req)

        assert result["ok"] is True
        assert result["upserted"] == 2
        assert result["dim"] == 3
        mock_async_clients["qdrant"].upsert.assert_called_once()

    # =========================================================================
    # Test: search() - 向量搜索
    # =========================================================================

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not importlib.util.find_spec("qdrant_client"),
        reason="qdrant_client not installed in test environment",
    )
    async def test_search_success(self, vector_service, mock_async_clients):
        """Test successful vector search."""
        # Mock embedding
        mock_embed_response = MagicMock()
        mock_embed_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_async_clients["llm"].embeddings.create.return_value = mock_embed_response

        # Mock search results
        mock_search_result = [
            MagicMock(id="1", score=0.95, payload={"text": "Result 1"}),
            MagicMock(id="2", score=0.85, payload={"text": "Result 2"}),
        ]
        mock_async_clients["qdrant"].search.return_value = mock_search_result

        with (
            patch(
                "services.gateway.services.async_vector_service.get_async_litellm_client",
                return_value=mock_async_clients["llm"],
            ),
            patch(
                "services.gateway.services.async_vector_service.get_async_qdrant_client",
                return_value=mock_async_clients["qdrant"],
            ),
            patch(
                "services.gateway.services.async_vector_service.get_async_neo4j_driver",
                return_value=mock_async_clients["neo4j"],
            ),
        ):
            req = SearchReq(query="test query", top_k=2)
            result = await vector_service.search(req)

        assert result["ok"] is True
        assert len(result["hits"]) == 2
        assert result["hits"][0]["score"] == 0.95

    # =========================================================================
    # Test: retrieve() - 並行混合檢索
    # =========================================================================

    @pytest.mark.asyncio
    async def test_retrieve_parallel_execution(self, vector_service, mock_async_clients):
        """Test parallel retrieval (vector search + graph expansion)."""
        from services.gateway.models import RetrieveHit

        # Mock _vector_search to return search results
        async def mock_vector_search(req):
            return [RetrieveHit(text="Result text", metadata={"chunk_id": "c1"}, citations=[], score=0.95)]

        # Mock graph expansion (return None for simplicity)
        async def mock_expand_graph(query, max_hops):
            return None

        with (
            patch(
                "services.gateway.services.async_vector_service.get_async_litellm_client",
                return_value=mock_async_clients["llm"],
            ),
            patch(
                "services.gateway.services.async_vector_service.get_async_qdrant_client",
                return_value=mock_async_clients["qdrant"],
            ),
            patch(
                "services.gateway.services.async_vector_service.get_async_neo4j_driver",
                return_value=mock_async_clients["neo4j"],
            ),
            patch.object(vector_service, "_vector_search", new=mock_vector_search),
            patch.object(vector_service, "_expand_graph_neighborhood", new=mock_expand_graph),
        ):
            req = RetrieveReq(query="test query", include_subgraph=True)
            result = await vector_service.retrieve(req)

        assert result["ok"] is True
        assert len(result["hits"]) == 1
        assert "query_time_ms" in result


class TestAsyncGraphService:
    """Test suite for AsyncGraphService."""

    @pytest.fixture
    def graph_service(self):
        """Create an AsyncGraphService instance for testing."""
        return AsyncGraphService()

    @pytest.fixture
    def mock_async_clients(self):
        """Mock async clients for graph service."""
        llm_client = MagicMock()
        llm_client.chat = MagicMock()
        llm_client.chat.completions = MagicMock()
        llm_client.chat.completions.create = AsyncMock()

        neo4j_driver = MagicMock()
        neo4j_session = MagicMock()
        neo4j_session.__aenter__ = AsyncMock(return_value=neo4j_session)
        neo4j_session.__aexit__ = AsyncMock()
        neo4j_session.run = AsyncMock()
        neo4j_driver.session = MagicMock(return_value=neo4j_session)

        return {
            "llm": llm_client,
            "neo4j": neo4j_driver,
        }

    # =========================================================================
    # Test: probe() - 供應商探測
    # =========================================================================

    @pytest.mark.asyncio
    async def test_probe_success(self, graph_service, mock_async_clients):
        """Test successful provider probe."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"test": "data"}'))]
        mock_response.model = "gpt-4"
        mock_async_clients["llm"].chat.completions.create.return_value = mock_response

        with (
            patch(
                "services.gateway.services.async_graph_service.get_async_litellm_client",
                return_value=mock_async_clients["llm"],
            ),
            patch(
                "services.gateway.services.async_graph_service.get_async_neo4j_driver",
                return_value=mock_async_clients["neo4j"],
            ),
        ):
            req = GraphProbeReq(model="gpt-4")
            result = await graph_service.probe(req, client_ip="127.0.0.1")

        assert result["ok"] is True
        assert result["provider"] == "gpt-4"
        # Mode can be "json" or "text" depending on response format
        assert result["mode"] in ["json", "text"]

    # =========================================================================
    # Test: extract() - 並行供應商嘗試
    # =========================================================================

    @pytest.mark.asyncio
    async def test_extract_parallel_providers(self, graph_service, mock_async_clients):
        """Test parallel provider attempts in extract."""
        from services.gateway.models import GraphData, GraphNode

        # Mock _try_provider_with_attempts to return success immediately
        async def mock_try_provider(
            provider, req, max_attempts, min_nodes, min_edges, allow_empty, sys_base, user_tmpl
        ):
            return {
                "ok": True,
                "data": GraphData(nodes=[GraphNode(id="1", type="Person", props=[])], edges=[]),
                "provider": provider,
                "schema_hash": "test_hash",
            }

        with (
            patch(
                "services.gateway.services.async_graph_service.get_async_litellm_client",
                return_value=mock_async_clients["llm"],
            ),
            patch(
                "services.gateway.services.async_graph_service.get_async_neo4j_driver",
                return_value=mock_async_clients["neo4j"],
            ),
            patch.object(graph_service, "_try_provider_with_attempts", new=mock_try_provider),
        ):
            req = GraphReq(context="Extract entities from this text")
            result = await graph_service.extract(req, client_ip="127.0.0.1")

        assert result["ok"] is True
        assert "data" in result
        assert result["data"].nodes[0].id == "1"

    # =========================================================================
    # Test: upsert() - Neo4j 批量寫入
    # =========================================================================

    @pytest.mark.asyncio
    async def test_upsert_success(self, graph_service, mock_async_clients):
        """Test successful Neo4j upsert."""
        from services.gateway.models import KV, GraphEdge, GraphNode

        with patch(
            "services.gateway.services.async_graph_service.get_async_neo4j_driver",
            return_value=mock_async_clients["neo4j"],
        ):
            graph_data = GraphData(
                nodes=[GraphNode(id="1", type="Person", props=[KV(key="name", value="Alice")])],
                edges=[GraphEdge(src="1", dst="2", type="KNOWS", props=[])],
            )
            req = GraphUpsertReq(data=graph_data)
            result = await graph_service.upsert(req)

        assert result["ok"] is True
        assert result["nodes"] >= 0
        assert result["edges"] >= 0

    # =========================================================================
    # Test: query() - Cypher 查詢
    # =========================================================================

    @pytest.mark.asyncio
    async def test_query_success(self, graph_service, mock_async_clients):
        """Test successful Cypher query."""
        # Mock query results - create proper async iterator
        mock_record1 = MagicMock()
        mock_record1.data = MagicMock(return_value={"n": {"id": "1", "name": "Alice"}})

        class AsyncResultIterator:
            def __init__(self):
                self.items = [mock_record1]
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.items):
                    raise StopAsyncIteration
                item = self.items[self.index]
                self.index += 1
                return item

        mock_result = AsyncResultIterator()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        mock_async_clients["neo4j"].session = MagicMock(return_value=mock_session)

        with patch(
            "services.gateway.services.async_graph_service.get_async_neo4j_driver",
            return_value=mock_async_clients["neo4j"],
        ):
            req = GraphQueryReq(query="MATCH (n:Person) RETURN n LIMIT 10")
            result = await graph_service.query(req)

        assert result["ok"] is True
        assert "records" in result
        assert len(result["records"]) == 1
