import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict

from fastapi import Request

request_ctx: ContextVar[Dict[str, Any]] = ContextVar("request_ctx", default={})


async def add_request_id(request: Request, call_next):
    """Attach X-Request-ID to every request/response for tracing."""
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = rid
    token = request_ctx.set(
        {
            "request_id": rid,
            "client_ip": request.client.host if request.client else "-",
            "start_time": time.time(),
        }
    )
    try:
        response = await call_next(request)
    finally:
        request_ctx.reset(token)
    response.headers["X-Request-ID"] = rid
    return response


class RequestContextFilter(logging.Filter):
    """Attach current request context fields to LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = request_ctx.get({})
        record.request_id = ctx.get("request_id", "-")
        record.client_ip = ctx.get("client_ip", "-")
        start = ctx.get("start_time")
        if start:
            record.duration_ms = int((time.time() - start) * 1000)
        else:
            record.duration_ms = 0
        if not hasattr(record, "event"):
            record.event = getattr(record, "event", "-")
        return True


def log_event(msg: str, event: str, level: int = logging.INFO, **meta: Any) -> None:
    extra = {"event": event}
    extra.update(meta)
    logging.getLogger("gateway").log(level, msg, extra=extra)


# Optional Prometheus metrics (soft dependency)
try:
    from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

    METRICS_ENABLED = True
    METRICS_REG = CollectorRegistry()
    REQUEST_COUNTER = Counter(
        "gateway_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "http_status"],
        registry=METRICS_REG,
    )
    REQUEST_LATENCY = Histogram(
        "gateway_request_duration_seconds",
        "Request latency",
        ["method", "endpoint"],
        registry=METRICS_REG,
    )
except Exception:  # pragma: no cover - optional dependency
    METRICS_ENABLED = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    METRICS_REG = None
    REQUEST_COUNTER = None
    REQUEST_LATENCY = None


async def prometheus_middleware(request: Request, call_next):
    if not METRICS_ENABLED:
        return await call_next(request)
    path = request.url.path
    method = request.method
    try:
        with REQUEST_LATENCY.labels(method=method, endpoint=path).time():
            resp = await call_next(request)
    except Exception:
        REQUEST_COUNTER.labels(method=method, endpoint=path, http_status="500").inc()
        raise
    status = str(resp.status_code)
    REQUEST_COUNTER.labels(method=method, endpoint=path, http_status=status).inc()
    return resp
