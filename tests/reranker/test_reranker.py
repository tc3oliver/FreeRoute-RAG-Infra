#!/usr/bin/env python3
import os

import requests

BASE = os.getenv("RERANKER_BASE", "http://localhost:9080")


def test_health():
    r = requests.get(f"{BASE}/health", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "model" in data
