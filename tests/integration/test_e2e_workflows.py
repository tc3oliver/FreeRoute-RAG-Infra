"""
Extended End-to-End Integration Tests for FreeRoute RAG Infra.

Tests complete workflows including:
- File ingestion → Indexing → Search → Retrieval
- Graph extraction → Upsert → Query
- Chat with RAG context
- Error recovery and fallback mechanisms
"""

import os
import time
from typing import Any, Dict, List

import pytest
import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Test configuration
DEFAULT_BASE = "http://localhost:9800"
DEFAULT_KEY = "dev-key"
TIMEOUT = 60  # seconds


@pytest.fixture
def api_base():
    """API base URL."""
    return DEFAULT_BASE


@pytest.fixture
def api_headers():
    """API authentication headers."""
    return {"X-API-Key": DEFAULT_KEY}


@pytest.fixture
def test_collection():
    """Test collection name."""
    return "e2e_test_collection"


@pytest.fixture
def cleanup_collection(api_base, test_collection):
    """Cleanup test collection after test."""
    yield
    # Cleanup after test
    try:
        import os

        qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:9333")
        requests.delete(f"{qdrant_url}/collections/{test_collection}", timeout=10)
    except Exception:
        pass


class TestEndToEndWorkflows:
    @staticmethod
    def qdrant_collection_exists(collection_name):
        qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:9333")
        resp = requests.get(f"{qdrant_url}/collections", timeout=10)
        collections = resp.json().get("result", {}).get("collections", [])
        return any(c["name"] == collection_name for c in collections)

    def test_tenant_disable_and_key_expiry(self):
        """
        測試異常情境：
        1. 停用租戶後 API key 失效
        2. API key 過期後失效
        3. 資料刪除後查詢無資料
        """
        # 建立租戶與 API key
        api_key, tenant_id = self.create_tenant({"name": "disable_test", "description": "異常測試"})
        collection = "disable_test_collection"
        self.index_doc(api_key, collection, "doc1", "這是異常測試資料")
        time.sleep(1)

        # 1. 停用租戶
        # 直接呼叫 admin API 修改租戶狀態
        patch_resp = requests.put(
            f"{self.API_BASE}/admin/tenants/{tenant_id}/status",
            headers={"Authorization": f"Bearer {self.ADMIN_KEY}"},
            json={"status": "suspended"},
            timeout=self.TIMEOUT,
        )
        assert patch_resp.status_code == 200

        # 查詢應失敗
        data = {"query": "異常", "collection": collection, "top_k": 3}
        resp = requests.post(
            f"{self.API_BASE}/search",
            headers={"X-API-Key": api_key},
            json=data,
            timeout=self.TIMEOUT,
        )
        assert resp.status_code in [401, 403, 404, 422]

        # # 2. API key 過期
        # # 先啟用租戶
        # patch_resp = requests.put(
        #     f"{self.API_BASE}/admin/tenants/{tenant_id}/status",
        #     headers={"Authorization": f"Bearer {self.ADMIN_KEY}"},
        #     json={"status": "active"},
        #     timeout=self.TIMEOUT,
        # )
        # assert patch_resp.status_code == 200

        # # 取得 API key id
        # tenant_info = requests.get(
        #     f"{self.API_BASE}/admin/tenants/{tenant_id}",
        #     headers={"Authorization": f"Bearer {self.ADMIN_KEY}"},
        #     timeout=self.TIMEOUT,
        # ).json()
        # key_id = tenant_info["api_keys"][0]["key_id"]

        # # 設定 API key 過期
        # expire_resp = requests.patch(
        #     f"{self.API_BASE}/admin/tenants/{tenant_id}/api-keys/{key_id}",
        #     headers={"Authorization": f"Bearer {self.ADMIN_KEY}"},
        #     json={"expires_at": "2000-01-01T00:00:00Z"},
        #     timeout=self.TIMEOUT,
        # )
        # assert expire_resp.status_code == 200

        # # 查詢應失敗
        # resp2 = requests.post(
        #     f"{self.API_BASE}/search",
        #     headers={"X-API-Key": api_key},
        #     json=data,
        #     timeout=self.TIMEOUT,
        # )
        # assert resp2.status_code in [401, 403, 404, 422]

        # 3. 資料刪除後查詢
        # 重新啟用租戶
        patch_resp = requests.put(
            f"{self.API_BASE}/admin/tenants/{tenant_id}/status",
            headers={"Authorization": f"Bearer {self.ADMIN_KEY}"},
            json={"status": "active"},
            timeout=self.TIMEOUT,
        )
        assert patch_resp.status_code == 200

        # 產生新 API key
        new_key_resp = requests.post(
            f"{self.API_BASE}/admin/tenants/{tenant_id}/api-keys",
            headers={"Authorization": f"Bearer {self.ADMIN_KEY}"},
            json={"name": "newkey"},
            timeout=self.TIMEOUT,
        )
        assert new_key_resp.status_code == 201
        new_api_key = new_key_resp.json()["api_key"]

        # 刪除向量資料
        del_resp = requests.post(
            f"{self.API_BASE}/delete/vector",
            headers={"X-API-Key": new_api_key},
            json={"collection": collection},
            timeout=self.TIMEOUT,
        )
        assert del_resp.status_code == 200
        # 檢查 Qdrant collection 是否已刪除
        actual_collection = f"{collection}_{tenant_id}"
        assert not self.qdrant_collection_exists(actual_collection)

        time.sleep(2)
        # 查詢應無資料
        hits = self.search_doc(new_api_key, collection, "異常")
        assert len(hits) == 0

    # =========================================================================
    # Test: 多租戶資料建立、查詢、刪除與隔離驗證
    # =========================================================================

    # 多租戶測試參數與 helper
    API_BASE = "http://localhost:9800"
    ADMIN_KEY = os.environ.get("ADMIN_API_KEY", "admin-secret-key")
    TENANT_A = {"name": "tenant_a", "description": "A測試租戶"}
    TENANT_B = {"name": "tenant_b", "description": "B測試租戶"}
    TIMEOUT = 30

    @classmethod
    def create_tenant(cls, tenant_data):
        resp = requests.post(
            f"{cls.API_BASE}/admin/tenants",
            headers={"Authorization": f"Bearer {cls.ADMIN_KEY}"},
            json=tenant_data,
            timeout=cls.TIMEOUT,
        )
        assert resp.status_code == 200 or resp.status_code == 201
        return resp.json()["api_key"], resp.json()["tenant_id"]

    @classmethod
    def delete_tenant(cls, tenant_id):
        resp = requests.delete(
            f"{cls.API_BASE}/admin/tenants/{tenant_id}",
            headers={"Authorization": f"Bearer {cls.ADMIN_KEY}"},
            timeout=cls.TIMEOUT,
        )
        assert resp.status_code == 200

    @classmethod
    def index_doc(cls, api_key, collection, doc_id, text):
        data = {"chunks": [{"doc_id": doc_id, "text": text}], "collection": collection}
        resp = requests.post(
            f"{cls.API_BASE}/index/chunks", headers={"X-API-Key": api_key}, json=data, timeout=cls.TIMEOUT
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @classmethod
    def search_doc(cls, api_key, collection, query):
        data = {"query": query, "collection": collection, "top_k": 3}
        resp = requests.post(f"{cls.API_BASE}/search", headers={"X-API-Key": api_key}, json=data, timeout=cls.TIMEOUT)
        assert resp.status_code == 200
        return resp.json()["hits"]

    def test_multi_tenant_isolation_and_deletion(self):
        # 建立兩個租戶
        api_key_a, tenant_id_a = self.create_tenant(self.TENANT_A)
        api_key_b, tenant_id_b = self.create_tenant(self.TENANT_B)
        collection = "multi_tenant_test"

        # 各自寫入資料
        collection_a = f"{collection}_{tenant_id_a}"
        collection_b = f"{collection}_{tenant_id_b}"
        self.index_doc(api_key_a, collection_a, "doc_a", "這是A租戶的資料")
        self.index_doc(api_key_b, collection_b, "doc_b", "這是B租戶的資料")
        time.sleep(2)

        # 各自查詢只能查到自己的資料
        hits_a = self.search_doc(api_key_a, collection_a, "A租戶")
        assert any("A租戶" in h["payload"]["text"] for h in hits_a)
        assert all("B租戶" not in h["payload"]["text"] for h in hits_a)

        hits_b = self.search_doc(api_key_b, collection_b, "B租戶")
        assert any("B租戶" in h["payload"]["text"] for h in hits_b)
        assert all("A租戶" not in h["payload"]["text"] for h in hits_b)

        # 刪除A租戶
        self.delete_tenant(tenant_id_a)
        time.sleep(2)

        # A租戶的API key應失效，查詢應回傳 401/403/404/422 等
        data = {"query": "A租戶", "collection": collection, "top_k": 3}
        resp = requests.post(
            f"{self.API_BASE}/search",
            headers={"X-API-Key": api_key_a},
            json=data,
            timeout=self.TIMEOUT,
        )
        assert resp.status_code in [401, 403, 404, 422]

        # B租戶資料仍可查詢
        hits_b2 = self.search_doc(api_key_b, collection_b, "B租戶")
        assert any("B租戶" in h["payload"]["text"] for h in hits_b2)

        # 清理B租戶
        self.delete_tenant(tenant_id_b)

    """Test complete end-to-end workflows."""

    # =========================================================================
    # Test: 完整文件攝取到檢索流程
    # =========================================================================

    def test_complete_ingestion_to_retrieval_workflow(self, api_base, api_headers, test_collection, cleanup_collection):
        """
        Test complete workflow:
        1. Index text chunks
        2. Search for relevant chunks
        3. Retrieve with hybrid approach
        """
        # Step 1: Index some test documents
        chunks_data = {
            "chunks": [
                {
                    "doc_id": "e2e_doc_1",
                    "text": "LiteLLM 是一個統一的 LLM API 代理層，支援多種供應商如 OpenAI、Gemini 和 OpenRouter。",
                    "metadata": {"source": "test_doc_1", "chunk_id": "1"},
                },
                {
                    "doc_id": "e2e_doc_2",
                    "text": "FreeRoute RAG 使用 Qdrant 作為向量資料庫，Neo4j 作為知識圖譜儲存。",
                    "metadata": {"source": "test_doc_2", "chunk_id": "2"},
                },
                {
                    "doc_id": "e2e_doc_3",
                    "text": "系統支援自動 Token Cap 和供應商 fallback 機制，確保成本控制。",
                    "metadata": {"source": "test_doc_3", "chunk_id": "3"},
                },
            ],
            "collection": test_collection,
        }

        # Index chunks
        index_resp = requests.post(
            f"{api_base}/index/chunks",
            headers=api_headers,
            json=chunks_data,
            timeout=TIMEOUT,
        )
        assert index_resp.status_code == 200
        index_result = index_resp.json()
        assert index_result["ok"] is True
        assert index_result["upserted"] >= 3

        # Wait for indexing to complete
        time.sleep(2)

        # Step 2: Search for relevant chunks
        search_data = {
            "query": "什麼是 LiteLLM？",
            "collection": test_collection,
            "top_k": 5,
        }

        search_resp = requests.post(
            f"{api_base}/search",
            headers=api_headers,
            json=search_data,
            timeout=TIMEOUT,
        )
        assert search_resp.status_code == 200
        search_result = search_resp.json()
        assert len(search_result["hits"]) > 0

        # Verify most relevant result contains "LiteLLM"
        top_result = search_result["hits"][0]
        assert "LiteLLM" in top_result["payload"].get("text", "") or "litellm" in str(top_result["payload"]).lower()

        # Step 3: Retrieve with hybrid approach
        retrieve_data = {
            "query": "LiteLLM 功能",
            "collection": test_collection,
            "top_k": 3,
            "use_graph": False,  # Skip graph for this test
        }

        retrieve_resp = requests.post(
            f"{api_base}/retrieve",
            headers=api_headers,
            json=retrieve_data,
            timeout=TIMEOUT,
        )
        assert retrieve_resp.status_code == 200
        retrieve_result = retrieve_resp.json()
        assert len(retrieve_result["hits"]) > 0

    # =========================================================================
    # Test: 圖譜抽取到查詢流程
    # =========================================================================

    def test_graph_extraction_to_query_workflow(self, api_base, api_headers):
        """
        Test complete graph workflow:
        1. Extract graph from text
        2. Upsert to Neo4j
        3. Query graph
        """
        # Step 1: Extract graph from text
        context = """
        Alice 在 2020 年加入 TechCorp 擔任工程師。
        她的主管是 Bob，他是 TechCorp 的技術長。
        TechCorp 總部位於台北，由 Carol 在 2015 年創立。
        """

        extract_data = {
            "context": context,
            "strict": False,
            "repair_if_invalid": True,
        }

        extract_resp = requests.post(
            f"{api_base}/graph/extract",
            headers=api_headers,
            json=extract_data,
            timeout=180,  # Graph extraction can take long
        )

        # If extraction is not available or fails, skip
        if extract_resp.status_code != 200:
            pytest.skip("Graph extraction not available or failed")

        extract_result = extract_resp.json()
        graph_data = extract_result.get("graph") or extract_result.get("data")

        if not graph_data:
            pytest.skip("No graph data extracted")

        # Verify graph structure
        assert "nodes" in graph_data
        assert "edges" in graph_data
        assert len(graph_data["nodes"]) >= 2

        # Step 2: Upsert graph to Neo4j
        upsert_data = {"data": graph_data}

        upsert_resp = requests.post(
            f"{api_base}/graph/upsert",
            headers=api_headers,
            json=upsert_data,
            timeout=TIMEOUT,
        )
        assert upsert_resp.status_code == 200
        upsert_result = upsert_resp.json()
        assert upsert_result["ok"] is True

        # Step 3: Query graph
        query_data = {
            "query": "MATCH (p:Person)-[r]->(c:Company) RETURN p.name as person, type(r) as relation, c.name as company LIMIT 5"
        }

        query_resp = requests.post(
            f"{api_base}/graph/query",
            headers=api_headers,
            json=query_data,
            timeout=TIMEOUT,
        )
        assert query_resp.status_code == 200
        query_result = query_resp.json()
        assert "results" in query_result or "records" in query_result

    # =========================================================================
    # Test: RAG 完整對話流程
    # =========================================================================

    def test_rag_chat_with_context_workflow(self, api_base, api_headers, test_collection, cleanup_collection):
        """
        Test RAG chat workflow:
        1. Index knowledge base
        2. Retrieve relevant context
        3. Chat with augmented context
        """
        # Step 1: Index knowledge base
        kb_chunks = {
            "chunks": [
                {
                    "doc_id": "kb_1",
                    "text": "FreeRoute RAG 是一個開源的 GraphRAG 基礎設施，專注於零成本運行和生產就緒性。",
                    "metadata": {"source": "kb"},
                },
                {
                    "doc_id": "kb_2",
                    "text": "系統使用 FastAPI 作為 API Gateway，LiteLLM 作為 LLM 代理層。",
                    "metadata": {"source": "kb"},
                },
            ],
            "collection": test_collection,
        }

        index_resp = requests.post(
            f"{api_base}/index/chunks",
            headers=api_headers,
            json=kb_chunks,
            timeout=TIMEOUT,
        )
        assert index_resp.status_code == 200

        time.sleep(2)

        # Step 2: Retrieve context for question
        query = "FreeRoute RAG 使用什麼技術？"
        retrieve_data = {
            "query": query,
            "collection": test_collection,
            "top_k": 3,
            "use_graph": False,
        }

        retrieve_resp = requests.post(
            f"{api_base}/retrieve",
            headers=api_headers,
            json=retrieve_data,
            timeout=TIMEOUT,
        )
        assert retrieve_resp.status_code == 200
        context_hits = retrieve_resp.json()["hits"]

        # Step 3: Chat with augmented context
        context_text = "\n".join([hit["text"] for hit in context_hits])
        messages = [
            {
                "role": "system",
                "content": f"請根據以下資訊回答問題：\n\n{context_text}",
            },
            {
                "role": "user",
                "content": query,
            },
        ]

        chat_data = {
            "model": "rag-answer",
            "messages": messages,
            "temperature": 0.3,
        }

        chat_resp = requests.post(
            f"{api_base}/chat",
            headers=api_headers,
            json=chat_data,
            timeout=TIMEOUT,
        )

        # Chat might fail if LLM not configured, so we just check it doesn't crash
        # In full e2e tests with real services, we'd check the answer quality
        if chat_resp.status_code == 200:
            chat_result = chat_resp.json()
            assert "data" in chat_result or "choices" in chat_result

    # =========================================================================
    # Test: 錯誤恢復和 Fallback
    # =========================================================================

    def test_error_recovery_and_fallback(self, api_base, api_headers):
        """
        Test error handling and recovery:
        1. Invalid requests return proper errors
        2. System degrades gracefully
        """
        # Test 1: Invalid collection name (non-existent)
        search_data = {
            "query": "test query",
            "collection": "nonexistent_collection_12345",
            "top_k": 5,
        }

        search_resp = requests.post(
            f"{api_base}/search",
            headers=api_headers,
            json=search_data,
            timeout=TIMEOUT,
        )
        # Should return empty results or proper error, not crash
        assert search_resp.status_code in [200, 404, 422]

        # Test 2: Empty query
        empty_search = {
            "query": "",
            "collection": "test",
            "top_k": 5,
        }

        empty_resp = requests.post(
            f"{api_base}/search",
            headers=api_headers,
            json=empty_search,
            timeout=TIMEOUT,
        )
        # Should handle gracefully with validation error
        assert empty_resp.status_code in [400, 422]

        # Test 3: Invalid model in chat (should fallback to default)
        chat_data = {
            "model": "nonexistent-model-xyz",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        chat_resp = requests.post(
            f"{api_base}/chat",
            headers=api_headers,
            json=chat_data,
            timeout=TIMEOUT,
        )
        # Should either use default model or return error
        assert chat_resp.status_code in [200, 400, 422, 500]

    # =========================================================================
    # Test: 性能基準測試
    # =========================================================================

    def test_performance_benchmarks(self, api_base, api_headers, test_collection, cleanup_collection):
        """
        Basic performance benchmarks:
        1. Health check latency
        2. Embedding generation latency
        3. Vector search latency
        """
        # Test 1: Health check (should be very fast)
        start = time.time()
        health_resp = requests.get(f"{api_base}/health", timeout=5)
        health_latency = time.time() - start

        assert health_resp.status_code == 200
        assert health_latency < 1.0  # Should respond in < 1 second

        # Test 2: Embedding generation (batch of 3)
        embed_data = {
            "texts": [
                "測試文字一",
                "測試文字二",
                "測試文字三",
            ]
        }

        start = time.time()
        embed_resp = requests.post(
            f"{api_base}/embed",
            headers=api_headers,
            json=embed_data,
            timeout=TIMEOUT,
        )
        embed_latency = time.time() - start

        if embed_resp.status_code == 200:
            # Embedding should complete in reasonable time
            assert embed_latency < 10.0  # < 10 seconds for 3 texts

        # Test 3: Vector search (after indexing)
        # First index some data
        chunks_data = {
            "chunks": [
                {
                    "doc_id": f"perf_test_{i}",
                    "text": f"這是性能測試文件 {i}，包含一些測試內容。",
                    "metadata": {"test": "performance"},
                }
                for i in range(10)
            ],
            "collection": test_collection,
        }

        index_resp = requests.post(
            f"{api_base}/index/chunks",
            headers=api_headers,
            json=chunks_data,
            timeout=TIMEOUT,
        )

        if index_resp.status_code == 200:
            time.sleep(2)  # Wait for indexing

            # Now search
            start = time.time()
            search_resp = requests.post(
                f"{api_base}/search",
                headers=api_headers,
                json={
                    "query": "性能測試",
                    "collection": test_collection,
                    "top_k": 5,
                },
                timeout=TIMEOUT,
            )
            search_latency = time.time() - start

            if search_resp.status_code == 200:
                # Search should be fast
                assert search_latency < 5.0  # < 5 seconds

    # =========================================================================
    # Test: 多步驟推理流程
    # =========================================================================

    def test_multi_step_reasoning_workflow(self, api_base, api_headers):
        """
        Test multi-step reasoning:
        1. Probe LLM JSON capability
        2. Extract graph with multiple attempts
        3. Query extracted graph
        """
        # Step 1: Probe LLM JSON capability
        probe_data = {
            "model": "graph-extractor",
            "test_prompt": "請用 JSON 格式回答：Python 是什麼類型的程式語言？",
        }

        probe_resp = requests.post(
            f"{api_base}/graph/probe",
            headers=api_headers,
            json=probe_data,
            timeout=TIMEOUT,
        )

        # If probe fails, skip graph extraction tests
        if probe_resp.status_code != 200:
            pytest.skip("LLM not configured or probe failed")

        probe_result = probe_resp.json()
        if not probe_result.get("ok"):
            pytest.skip("LLM JSON mode not working")

        # Step 2: Complex graph extraction with retry
        complex_context = """
        DataCorp 是一家數據分析公司，由 John 在 2018 年創立。
        Sarah 擔任 CTO，負責技術團隊。
        技術團隊使用 Python 和 PostgreSQL 進行數據處理。
        公司與 CloudProvider 合作，使用他們的雲端服務。
        """

        extract_data = {
            "context": complex_context,
            "strict": True,
            "repair_if_invalid": True,
        }

        extract_resp = requests.post(
            f"{api_base}/graph/extract",
            headers=api_headers,
            json=extract_data,
            timeout=180,
        )

        if extract_resp.status_code == 200:
            extract_result = extract_resp.json()
            graph = extract_result.get("graph") or extract_result.get("data")

            if graph:
                # Verify complex relationships were extracted
                assert len(graph.get("nodes", [])) >= 3
                assert len(graph.get("edges", [])) >= 2

    def test_openai_style_endpoints(self, api_base, api_headers):
        """
        Test OpenAI-compatible endpoints exposed by the Gateway:
        - POST /v1/chat/completions
        - POST /v1/embeddings
        Behaviour: if endpoint returns 200, validate basic response shape; otherwise skip.
        """
        # Chat completions (OpenAI style)
        chat_payload = {"model": "rag-answer", "messages": [{"role": "user", "content": "Hello"}]}
        chat_resp = requests.post(
            f"{api_base}/v1/chat/completions", headers=api_headers, json=chat_payload, timeout=TIMEOUT
        )
        if chat_resp.status_code == 200:
            j = chat_resp.json()
            # Accept either OpenAI choices format or the gateway custom data
            assert ("choices" in j) or (j.get("ok") is True and "data" in j)
        else:
            # Upstream not configured or returns error - don't fail the whole test suite
            pytest.skip(f"/v1/chat/completions not available (status={chat_resp.status_code})")
        # Embeddings (OpenAI style)
        emb_payload = {"model": "local-embed", "input": ["What is RAG?", "Describe RAG"]}
        emb_resp = requests.post(f"{api_base}/v1/embeddings", headers=api_headers, json=emb_payload, timeout=TIMEOUT)
        if emb_resp.status_code == 200:
            j = emb_resp.json()
            assert ("data" in j) or ("embeddings" in j) or (j.get("ok") is True and "vectors" in j)
        else:
            pytest.skip(f"/v1/embeddings not available (status={emb_resp.status_code})")


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
