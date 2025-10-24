import hashlib
import json
import os
from typing import Any, Dict, List

from jsonschema import Draft202012Validator

# === 環境變數與全域參數 ===
LITELLM_BASE = os.environ.get("LITELLM_BASE", "http://litellm:4000/v1").rstrip("/")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "sk-admin")
RERANKER_URL = os.environ.get("RERANKER_URL", "http://reranker:8080")
QDRANT_URL = os.environ.get("QDRANT_URL")  # e.g., http://qdrant:6333
NEO4J_URI = os.environ.get("NEO4J_URI")  # e.g., bolt://neo4j:7687
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")

# 統一路徑：容器內掛載到 /app/schemas/graph_schema.json
GRAPH_SCHEMA_PATH = os.environ.get("GRAPH_SCHEMA_PATH", "/app/schemas/graph_schema.json")


def _load_graph_schema(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise RuntimeError(f"[FATAL] graph_schema.json not found at: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        raise RuntimeError(f"[FATAL] graph_schema.json load failed: {e}")
    if not isinstance(schema, dict) or "type" not in schema:
        raise RuntimeError("[FATAL] graph_schema.json invalid: missing top-level 'type'")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as e:
        raise RuntimeError(f"[FATAL] graph_schema.json is not a valid JSON Schema: {e}")
    return schema


GRAPH_JSON_SCHEMA: Dict[str, Any] = _load_graph_schema(GRAPH_SCHEMA_PATH)
with open(GRAPH_SCHEMA_PATH, "rb") as _f:
    GRAPH_SCHEMA_HASH = hashlib.sha256(_f.read()).hexdigest()


# Graph 工作流程參數（可環境覆蓋）
GRAPH_MIN_NODES = int(os.environ.get("GRAPH_MIN_NODES", "1"))
GRAPH_MIN_EDGES = int(os.environ.get("GRAPH_MIN_EDGES", "1"))
GRAPH_ALLOW_EMPTY = os.environ.get("GRAPH_ALLOW_EMPTY", "false").lower() == "true"
GRAPH_MAX_ATTEMPTS = int(os.environ.get("GRAPH_MAX_ATTEMPTS", "2"))
DEFAULT_PROVIDER_CHAIN: List[str] = ["graph-extractor", "graph-extractor-o1mini", "graph-extractor-gemini"]
ENV_PROVIDER_CHAIN: List[str] = [
    x.strip() for x in os.environ.get("GRAPH_PROVIDER_CHAIN", ",".join(DEFAULT_PROVIDER_CHAIN)).split(",") if x.strip()
]
PROVIDER_CHAIN: List[str] = ENV_PROVIDER_CHAIN if ENV_PROVIDER_CHAIN else DEFAULT_PROVIDER_CHAIN

APP_VERSION = os.environ.get("APP_VERSION", "v0.2.2")

# Entrypoints
ENTRYPOINTS = {"rag-answer", "graph-extractor"}
DEFAULTS = {"chat": "rag-answer", "graph": "graph-extractor"}
