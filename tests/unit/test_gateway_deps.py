"""
Unit tests for services/gateway/deps.py
"""

import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

# Setup schema path before any gateway imports
ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))


class TestRequireKey:
    """Test API key authentication dependency."""

    def test_valid_api_key_in_header(self, monkeypatch):
        """Test valid API key in X-API-Key header."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "test-key-1,test-key-2")
        # Force reload to pick up env var
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        # Call directly with string values (bypassing FastAPI dependency injection)
        result = deps.require_key(x_api_key="test-key-1", authorization=None)
        assert result is True

    def test_valid_api_key_with_whitespace(self, monkeypatch):
        """Test valid API key with surrounding whitespace."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "test-key")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        result = deps.require_key(x_api_key="  test-key  ", authorization=None)
        assert result is True

    def test_valid_bearer_token(self, monkeypatch):
        """Test valid Bearer token in Authorization header."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "secret-token")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        result = deps.require_key(x_api_key=None, authorization="Bearer secret-token")
        assert result is True

    def test_valid_bearer_token_with_whitespace(self, monkeypatch):
        """Test Bearer token with whitespace."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "secret-token")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        result = deps.require_key(x_api_key=None, authorization="Bearer  secret-token  ")
        assert result is True

    def test_bearer_token_case_insensitive(self, monkeypatch):
        """Test that 'bearer' is case-insensitive."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "token123")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        result = deps.require_key(x_api_key=None, authorization="bearer token123")
        assert result is True

        result = deps.require_key(x_api_key=None, authorization="BEARER token123")
        assert result is True

        result = deps.require_key(x_api_key=None, authorization="BeArEr token123")
        assert result is True

    def test_invalid_api_key(self, monkeypatch):
        """Test invalid API key raises 401."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "valid-key")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        with pytest.raises(HTTPException) as exc:
            deps.require_key(x_api_key="invalid-key", authorization=None)

        assert exc.value.status_code == 401
        assert "missing or invalid API key" in exc.value.detail

    def test_missing_api_key(self, monkeypatch):
        """Test missing API key raises 401."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "some-key")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        with pytest.raises(HTTPException) as exc:
            deps.require_key(x_api_key=None, authorization=None)

        assert exc.value.status_code == 401
        assert "missing or invalid API key" in exc.value.detail

    def test_empty_api_key(self, monkeypatch):
        """Test empty API key raises 401."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "valid-key")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        with pytest.raises(HTTPException) as exc:
            deps.require_key(x_api_key="", authorization=None)

        assert exc.value.status_code == 401

    def test_empty_bearer_token(self, monkeypatch):
        """Test empty Bearer token raises 401."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "valid-key")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        with pytest.raises(HTTPException) as exc:
            deps.require_key(x_api_key=None, authorization="Bearer ")

        assert exc.value.status_code == 401

    def test_malformed_authorization_header(self, monkeypatch):
        """Test malformed Authorization header raises 401."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "valid-key")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        with pytest.raises(HTTPException) as exc:
            deps.require_key(x_api_key=None, authorization="Basic some-token")

        assert exc.value.status_code == 401

    def test_x_api_key_takes_precedence(self, monkeypatch):
        """Test that X-API-Key takes precedence over Authorization."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "key-from-x-api-key,key-from-bearer")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        # Valid X-API-Key, invalid Bearer
        result = deps.require_key(x_api_key="key-from-x-api-key", authorization="Bearer wrong-token")
        assert result is True

    def test_multiple_valid_keys(self, monkeypatch):
        """Test multiple valid keys in configuration."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "key1,key2,key3")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        assert deps.require_key(x_api_key="key1", authorization=None) is True
        assert deps.require_key(x_api_key="key2", authorization=None) is True
        assert deps.require_key(x_api_key="key3", authorization=None) is True

    def test_keys_with_commas_and_spaces(self, monkeypatch):
        """Test key parsing with spaces around commas."""
        monkeypatch.setenv("API_GATEWAY_KEYS", " key1 , key2 , key3 ")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        assert deps.require_key(x_api_key="key1", authorization=None) is True
        assert deps.require_key(x_api_key="key2", authorization=None) is True
        assert deps.require_key(x_api_key="key3", authorization=None) is True

    def test_default_dev_key(self, monkeypatch):
        """Test default 'dev-key' when no env var set."""
        monkeypatch.delenv("API_GATEWAY_KEYS", raising=False)
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        result = deps.require_key(x_api_key="dev-key", authorization=None)
        assert result is True

    def test_empty_keys_config(self, monkeypatch):
        """Test behavior with empty API_GATEWAY_KEYS."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        # Should fall back to default "dev-key" when filter removes empty strings
        # But actually, it filters out empty strings, so API_KEYS becomes empty set
        with pytest.raises(HTTPException) as exc:
            deps.require_key(x_api_key="any-key", authorization=None)

        assert exc.value.status_code == 401

    def test_only_whitespace_keys(self, monkeypatch):
        """Test configuration with only whitespace keys."""
        monkeypatch.setenv("API_GATEWAY_KEYS", "  ,  ,  ")
        import importlib

        from services.gateway import deps

        importlib.reload(deps)

        # Empty set after filtering
        with pytest.raises(HTTPException) as exc:
            deps.require_key(x_api_key="any-key", authorization=None)

        assert exc.value.status_code == 401
