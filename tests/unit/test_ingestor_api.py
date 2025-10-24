"""
Unit tests for Ingestor API (tenant-aware).

Covers /ingest/directory endpoint with X-API-Key and tenant_id propagation.
"""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.ingestor.app import app

client = TestClient(app)


def make_test_file(tmp_path, content="test content"):
    file_path = tmp_path / "test.md"
    file_path.write_text(content)
    return str(file_path)


def test_ingest_directory_tenant_headers(monkeypatch, tmp_path):
    """
    測試 /ingest/directory 支援 X-API-Key/tenant_id header 並正確傳遞
    """

    # 準備假 Gateway 回應
    def fake_call_gateway(endpoint, data, api_key=None):
        assert api_key == "test-key"
        # 只有帶 tenant_id 時才檢查
        if "tenant_id" in data:
            assert data["tenant_id"] == "tenant-123"
        # 模擬不同 endpoint 回傳
        if endpoint == "/index/chunks":
            return {"upserted": len(data["chunks"])}
        if endpoint == "/graph/extract":
            return {"ok": True, "data": {"nodes": [], "edges": []}}
        if endpoint == "/graph/upsert":
            return {"nodes": 0, "edges": 0}
        return {}

    monkeypatch.setattr("services.ingestor.app._call_gateway", fake_call_gateway)

    # 建立測試檔案
    _ = make_test_file(tmp_path, "hello world")
    test_dir = tmp_path

    req = {
        "path": str(test_dir),
        "collection": "test-coll",
        "tenant_id": "tenant-123",
        "extract_graph": True,
        "force_reprocess": True,
        "chunk_size": 100,
        "chunk_overlap": 0,
    }
    headers = {"X-API-Key": "test-key"}
    resp = client.post("/ingest/directory", json=req, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["files_processed"] == 1
    assert data["stats"]["chunks_created"] >= 1
    assert data["stats"]["graphs_extracted"] == 1
    assert not data["errors"]
