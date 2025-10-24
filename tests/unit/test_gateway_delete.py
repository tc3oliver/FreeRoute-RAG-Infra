"""
Gateway 刪除 API 單元測試
"""

# 設定 schema 路徑必須在 import gateway modules 之前
import os
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.gateway.app import app

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))


@pytest.fixture(autouse=True, scope="module")
def override_require_key():
    from services.gateway.app import app
    from services.gateway.routers import delete

    app.dependency_overrides[delete.require_key] = lambda: "tenant-123"
    yield
    app.dependency_overrides = {}


client = TestClient(app)


def test_delete_vector(monkeypatch):
    """測試 /delete/vector API 多租戶刪除"""

    async def fake_delete(self, req, tenant_id="default"):
        assert req.collection == "test-coll"
        assert tenant_id == "tenant-123"
        if req.doc_id:
            assert req.doc_id == "doc-1"
            return 1
        return 5

    monkeypatch.setattr("services.gateway.services.async_vector_service.AsyncVectorService.delete", fake_delete)

    # 刪除單一 doc
    req = {"collection": "test-coll", "doc_id": "doc-1"}
    headers = {"X-API-Key": "tenant-123"}
    resp = client.post("/delete/vector", json=req, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"]
    assert resp.json()["deleted"] == 1

    # 刪除整個 collection
    req = {"collection": "test-coll"}
    resp = client.post("/delete/vector", json=req, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"]
    assert resp.json()["deleted"] == 5


def test_delete_graph(monkeypatch):
    """測試 /delete/graph API 多租戶刪除"""

    async def fake_delete(self, req, tenant_id="default"):
        assert tenant_id == "tenant-123"
        if req.doc_id:
            assert req.doc_id == "doc-2"
            return 2
        return 10

    monkeypatch.setattr("services.gateway.services.async_graph_service.AsyncGraphService.delete", fake_delete)

    # 刪除單一 doc
    req = {"doc_id": "doc-2"}
    headers = {"X-API-Key": "tenant-123"}
    resp = client.post("/delete/graph", json=req, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"]
    assert resp.json()["deleted"] == 2

    # 刪除整個 tenant
    req = {}
    resp = client.post("/delete/graph", json=req, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"]
    assert resp.json()["deleted"] == 10
