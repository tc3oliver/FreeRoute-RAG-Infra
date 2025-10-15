"""
Unit tests for services/gateway/middleware.py
"""

import json
import logging
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

# Setup schema path before any gateway imports
ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))


class TestRequestIdMiddleware:
    """Test request ID middleware functionality."""

    @pytest.mark.asyncio
    async def test_add_request_id_new_id(self):
        """Test that middleware generates new request ID if not present."""
        from services.gateway.middleware import add_request_id

        request = SimpleNamespace(headers={}, state=SimpleNamespace(), client=SimpleNamespace(host="127.0.0.1"))

        async def call_next(req):
            response = SimpleNamespace(headers={})
            return response

        response = await add_request_id(request, call_next)

        assert hasattr(request.state, "request_id")
        assert isinstance(request.state.request_id, str)
        assert len(request.state.request_id) > 0
        assert response.headers["X-Request-ID"] == request.state.request_id

    @pytest.mark.asyncio
    async def test_add_request_id_preserve_existing(self):
        """Test that middleware preserves existing X-Request-ID."""
        from services.gateway.middleware import add_request_id

        existing_id = "existing-request-id-123"

        # Create a mock headers object that supports get
        class MockHeaders(dict):
            def get(self, key, default=None):
                if key == "X-Request-ID":
                    return existing_id
                return default

        request = SimpleNamespace(
            headers=MockHeaders(), state=SimpleNamespace(), client=SimpleNamespace(host="127.0.0.1")
        )

        async def call_next(req):
            response = SimpleNamespace(headers={})
            return response

        response = await add_request_id(request, call_next)

        assert request.state.request_id == existing_id
        assert response.headers["X-Request-ID"] == existing_id

    @pytest.mark.asyncio
    async def test_add_request_id_no_client(self):
        """Test middleware handles missing client gracefully."""
        from services.gateway.middleware import add_request_id

        class MockHeaders(dict):
            def get(self, key, default=None):
                return None

        request = SimpleNamespace(headers=MockHeaders(), state=SimpleNamespace(), client=None)

        async def call_next(req):
            response = SimpleNamespace(headers={})
            return response

        response = await add_request_id(request, call_next)

        assert hasattr(request.state, "request_id")
        assert response.headers["X-Request-ID"] == request.state.request_id


class TestRequestContextFilter:
    """Test logging filter for request context."""

    def test_filter_adds_request_context(self):
        """Test that filter adds request context to log records."""
        from services.gateway.middleware import RequestContextFilter, request_ctx

        filter_obj = RequestContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="test", args=(), exc_info=None
        )

        # Set context
        token = request_ctx.set({"request_id": "req-123", "client_ip": "192.168.1.1", "start_time": time.time()})

        try:
            result = filter_obj.filter(record)
            assert result is True
            assert record.request_id == "req-123"
            assert record.client_ip == "192.168.1.1"
            assert hasattr(record, "duration_ms")
            assert record.duration_ms >= 0
        finally:
            request_ctx.reset(token)

    def test_filter_handles_missing_context(self):
        """Test filter handles missing context gracefully."""
        from services.gateway.middleware import RequestContextFilter, request_ctx

        filter_obj = RequestContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="test", args=(), exc_info=None
        )

        # Clear context
        request_ctx.set({})

        result = filter_obj.filter(record)
        assert result is True
        assert record.request_id == "-"
        assert record.client_ip == "-"
        assert record.duration_ms == 0

    def test_filter_adds_event_field(self):
        """Test that filter ensures event field exists."""
        from services.gateway.middleware import RequestContextFilter

        filter_obj = RequestContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="test", args=(), exc_info=None
        )

        filter_obj.filter(record)
        assert hasattr(record, "event")
        assert record.event == "-"


class TestLogEvent:
    """Test log_event utility function."""

    def test_log_event_basic(self, caplog):
        """Test basic log event with default level."""
        from services.gateway.middleware import log_event

        with caplog.at_level(logging.INFO, logger="gateway"):
            log_event("test message", event="test.event")

        assert len(caplog.records) == 1
        assert caplog.records[0].message == "test message"

    def test_log_event_with_metadata(self, caplog):
        """Test log event with additional metadata."""
        from services.gateway.middleware import log_event

        with caplog.at_level(logging.INFO, logger="gateway"):
            log_event("test message", event="test.event", user_id="user123", action="login")

        assert len(caplog.records) == 1
        # Extra fields are in the LogRecord but may not show in message
        # We'd need to check the record's attributes directly

    def test_log_event_custom_level(self, caplog):
        """Test log event with custom log level."""
        from services.gateway.middleware import log_event

        with caplog.at_level(logging.WARNING, logger="gateway"):
            log_event("warning message", event="test.warning", level=logging.WARNING)

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.WARNING


class TestPrometheusMiddleware:
    """Test Prometheus metrics middleware."""

    @pytest.mark.asyncio
    async def test_prometheus_middleware_disabled(self, monkeypatch):
        """Test middleware when Prometheus is disabled."""
        from services.gateway.middleware import prometheus_middleware

        monkeypatch.setattr("services.gateway.middleware.METRICS_ENABLED", False)

        request = SimpleNamespace(url=SimpleNamespace(path="/test"), method="GET")

        async def call_next(req):
            return SimpleNamespace(status_code=200)

        response = await prometheus_middleware(request, call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_prometheus_middleware_enabled(self, monkeypatch):
        """Test middleware when Prometheus is enabled."""
        # This test requires prometheus-client to be installed
        try:
            from prometheus_client import CollectorRegistry, Counter, Histogram

            from services.gateway.middleware import prometheus_middleware

            # Create test metrics
            test_registry = CollectorRegistry()
            test_counter = Counter(
                "test_requests_total", "Test counter", ["method", "endpoint", "http_status"], registry=test_registry
            )
            test_latency = Histogram(
                "test_request_duration_seconds", "Test latency", ["method", "endpoint"], registry=test_registry
            )

            monkeypatch.setattr("services.gateway.middleware.METRICS_ENABLED", True)
            monkeypatch.setattr("services.gateway.middleware.REQUEST_COUNTER", test_counter)
            monkeypatch.setattr("services.gateway.middleware.REQUEST_LATENCY", test_latency)

            request = SimpleNamespace(url=SimpleNamespace(path="/test"), method="GET")

            async def call_next(req):
                await asyncio.sleep(0.01)  # Simulate some processing
                return SimpleNamespace(status_code=200)

            import asyncio

            response = await prometheus_middleware(request, call_next)
            assert response.status_code == 200

            # Check that metrics were recorded
            assert test_counter.labels(method="GET", endpoint="/test", http_status="200")._value.get() == 1

        except ImportError:
            pytest.skip("prometheus-client not installed")

    @pytest.mark.asyncio
    async def test_prometheus_middleware_exception(self, monkeypatch):
        """Test middleware records metrics on exception."""
        try:
            from prometheus_client import CollectorRegistry, Counter, Histogram

            from services.gateway.middleware import prometheus_middleware

            test_registry = CollectorRegistry()
            test_counter = Counter(
                "test_requests_total", "Test counter", ["method", "endpoint", "http_status"], registry=test_registry
            )
            test_latency = Histogram(
                "test_request_duration_seconds", "Test latency", ["method", "endpoint"], registry=test_registry
            )

            monkeypatch.setattr("services.gateway.middleware.METRICS_ENABLED", True)
            monkeypatch.setattr("services.gateway.middleware.REQUEST_COUNTER", test_counter)
            monkeypatch.setattr("services.gateway.middleware.REQUEST_LATENCY", test_latency)

            request = SimpleNamespace(url=SimpleNamespace(path="/error"), method="POST")

            async def call_next(req):
                raise ValueError("Test error")

            with pytest.raises(ValueError, match="Test error"):
                await prometheus_middleware(request, call_next)

            # Check that error metric was recorded
            assert test_counter.labels(method="POST", endpoint="/error", http_status="500")._value.get() == 1

        except ImportError:
            pytest.skip("prometheus-client not installed")


class TestMetricsConstants:
    """Test metrics-related constants and imports."""

    def test_metrics_enabled_flag_exists(self):
        """Test that METRICS_ENABLED flag exists."""
        from services.gateway.middleware import METRICS_ENABLED

        assert isinstance(METRICS_ENABLED, bool)

    def test_content_type_latest_exists(self):
        """Test that CONTENT_TYPE_LATEST is defined."""
        from services.gateway.middleware import CONTENT_TYPE_LATEST

        assert isinstance(CONTENT_TYPE_LATEST, str)
        assert "text/plain" in CONTENT_TYPE_LATEST or "charset" in CONTENT_TYPE_LATEST

    def test_metrics_registry_when_enabled(self):
        """Test metrics registry when Prometheus is available."""
        from services.gateway.middleware import METRICS_ENABLED, METRICS_REG

        if METRICS_ENABLED:
            assert METRICS_REG is not None
        else:
            assert METRICS_REG is None

    def test_metrics_counters_when_enabled(self):
        """Test metrics counters when Prometheus is available."""
        from services.gateway.middleware import METRICS_ENABLED, REQUEST_COUNTER, REQUEST_LATENCY

        if METRICS_ENABLED:
            assert REQUEST_COUNTER is not None
            assert REQUEST_LATENCY is not None
        else:
            assert REQUEST_COUNTER is None
            assert REQUEST_LATENCY is None
