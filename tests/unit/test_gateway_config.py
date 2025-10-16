"""
Unit tests for services/gateway/config.py
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


class TestConfigEnvironmentVariables:
    """Test configuration loading from environment variables."""

    def test_litellm_base_default(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.delenv("LITELLM_BASE", raising=False)
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.LITELLM_BASE == "http://litellm:4000/v1"

    def test_litellm_base_custom(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.setenv("LITELLM_BASE", "http://custom:5000/v1/")
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.LITELLM_BASE == "http://custom:5000/v1"

    def test_litellm_key_default(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.delenv("LITELLM_KEY", raising=False)
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.LITELLM_KEY == "sk-admin"

    def test_reranker_url_default(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.delenv("RERANKER_URL", raising=False)
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.RERANKER_URL == "http://reranker:8080"

    def test_neo4j_credentials_from_env(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "admin")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.NEO4J_URI == "bolt://localhost:7687"
        assert config.NEO4J_USER == "admin"
        assert config.NEO4J_PASSWORD == "secret"


class TestGraphSchemaLoading:
    """Test graph schema loading and validation."""

    def test_load_valid_schema(self, monkeypatch, tmp_path):
        """Test loading a valid JSON Schema."""
        schema_path = tmp_path / "valid_schema.json"
        schema_content = {
            "type": "object",
            "properties": {"nodes": {"type": "array"}, "edges": {"type": "array"}},
            "required": ["nodes", "edges"],
        }
        schema_path.write_text(json.dumps(schema_content))

        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.GRAPH_JSON_SCHEMA == schema_content
        assert isinstance(config.GRAPH_SCHEMA_HASH, str)
        assert len(config.GRAPH_SCHEMA_HASH) == 64  # SHA256 hash

    def test_load_schema_file_not_found(self, monkeypatch, tmp_path):
        """Test error when schema file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.json"
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(nonexistent))

        import importlib

        from services.gateway import config

        with pytest.raises(RuntimeError, match="graph_schema.json not found"):
            importlib.reload(config)

    def test_load_schema_invalid_json(self, monkeypatch, tmp_path):
        """Test error when schema file contains invalid JSON."""
        schema_path = tmp_path / "invalid.json"
        schema_path.write_text("{invalid json")

        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        import importlib

        from services.gateway import config

        with pytest.raises(RuntimeError, match="graph_schema.json load failed"):
            importlib.reload(config)

    def test_load_schema_not_valid_json_schema(self, monkeypatch, tmp_path):
        """Test error when schema is not a valid JSON Schema."""
        schema_path = tmp_path / "not_schema.json"
        schema_path.write_text(json.dumps({"invalid": "schema"}))

        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        import importlib

        from services.gateway import config

        with pytest.raises(RuntimeError, match="missing top-level 'type'"):
            importlib.reload(config)

    def test_schema_hash_consistency(self, monkeypatch, tmp_path):
        """Test that schema hash is consistent."""
        schema_path = tmp_path / "schema.json"
        schema_content = {"type": "object", "properties": {}}
        schema_path.write_text(json.dumps(schema_content))

        expected_hash = hashlib.sha256(json.dumps(schema_content).encode()).hexdigest()

        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.GRAPH_SCHEMA_HASH == expected_hash


class TestGraphWorkflowParameters:
    """Test graph extraction workflow configuration."""

    def test_graph_min_nodes_default(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.delenv("GRAPH_MIN_NODES", raising=False)
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.GRAPH_MIN_NODES == 1

    def test_graph_min_nodes_custom(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.setenv("GRAPH_MIN_NODES", "5")
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.GRAPH_MIN_NODES == 5

    def test_graph_min_edges_default(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.delenv("GRAPH_MIN_EDGES", raising=False)
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.GRAPH_MIN_EDGES == 1

    def test_graph_allow_empty_default(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.delenv("GRAPH_ALLOW_EMPTY", raising=False)
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.GRAPH_ALLOW_EMPTY is False

    def test_graph_allow_empty_true(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.setenv("GRAPH_ALLOW_EMPTY", "true")
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.GRAPH_ALLOW_EMPTY is True

    def test_graph_max_attempts_default(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.delenv("GRAPH_MAX_ATTEMPTS", raising=False)
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.GRAPH_MAX_ATTEMPTS == 2

    def test_provider_chain_default(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.delenv("GRAPH_PROVIDER_CHAIN", raising=False)
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert "graph-extractor" in config.PROVIDER_CHAIN
        assert "graph-extractor-o1mini" in config.PROVIDER_CHAIN
        assert "graph-extractor-gemini" in config.PROVIDER_CHAIN

    def test_provider_chain_custom(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.setenv("GRAPH_PROVIDER_CHAIN", "model1,model2,model3")
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.PROVIDER_CHAIN == ["model1", "model2", "model3"]

    def test_provider_chain_with_spaces(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.setenv("GRAPH_PROVIDER_CHAIN", " model1 , model2 , model3 ")
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.PROVIDER_CHAIN == ["model1", "model2", "model3"]


class TestAppConfiguration:
    """Test application-level configuration."""

    def test_app_version_default(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.delenv("APP_VERSION", raising=False)
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.APP_VERSION == "v0.1.2"

    def test_app_version_custom(self, monkeypatch, tmp_path):
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps({"type": "object"}))
        monkeypatch.setenv("GRAPH_SCHEMA_PATH", str(schema_path))
        monkeypatch.setenv("APP_VERSION", "v2.0.0")
        import importlib

        from services.gateway import config

        importlib.reload(config)
        assert config.APP_VERSION == "v2.0.0"

    def test_entrypoints_set(self):
        from services.gateway.config import ENTRYPOINTS

        assert "rag-answer" in ENTRYPOINTS
        assert "graph-extractor" in ENTRYPOINTS

    def test_defaults_dict(self):
        from services.gateway.config import DEFAULTS

        assert DEFAULTS["chat"] == "rag-answer"
        assert DEFAULTS["graph"] == "graph-extractor"


class TestSchemaValidatorFunction:
    """Test the _load_graph_schema function behavior."""

    def test_schema_validator_check(self, tmp_path):
        """Test that loaded schema passes JSON Schema validation."""
        from services.gateway.config import _load_graph_schema

        schema_path = tmp_path / "valid.json"
        valid_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"nodes": {"type": "array"}, "edges": {"type": "array"}},
        }
        schema_path.write_text(json.dumps(valid_schema))

        loaded = _load_graph_schema(str(schema_path))
        assert loaded == valid_schema

        # Verify it's a valid JSON Schema
        Draft202012Validator.check_schema(loaded)

    def test_schema_missing_type_field(self, tmp_path):
        """Test that schema without 'type' field raises error."""
        from services.gateway.config import _load_graph_schema

        schema_path = tmp_path / "no_type.json"
        schema_path.write_text(json.dumps({"properties": {}}))

        with pytest.raises(RuntimeError, match="missing top-level 'type'"):
            _load_graph_schema(str(schema_path))
