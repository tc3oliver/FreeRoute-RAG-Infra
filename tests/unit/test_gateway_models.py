"""
Unit tests for services/gateway/models.py
"""

import pytest
from pydantic import ValidationError

from services.gateway.models import (
    KV,
    ChatReq,
    ChatResp,
    ChunkItem,
    Citation,
    EmbedReq,
    EmbedResp,
    GraphData,
    GraphEdge,
    GraphExtractResp,
    GraphNode,
    GraphProbeReq,
    GraphProbeResp,
    GraphQueryReq,
    GraphQueryResp,
    GraphReq,
    GraphUpsertReq,
    GraphUpsertResp,
    HealthResp,
    IndexChunksReq,
    IndexChunksResp,
    RerankItem,
    RerankReq,
    RerankResp,
    RetrieveHit,
    RetrieveReq,
    RetrieveResp,
    SearchHit,
    SearchReq,
    SearchResp,
    Subgraph,
    SubgraphEdge,
    SubgraphNode,
    VersionResp,
    WhoAmIResp,
)


class TestRequestModels:
    """Test request model validations."""

    def test_chat_req_valid(self):
        req = ChatReq(messages=[{"role": "user", "content": "Hello"}])
        assert req.messages == [{"role": "user", "content": "Hello"}]
        assert req.temperature == 0.2
        assert req.json_mode is False

    def test_chat_req_with_model(self):
        req = ChatReq(messages=[{"role": "user", "content": "Hi"}], model="gpt-4", temperature=0.5, json_mode=True)
        assert req.model == "gpt-4"
        assert req.temperature == 0.5
        assert req.json_mode is True

    def test_embed_req_valid(self):
        req = EmbedReq(texts=["hello", "world"])
        assert req.texts == ["hello", "world"]

    def test_embed_req_empty_texts(self):
        req = EmbedReq(texts=[])
        assert req.texts == []

    def test_rerank_req_defaults(self):
        req = RerankReq(query="test", documents=["doc1", "doc2"])
        assert req.query == "test"
        assert req.documents == ["doc1", "doc2"]
        assert req.top_n == 6

    def test_rerank_req_custom_top_n(self):
        req = RerankReq(query="test", documents=["doc1"], top_n=3)
        assert req.top_n == 3

    def test_graph_req_defaults(self):
        req = GraphReq(context="Some text")
        assert req.context == "Some text"
        assert req.strict is True
        assert req.repair_if_invalid is True
        assert req.min_nodes is None
        assert req.min_edges is None
        assert req.allow_empty is None
        assert req.max_attempts is None
        assert req.provider_chain is None

    def test_graph_req_with_overrides(self):
        req = GraphReq(
            context="Text",
            strict=False,
            repair_if_invalid=False,
            min_nodes=2,
            min_edges=3,
            allow_empty=True,
            max_attempts=5,
            provider_chain=["model1", "model2"],
        )
        assert req.strict is False
        assert req.repair_if_invalid is False
        assert req.min_nodes == 2
        assert req.min_edges == 3
        assert req.allow_empty is True
        assert req.max_attempts == 5
        assert req.provider_chain == ["model1", "model2"]

    def test_graph_probe_req_defaults(self):
        req = GraphProbeReq(model="graph-extractor")
        assert req.model == "graph-extractor"
        assert req.strict_json is False
        assert req.temperature == 0.0
        assert req.timeout == 60
        assert req.messages is None

    def test_chunk_item_minimal(self):
        chunk = ChunkItem(doc_id="doc1", text="content")
        assert chunk.doc_id == "doc1"
        assert chunk.text == "content"
        assert chunk.chunk_id is None
        assert chunk.metadata is None

    def test_chunk_item_full(self):
        chunk = ChunkItem(doc_id="doc1", text="content", chunk_id="chunk1", metadata={"key": "value"})
        assert chunk.chunk_id == "chunk1"
        assert chunk.metadata == {"key": "value"}

    def test_index_chunks_req_defaults(self):
        req = IndexChunksReq(chunks=[ChunkItem(doc_id="doc1", text="text")])
        assert req.collection == "chunks"
        assert len(req.chunks) == 1

    def test_search_req_defaults(self):
        req = SearchReq(query="test query")
        assert req.query == "test query"
        assert req.top_k == 5
        assert req.collection == "chunks"
        assert req.filters is None

    def test_graph_query_req(self):
        req = GraphQueryReq(query="MATCH (n) RETURN n")
        assert req.query == "MATCH (n) RETURN n"
        assert req.params is None

    def test_graph_query_req_with_params(self):
        req = GraphQueryReq(query="MATCH (n {id: $id}) RETURN n", params={"id": "123"})
        assert req.params == {"id": "123"}

    def test_retrieve_req_defaults(self):
        req = RetrieveReq(query="test")
        assert req.query == "test"
        assert req.top_k == 5
        assert req.collection == "chunks"
        assert req.include_subgraph is True
        assert req.max_hops == 1
        assert req.filters is None


class TestResponseModels:
    """Test response model serialization."""

    def test_health_resp(self):
        resp = HealthResp(ok=True)
        assert resp.ok is True

    def test_version_resp(self):
        resp = VersionResp(version="v1.0.0")
        assert resp.version == "v1.0.0"

    def test_whoami_resp(self):
        resp = WhoAmIResp(
            app_version="v1.0.0",
            litellm_base="http://litellm:4000",
            entrypoints=["rag-answer"],
            json_mode_hint_injection=True,
            graph_schema_path="/path/to/schema",
            schema_hash="abc123",
            graph_defaults={"min_nodes": 1},
        )
        assert resp.app_version == "v1.0.0"
        assert resp.litellm_base == "http://litellm:4000"
        assert resp.entrypoints == ["rag-answer"]

    def test_embed_resp(self):
        resp = EmbedResp(ok=True, vectors=[[0.1, 0.2], [0.3, 0.4]], dim=2)
        assert resp.ok is True
        assert len(resp.vectors) == 2
        assert resp.dim == 2

    def test_rerank_resp(self):
        items = [RerankItem(index=0, score=0.9, text="doc1"), RerankItem(index=1, score=0.7)]
        resp = RerankResp(ok=True, results=items)
        assert resp.ok is True
        assert len(resp.results) == 2
        assert resp.results[0].text == "doc1"
        assert resp.results[1].text is None

    def test_chat_resp(self):
        resp = ChatResp(ok=True, data="response text", meta={"model": "gpt-4"})
        assert resp.ok is True
        assert resp.data == "response text"
        assert resp.meta["model"] == "gpt-4"

    def test_chat_resp_with_json_data(self):
        resp = ChatResp(ok=True, data={"key": "value"}, meta={})
        assert isinstance(resp.data, dict)
        assert resp.data["key"] == "value"

    def test_kv_model(self):
        kv = KV(key="name", value="Alice")
        assert kv.key == "name"
        assert kv.value == "Alice"

    def test_graph_node(self):
        node = GraphNode(id="n1", type="Person", props=[KV(key="name", value="Bob")])
        assert node.id == "n1"
        assert node.type == "Person"
        assert len(node.props) == 1
        assert node.props[0].key == "name"

    def test_graph_edge(self):
        edge = GraphEdge(src="n1", dst="n2", type="KNOWS", props=[KV(key="since", value=2020)])
        assert edge.src == "n1"
        assert edge.dst == "n2"
        assert edge.type == "KNOWS"
        assert edge.props[0].value == 2020

    def test_graph_data(self):
        nodes = [GraphNode(id="n1", type="Person", props=[])]
        edges = [GraphEdge(src="n1", dst="n2", type="KNOWS", props=[])]
        data = GraphData(nodes=nodes, edges=edges)
        assert len(data.nodes) == 1
        assert len(data.edges) == 1

    def test_graph_extract_resp(self):
        data = GraphData(nodes=[], edges=[])
        resp = GraphExtractResp(ok=True, data=data, provider="gpt-4", schema_hash="hash123")
        assert resp.ok is True
        assert resp.provider == "gpt-4"
        assert resp.schema_hash == "hash123"

    def test_graph_probe_resp_json_mode(self):
        resp = GraphProbeResp(ok=True, mode="json", provider="gpt-4", data={"key": "value"})
        assert resp.mode == "json"
        assert resp.data == {"key": "value"}
        assert resp.text is None

    def test_graph_probe_resp_text_mode(self):
        resp = GraphProbeResp(ok=True, mode="text", provider="gpt-4", text="plain text")
        assert resp.mode == "text"
        assert resp.text == "plain text"
        assert resp.data is None

    def test_graph_probe_resp_error(self):
        resp = GraphProbeResp(ok=False, mode="json", error="parse error", raw="invalid json")
        assert resp.ok is False
        assert resp.error == "parse error"
        assert resp.raw == "invalid json"

    def test_index_chunks_resp(self):
        resp = IndexChunksResp(ok=True, upserted=10, dim=768, collection="chunks")
        assert resp.ok is True
        assert resp.upserted == 10
        assert resp.dim == 768
        assert resp.collection == "chunks"

    def test_search_hit(self):
        hit = SearchHit(id="uuid", score=0.95, payload={"doc_id": "doc1", "text": "content"})
        assert hit.id == "uuid"
        assert hit.score == 0.95
        assert hit.payload["doc_id"] == "doc1"

    def test_search_resp(self):
        hits = [SearchHit(id="1", score=0.9, payload={})]
        resp = SearchResp(ok=True, hits=hits)
        assert resp.ok is True
        assert len(resp.hits) == 1

    def test_graph_upsert_resp(self):
        resp = GraphUpsertResp(ok=True, nodes=5, edges=3)
        assert resp.ok is True
        assert resp.nodes == 5
        assert resp.edges == 3

    def test_graph_query_resp(self):
        resp = GraphQueryResp(ok=True, records=[{"n": {"id": "1"}}, {"n": {"id": "2"}}])
        assert resp.ok is True
        assert len(resp.records) == 2

    def test_citation_vector_source(self):
        cit = Citation(source="vector", doc_id="doc1", chunk_id="chunk1", score=0.9)
        assert cit.source == "vector"
        assert cit.doc_id == "doc1"
        assert cit.chunk_id == "chunk1"
        assert cit.score == 0.9

    def test_citation_graph_source(self):
        cit = Citation(source="graph", node_id="n1", edge_type="KNOWS")
        assert cit.source == "graph"
        assert cit.node_id == "n1"
        assert cit.edge_type == "KNOWS"

    def test_retrieve_hit(self):
        citations = [Citation(source="vector", doc_id="doc1", score=0.9)]
        hit = RetrieveHit(text="content", metadata={"key": "value"}, citations=citations, score=0.9)
        assert hit.text == "content"
        assert hit.metadata["key"] == "value"
        assert len(hit.citations) == 1
        assert hit.score == 0.9

    def test_subgraph_node(self):
        node = SubgraphNode(id="n1", type="Person", props={"name": "Alice"})
        assert node.id == "n1"
        assert node.type == "Person"
        assert node.props["name"] == "Alice"

    def test_subgraph_edge(self):
        edge = SubgraphEdge(src="n1", dst="n2", type="KNOWS", props={"since": 2020})
        assert edge.src == "n1"
        assert edge.dst == "n2"
        assert edge.type == "KNOWS"

    def test_subgraph(self):
        nodes = [SubgraphNode(id="n1", type="Person", props={})]
        edges = [SubgraphEdge(src="n1", dst="n2", type="KNOWS", props={})]
        sg = Subgraph(nodes=nodes, edges=edges)
        assert len(sg.nodes) == 1
        assert len(sg.edges) == 1

    def test_retrieve_resp_with_subgraph(self):
        hits = [RetrieveHit(text="text", metadata={}, citations=[], score=0.9)]
        sg = Subgraph(nodes=[], edges=[])
        resp = RetrieveResp(ok=True, hits=hits, subgraph=sg, query_time_ms=100)
        assert resp.ok is True
        assert len(resp.hits) == 1
        assert resp.subgraph is not None
        assert resp.query_time_ms == 100

    def test_retrieve_resp_without_subgraph(self):
        resp = RetrieveResp(ok=True, hits=[], subgraph=None, query_time_ms=50)
        assert resp.subgraph is None


class TestModelValidation:
    """Test model validation edge cases."""

    def test_chat_req_missing_messages(self):
        with pytest.raises(ValidationError):
            ChatReq()

    def test_embed_req_missing_texts(self):
        with pytest.raises(ValidationError):
            EmbedReq()

    def test_rerank_req_missing_query(self):
        with pytest.raises(ValidationError):
            RerankReq(documents=["doc"])

    def test_rerank_req_missing_documents(self):
        with pytest.raises(ValidationError):
            RerankReq(query="test")

    def test_graph_req_missing_context(self):
        with pytest.raises(ValidationError):
            GraphReq()

    def test_graph_probe_req_missing_model(self):
        with pytest.raises(ValidationError):
            GraphProbeReq()

    def test_chunk_item_missing_required_fields(self):
        with pytest.raises(ValidationError):
            ChunkItem(doc_id="doc1")

        with pytest.raises(ValidationError):
            ChunkItem(text="text")

    def test_graph_upsert_req_forward_ref(self):
        """Test that forward references are resolved correctly."""
        data = GraphData(nodes=[], edges=[])
        req = GraphUpsertReq(data=data)
        assert req.data == data


class TestModelSerialization:
    """Test model JSON serialization/deserialization."""

    def test_chat_req_json_round_trip(self):
        req = ChatReq(messages=[{"role": "user", "content": "Hi"}], temperature=0.5, json_mode=True)
        json_str = req.model_dump_json()
        req2 = ChatReq.model_validate_json(json_str)
        assert req2.messages == req.messages
        assert req2.temperature == req.temperature
        assert req2.json_mode == req.json_mode

    def test_graph_data_json_round_trip(self):
        data = GraphData(
            nodes=[GraphNode(id="n1", type="Person", props=[KV(key="name", value="Alice")])],
            edges=[GraphEdge(src="n1", dst="n2", type="KNOWS", props=[])],
        )
        json_str = data.model_dump_json()
        data2 = GraphData.model_validate_json(json_str)
        assert len(data2.nodes) == 1
        assert data2.nodes[0].id == "n1"
        assert len(data2.edges) == 1
        assert data2.edges[0].src == "n1"

    def test_retrieve_resp_dict_serialization(self):
        resp = RetrieveResp(ok=True, hits=[], subgraph=None, query_time_ms=100)
        resp_dict = resp.model_dump()
        assert resp_dict["ok"] is True
        assert resp_dict["hits"] == []
        assert resp_dict["subgraph"] is None
        assert resp_dict["query_time_ms"] == 100
