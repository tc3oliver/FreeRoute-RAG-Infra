import importlib

# Ensure services is importable
import os
import sys

from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _import_app_with_schema():
    # Ensure the gateway loads the local schema from the repo during tests
    os.environ["GRAPH_SCHEMA_PATH"] = os.path.join(ROOT, "schemas", "graph_schema.json")
    module = importlib.import_module("services.gateway.app")
    importlib.reload(module)
    return module


def test_metrics_disabled_by_default(monkeypatch):
    # Import app with valid schema path
    app_mod = _import_app_with_schema()
    # Simulate metrics disabled at runtime (soft-dependency behavior)
    monkeypatch.setattr(app_mod, "METRICS_ENABLED", False)
    app = app_mod.app
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 204


def test_metrics_enabled_and_exposed():
    app_mod = _import_app_with_schema()
    # If prometheus-client isn't available in the test runtime (e.g. pre-commit
    # isolated env), the module sets METRICS_ENABLED = False. Skip the test in
    # that case to avoid false failures during pre-commit hooks.
    import pytest

    if not getattr(app_mod, "METRICS_ENABLED", False):
        pytest.skip("prometheus-client not available in this runtime")
    # Ensure prometheus-client was imported and enabled
    app = app_mod.app
    client = TestClient(app)
    # hit an endpoint to create some metrics
    r1 = client.get("/health")
    assert r1.status_code == 200
    r = client.get("/metrics")
    # When prometheus-client is installed, /metrics should return text with metric names
    assert r.status_code == 200
    assert "gateway_requests_total" in r.text
