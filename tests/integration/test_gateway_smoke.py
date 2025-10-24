#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Enhanced integration smoke test for FreeRoute RAG Infra API Gateway.
Tests all major endpoints including meta, chat, vector, and graph operations.

Test Coverage:
==============

Meta Endpoints (4/4):
  ✓ GET  /health         - Health check
  ✓ GET  /version        - Version information
  ✓ GET  /whoami         - Configuration details
  ✓ GET  /metrics        - Prometheus metrics

Chat & Embedding Endpoints (3/3):
  ✓ POST /chat          - Chat completion
  ✓ POST /embed         - Text embedding generation
  ✓ POST /rerank        - Document reranking

Vector Endpoints (3/3):
  ✓ POST /index/chunks  - Index text chunks into Qdrant
  ✓ POST /search        - Vector similarity search
  ✓ POST /retrieve      - Hybrid retrieval (vector + graph)

Graph Endpoints (4/4):
  ✓ POST /graph/probe   - Test provider JSON capability
  ✓ POST /graph/extract - Extract graph from text
  ✓ POST /graph/upsert  - Upsert nodes and edges
  ✓ POST /graph/query   - Execute Cypher queries

Cleanup:
  ✓ Cleanup vector test data from Qdrant
  ✓ Cleanup graph test nodes from Neo4j

Total Coverage: 14 endpoints + 2 cleanup operations

Environment Variables:
=====================
  API_GATEWAY_BASE        - API Gateway base URL (default: http://localhost:9800)
  API_GATEWAY_KEY         - API key for authentication (default: dev-key)
  API_GATEWAY_AUTH_HEADER - Authentication header name (default: X-API-Key)
  QDRANT_URL              - Qdrant base URL for cleanup (default: http://localhost:9333)
  NEO4J_URI               - Neo4j HTTP API URL for cleanup (default: http://localhost:9474)
  NEO4J_USER              - Neo4j username (default: neo4j)
  NEO4J_PASSWORD          - Neo4j password (default: neo4jneo4j)

Usage:
======
  # Run all tests with cleanup
  python test_gateway_smoke.py

  # Skip cleanup (留下測試數據以便檢查)
  python test_gateway_smoke.py --skip-cleanup

  # Run specific test categories only
  python test_gateway_smoke.py --skip-graph --skip-vector
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

try:
    from jsonschema import validate

    HAS_JSONSCHEMA = True
except Exception:
    HAS_JSONSCHEMA = False

DEFAULT_BASE = os.environ.get("API_GATEWAY_BASE", "http://localhost:9800")
DEFAULT_KEY = os.environ.get("API_GATEWAY_KEY", "dev-key")
DEFAULT_HEADER = os.environ.get("API_GATEWAY_AUTH_HEADER", "X-API-Key")

# Test data identifiers for cleanup
TEST_COLLECTION = "test_collection_smoke"
TEST_NODE_IDS = ["test_node_1", "test_node_2"]
TEST_DOC_IDS = ["test_doc_1", "test_doc_2"]

# Test counters for reporting
test_results = {"passed": 0, "failed": 0, "skipped": 0}


def log_test(name: str, status: str, details: str = ""):
    """Log test result with colored output."""
    colors = {"PASS": "\033[92m", "FAIL": "\033[91m", "SKIP": "\033[93m", "RESET": "\033[0m"}
    status_colored = f"{colors.get(status, '')}{status}{colors['RESET']}"
    print(f"[{status_colored}] {name:<30} {details}")

    if status == "PASS":
        test_results["passed"] += 1
    elif status == "FAIL":
        test_results["failed"] += 1
    elif status == "SKIP":
        test_results["skipped"] += 1


def make_headers(key: str, auth_header: str) -> Dict[str, str]:
    """Create authentication headers."""
    if auth_header.lower() == "authorization":
        return {"Authorization": f"Bearer {key}"}
    return {"X-API-Key": key}


def ensure_ok(resp: requests.Response) -> Dict[str, Any]:
    """Parse response and ensure it's OK."""
    text = resp.text
    try:
        data = resp.json()
    except Exception:
        data = {"_non_json": text, "_status": resp.status_code}
        if not resp.ok:
            return {"ok": False, "status": resp.status_code, "body": text}
        return data
    if not resp.ok:
        return {"ok": False, "status": resp.status_code, "body": data}
    return data


# =============================================================================
# Cleanup Functions
# =============================================================================


def cleanup_vector_data(base: str, headers: Dict[str, str]) -> bool:
    """
    Clean up test vector data from Qdrant.
    Uses Qdrant's direct API to delete test collection.
    """
    try:
        # Try to get Qdrant endpoint from environment or use default
        qdrant_base = os.environ.get("QDRANT_URL", "http://localhost:9333")

        # Delete the test collection
        r = requests.delete(f"{qdrant_base}/collections/{TEST_COLLECTION}", timeout=10)

        if r.status_code in [200, 404]:  # 404 is OK if collection doesn't exist
            log_test("Cleanup Vector Data", "PASS", f"Collection '{TEST_COLLECTION}' cleaned")
            return True
        else:
            log_test("Cleanup Vector Data", "FAIL", f"Status: {r.status_code}")
            return False
    except Exception as e:
        log_test("Cleanup Vector Data", "FAIL", f"Exception: {e}")
        return False


def cleanup_graph_data(base: str, headers: Dict[str, str]) -> bool:
    """
    Clean up test graph data from Neo4j.
    Uses /graph/query endpoint with DETACH DELETE.
    """
    try:
        # Delete test nodes and their relationships
        node_ids_str = ", ".join([f"'{nid}'" for nid in TEST_NODE_IDS])
        cypher = f"MATCH (n) WHERE n.id IN [{node_ids_str}] DETACH DELETE n"

        # Note: /graph/query only allows read operations by default
        # We'll try to use Neo4j's direct API instead
        neo4j_base = os.environ.get("NEO4J_URI", "http://localhost:9474")
        neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
        neo4j_pass = os.environ.get("NEO4J_PASSWORD", "neo4j123")

        # Use Neo4j's transaction API
        auth = (neo4j_user, neo4j_pass)
        tx_url = f"{neo4j_base}/db/neo4j/tx/commit"

        tx_payload = {"statements": [{"statement": cypher, "parameters": {}}]}

        r = requests.post(tx_url, json=tx_payload, auth=auth, timeout=10)

        if r.status_code == 200:
            log_test("Cleanup Graph Data", "PASS", f"Nodes {TEST_NODE_IDS} cleaned")
            return True
        else:
            # If direct Neo4j API fails, it might be OK (nodes might not exist)
            log_test("Cleanup Graph Data", "SKIP", f"Could not clean (Status: {r.status_code})")
            return True  # Don't fail the test suite
    except Exception as e:
        log_test("Cleanup Graph Data", "SKIP", f"Could not clean: {e}")
        return True  # Don't fail the test suite


# =============================================================================
# Meta Endpoints
# =============================================================================


def test_health(base: str) -> bool:
    """Test /health endpoint."""
    try:
        r = requests.get(f"{base}/health", timeout=10)
        data = ensure_ok(r)
        if r.ok and data.get("ok") is True:
            log_test("GET /health", "PASS", f"Status: {r.status_code}")
            return True
        else:
            log_test("GET /health", "FAIL", f"Unexpected response: {data}")
            return False
    except Exception as e:
        log_test("GET /health", "FAIL", f"Exception: {e}")
        return False


def test_version(base: str) -> bool:
    """Test /version endpoint."""
    try:
        r = requests.get(f"{base}/version", timeout=10)
        data = ensure_ok(r)
        if r.ok and "version" in data:
            log_test("GET /version", "PASS", f"Version: {data['version']}")
            return True
        else:
            log_test("GET /version", "FAIL", f"Unexpected response: {data}")
            return False
    except Exception as e:
        log_test("GET /version", "FAIL", f"Exception: {e}")
        return False


def test_whoami(base: str, headers: Dict[str, str]) -> bool:
    """Test /whoami endpoint."""
    try:
        r = requests.get(f"{base}/whoami", headers=headers, timeout=10)
        data = ensure_ok(r)
        if r.ok and "app_version" in data:
            log_test("GET /whoami", "PASS", f"App version: {data.get('app_version', 'N/A')}")
            return True
        else:
            log_test("GET /whoami", "FAIL", f"Unexpected response: {data}")
            return False
    except Exception as e:
        log_test("GET /whoami", "FAIL", f"Exception: {e}")
        return False


def test_metrics(base: str) -> bool:
    """Test /metrics endpoint."""
    try:
        r = requests.get(f"{base}/metrics", timeout=10)
        # Metrics endpoint may return 204 if disabled
        if r.status_code == 204:
            log_test("GET /metrics", "PASS", "Metrics disabled (204)")
            return True
        elif r.ok:
            log_test("GET /metrics", "PASS", f"Metrics available ({len(r.text)} bytes)")
            return True
        else:
            log_test("GET /metrics", "FAIL", f"Status: {r.status_code}")
            return False
    except Exception as e:
        log_test("GET /metrics", "FAIL", f"Exception: {e}")
        return False


# =============================================================================
# Chat & Embedding Endpoints
# =============================================================================


def test_chat(base: str, headers: Dict[str, str]) -> bool:
    """Test /chat endpoint."""
    try:
        payload = {
            "model": "rag-answer",
            "messages": [{"role": "user", "content": "請用三點條列這個系統的用途"}],
            "json_mode": True,
            "temperature": 0.2,
        }
        r = requests.post(f"{base}/chat", headers=headers, json=payload, timeout=120)
        data = ensure_ok(r)
        # Accept both choices (OpenAI format) and data (custom format)
        if r.ok and (("choices" in data) or ("data" in data and data.get("ok") is True)):
            if "choices" in data:
                log_test("POST /chat", "PASS", f"Got {len(data['choices'])} choice(s)")
            else:
                log_test("POST /chat", "PASS", "Got response with data")
            return True
        else:
            log_test("POST /chat", "FAIL", f"Unexpected response: {str(data)[:200]}")
            return False
    except Exception as e:
        log_test("POST /chat", "FAIL", f"Exception: {e}")
        return False


def test_openai_style_endpoints(base: str, headers: Dict[str, str]) -> bool:
    """Test OpenAI-style endpoints if available: /v1/chat/completions and /v1/embeddings"""
    try:
        # Chat completions
        chat_payload = {"model": "rag-answer", "messages": [{"role": "user", "content": "Hello"}]}
        r = requests.post(f"{base}/v1/chat/completions", headers=headers, json=chat_payload, timeout=60)
        if r.status_code == 200:
            data = ensure_ok(r)
            if ("choices" in data) or (data.get("ok") is True and "data" in data):
                log_test("POST /v1/chat/completions", "PASS", "Compatible response")
            else:
                log_test("POST /v1/chat/completions", "FAIL", "Unexpected shape")
                return False
        else:
            log_test("POST /v1/chat/completions", "SKIP", f"Status {r.status_code}")

        # Embeddings
        emb_payload = {"model": "local-embed", "input": ["What is RAG?", "Describe RAG"]}
        r = requests.post(f"{base}/v1/embeddings", headers=headers, json=emb_payload, timeout=60)
        if r.status_code == 200:
            data = ensure_ok(r)
            if ("data" in data) or ("embeddings" in data) or (data.get("ok") is True and "vectors" in data):
                log_test("POST /v1/embeddings", "PASS", "Compatible response")
            else:
                log_test("POST /v1/embeddings", "FAIL", "Unexpected shape")
                return False
        else:
            log_test("POST /v1/embeddings", "SKIP", f"Status {r.status_code}")

        return True
    except Exception as e:
        log_test("OpenAI-style endpoints", "FAIL", f"Exception: {e}")
        return False


def test_embed(base: str, headers: Dict[str, str]) -> bool:
    """Test /embed endpoint."""
    try:
        payload = {"texts": ["這是第一段測試文字", "這是第二段測試文字"]}
        r = requests.post(f"{base}/embed", headers=headers, json=payload, timeout=60)
        data = ensure_ok(r)
        # Accept both embeddings (OpenAI format) and vectors (custom format)
        if r.ok and (("embeddings" in data) or ("vectors" in data and data.get("ok") is True)):
            count = len(data.get("embeddings", data.get("vectors", [])))
            log_test("POST /embed", "PASS", f"Got {count} embedding(s)")
            return True
        else:
            log_test("POST /embed", "FAIL", f"Unexpected response: {str(data)[:100]}")
            return False
    except Exception as e:
        log_test("POST /embed", "FAIL", f"Exception: {e}")
        return False


def test_rerank(base: str, headers: Dict[str, str]) -> bool:
    """Test /rerank endpoint."""
    try:
        payload = {
            "query": "什麼是 LiteLLM？",
            "documents": [
                "LiteLLM 是一個代理層，提供 OpenAI 相容 API，支援多供應商與路由。",
                "這是一個與主題無關的段落。",
                "LiteLLM 也能做 fallback、費用控額與熔斷冷卻。",
            ],
            "top_n": 2,
        }
        r = requests.post(f"{base}/rerank", headers=headers, json=payload, timeout=60)
        data = ensure_ok(r)
        if r.ok and "results" in data:
            log_test("POST /rerank", "PASS", f"Got {len(data['results'])} result(s)")
            return True
        else:
            log_test("POST /rerank", "FAIL", f"Unexpected response: {data}")
            return False
    except Exception as e:
        log_test("POST /rerank", "FAIL", f"Exception: {e}")
        return False


# =============================================================================
# Vector Endpoints
# =============================================================================


def test_index_chunks(base: str, headers: Dict[str, str]) -> bool:
    """Test /index/chunks endpoint."""
    try:
        payload = {
            "chunks": [
                {
                    "doc_id": TEST_DOC_IDS[0],
                    "text": "這是測試文件的第一個段落，包含一些關於測試的資訊。",
                    "metadata": {"source": "test_doc", "chunk_id": "chunk_1"},
                },
                {
                    "doc_id": TEST_DOC_IDS[1],
                    "text": "這是測試文件的第二個段落，提供更多測試相關內容。",
                    "metadata": {"source": "test_doc", "chunk_id": "chunk_2"},
                },
            ],
            "collection": TEST_COLLECTION,
        }
        r = requests.post(f"{base}/index/chunks", headers=headers, json=payload, timeout=60)
        data = ensure_ok(r)
        if r.ok and data.get("ok") is True:
            indexed = data.get("indexed_count", data.get("count", 0))
            log_test("POST /index/chunks", "PASS", f"Indexed {indexed} chunk(s)")
            return True
        else:
            log_test("POST /index/chunks", "FAIL", f"Unexpected response: {str(data)[:200]}")
            return False
    except Exception as e:
        log_test("POST /index/chunks", "FAIL", f"Exception: {e}")
        return False


def test_search(base: str, headers: Dict[str, str]) -> bool:
    """Test /search endpoint."""
    try:
        payload = {"query": "測試資訊", "collection": TEST_COLLECTION, "top_k": 5}
        r = requests.post(f"{base}/search", headers=headers, json=payload, timeout=60)
        data = ensure_ok(r)
        # Accept both results and hits
        results = data.get("results", data.get("hits", []))
        if r.ok and isinstance(results, list):
            log_test("POST /search", "PASS", f"Found {len(results)} result(s)")
            return True
        else:
            log_test("POST /search", "FAIL", f"Unexpected response: {str(data)[:200]}")
            return False
    except Exception as e:
        log_test("POST /search", "FAIL", f"Exception: {e}")
        return False


def test_retrieve(base: str, headers: Dict[str, str]) -> bool:
    """Test /retrieve endpoint (hybrid retrieval)."""
    try:
        payload = {"query": "測試", "collection": TEST_COLLECTION, "top_k": 3, "use_graph": False}
        r = requests.post(f"{base}/retrieve", headers=headers, json=payload, timeout=60)
        data = ensure_ok(r)
        # Accept both results and hits
        results = data.get("results", data.get("hits", []))
        if r.ok and isinstance(results, list):
            log_test("POST /retrieve", "PASS", f"Retrieved {len(results)} result(s)")
            return True
        else:
            log_test("POST /retrieve", "FAIL", f"Unexpected response: {str(data)[:200]}")
            return False
    except Exception as e:
        log_test("POST /retrieve", "FAIL", f"Exception: {e}")
        return False


# =============================================================================
# Graph Endpoints
# =============================================================================


def test_graph_probe(base: str, headers: Dict[str, str]) -> bool:
    """Test /graph/probe endpoint."""
    try:
        payload = {"model": "graph-extractor", "test_prompt": "請用JSON格式回答：台北是哪個國家的首都？"}
        r = requests.post(f"{base}/graph/probe", headers=headers, json=payload, timeout=60)
        data = ensure_ok(r)
        if r.ok and "ok" in data:
            log_test("POST /graph/probe", "PASS", f"Probe successful: {data.get('ok')}")
            return True
        else:
            log_test("POST /graph/probe", "FAIL", f"Unexpected response: {data}")
            return False
    except Exception as e:
        log_test("POST /graph/probe", "FAIL", f"Exception: {e}")
        return False


def test_graph_extract(base: str, headers: Dict[str, str]) -> bool:
    """Test /graph/extract endpoint."""
    try:
        context = "Nick 於 2022 年加入 Acme 擔任工程師；Acme 總部位於台北，創辦人是 Bob。"
        payload = {"context": context, "strict": True, "repair_if_invalid": True}
        r = requests.post(f"{base}/graph/extract", headers=headers, json=payload, timeout=180)
        data = ensure_ok(r)
        # Check for both graph and data fields
        graph_data = data.get("graph", data.get("data"))
        if r.ok and graph_data:
            nodes = len(graph_data.get("nodes", []))
            edges = len(graph_data.get("edges", []))
            log_test("POST /graph/extract", "PASS", f"Extracted {nodes} node(s), {edges} edge(s)")
            return True
        else:
            log_test("POST /graph/extract", "FAIL", f"Unexpected response: {str(data)[:200]}")
            return False
    except Exception as e:
        log_test("POST /graph/extract", "FAIL", f"Exception: {e}")
        return False


def test_graph_upsert(base: str, headers: Dict[str, str]) -> bool:
    """Test /graph/upsert endpoint."""
    try:
        payload = {
            "data": {
                "nodes": [
                    {"id": TEST_NODE_IDS[0], "type": "Person", "props": [{"key": "name", "value": "TestUser"}]},
                    {"id": TEST_NODE_IDS[1], "type": "Company", "props": [{"key": "name", "value": "TestCorp"}]},
                ],
                "edges": [
                    {
                        "src": TEST_NODE_IDS[0],
                        "dst": TEST_NODE_IDS[1],
                        "type": "WORKS_AT",
                        "props": [{"key": "since", "value": "2024"}],
                    }
                ],
            }
        }
        r = requests.post(f"{base}/graph/upsert", headers=headers, json=payload, timeout=60)
        data = ensure_ok(r)
        if r.ok and data.get("ok") is True:
            log_test("POST /graph/upsert", "PASS", "Upserted graph data")
            return True
        else:
            log_test("POST /graph/upsert", "FAIL", f"Unexpected response: {str(data)[:200]}")
            return False
    except Exception as e:
        log_test("POST /graph/upsert", "FAIL", f"Exception: {e}")
        return False


def test_graph_query(base: str, headers: Dict[str, str]) -> bool:
    """Test /graph/query endpoint."""
    try:
        payload = {"query": "MATCH (n:Person) RETURN n LIMIT 5"}
        r = requests.post(f"{base}/graph/query", headers=headers, json=payload, timeout=60)
        data = ensure_ok(r)
        # Accept both results and records
        results = data.get("results", data.get("records", []))
        if r.ok and isinstance(results, list):
            log_test("POST /graph/query", "PASS", f"Query returned {len(results)} result(s)")
            return True
        else:
            log_test("POST /graph/query", "FAIL", f"Unexpected response: {str(data)[:200]}")
            return False
    except Exception as e:
        log_test("POST /graph/query", "FAIL", f"Exception: {e}")
        return False


# =============================================================================
# Test Suite Runner
# =============================================================================


def run_all_tests(
    base: str,
    headers: Dict[str, str],
    skip_meta: bool = False,
    skip_chat: bool = False,
    skip_vector: bool = False,
    skip_graph: bool = False,
    skip_cleanup: bool = False,
) -> bool:
    """
    Run all integration tests.

    Args:
        base: API Gateway base URL
        headers: Authentication headers
        skip_meta: Skip meta endpoint tests
        skip_chat: Skip chat/embed/rerank tests
        skip_vector: Skip vector endpoint tests
        skip_graph: Skip graph endpoint tests
        skip_cleanup: Skip cleanup after tests

    Returns:
        True if all tests passed, False otherwise.
    """
    print("\n" + "=" * 70)
    print("FreeRoute RAG Infra - Enhanced Integration Test Suite")
    print("=" * 70 + "\n")

    all_passed = True

    # Meta endpoints
    if not skip_meta:
        print("📋 Meta Endpoints")
        print("-" * 70)
        all_passed &= test_health(base)
        time.sleep(0.1)
        all_passed &= test_version(base)
        time.sleep(0.1)
        all_passed &= test_whoami(base, headers)
        time.sleep(0.1)
        all_passed &= test_metrics(base)
        print()

    # Chat & Embedding endpoints
    if not skip_chat:
        print("💬 Chat & Embedding Endpoints")
        print("-" * 70)
        all_passed &= test_chat(base, headers)
        time.sleep(0.1)
        all_passed &= test_embed(base, headers)
        time.sleep(0.1)
        all_passed &= test_openai_style_endpoints(base, headers)
        time.sleep(0.1)
        all_passed &= test_rerank(base, headers)
        print()

    # Vector endpoints
    if not skip_vector:
        print("🔍 Vector Endpoints")
        print("-" * 70)
        all_passed &= test_index_chunks(base, headers)
        time.sleep(0.1)
        all_passed &= test_search(base, headers)
        time.sleep(0.1)
        all_passed &= test_retrieve(base, headers)
        print()

    # Graph endpoints
    if not skip_graph:
        print("🕸️  Graph Endpoints")
        print("-" * 70)
        all_passed &= test_graph_probe(base, headers)
        time.sleep(0.1)
        all_passed &= test_graph_extract(base, headers)
        time.sleep(0.1)
        all_passed &= test_graph_upsert(base, headers)
        time.sleep(0.1)
        all_passed &= test_graph_query(base, headers)
        print()

    # Cleanup test data
    if not skip_cleanup:
        print("🧹 Cleanup Test Data")
        print("-" * 70)
        if not skip_vector:
            cleanup_vector_data(base, headers)
            time.sleep(0.1)
        if not skip_graph:
            cleanup_graph_data(base, headers)
            time.sleep(0.1)
        print()

    # Print summary
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    total = test_results["passed"] + test_results["failed"] + test_results["skipped"]
    print(f"Total:   {total}")
    print(f"✅ Passed:  {test_results['passed']}")
    print(f"❌ Failed:  {test_results['failed']}")
    print(f"⏭️  Skipped: {test_results['skipped']}")

    if test_results["failed"] > 0:
        print(f"\n⚠️  {test_results['failed']} test(s) failed!")
        return False
    else:
        print("\n🎉 All tests passed!")
        return True


def main():
    """Main entry point for the smoke test suite."""
    ap = argparse.ArgumentParser(
        description="FreeRoute RAG Infra – Enhanced API Gateway Integration Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests
  python test_gateway_smoke.py

  # Run with custom endpoint
  python test_gateway_smoke.py --base http://localhost:8000

  # Skip specific test categories
  python test_gateway_smoke.py --skip-graph --skip-vector

  # Use custom API key
  python test_gateway_smoke.py --key my-secret-key

  # Skip cleanup (leave test data for inspection)
  python test_gateway_smoke.py --skip-cleanup
        """,
    )
    ap.add_argument("--base", default=DEFAULT_BASE, help="API Gateway base URL")
    ap.add_argument("--key", default=DEFAULT_KEY, help="API key for authentication")
    ap.add_argument("--auth-header", default=DEFAULT_HEADER, help="Authentication header name")
    ap.add_argument("--skip-meta", action="store_true", help="Skip meta endpoint tests")
    ap.add_argument("--skip-chat", action="store_true", help="Skip chat/embed/rerank tests")
    ap.add_argument("--skip-vector", action="store_true", help="Skip vector endpoint tests")
    ap.add_argument("--skip-graph", action="store_true", help="Skip graph endpoint tests")
    ap.add_argument("--skip-cleanup", action="store_true", help="Skip cleanup after tests (留下測試數據)")
    ap.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = ap.parse_args()

    headers = make_headers(args.key, args.auth_header)

    if args.verbose:
        print(f"Base URL: {args.base}")
        print(f"Auth Header: {args.auth_header}")
        print(f"Headers: {headers}")
        print(f"Test Collection: {TEST_COLLECTION}")
        print(f"Test Node IDs: {TEST_NODE_IDS}")
        print(f"Test Doc IDs: {TEST_DOC_IDS}\n")

    success = run_all_tests(
        args.base,
        headers,
        skip_meta=args.skip_meta,
        skip_chat=args.skip_chat,
        skip_vector=args.skip_vector,
        skip_graph=args.skip_graph,
        skip_cleanup=args.skip_cleanup,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
