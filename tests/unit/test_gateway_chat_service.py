"""
Unit tests for AsyncChatService.

Tests chat completion, embedding generation, and model normalization.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Set GRAPH_SCHEMA_PATH environment variable before any imports
_test_dir = Path(__file__).parent.parent.parent
_schema_path = _test_dir / "schemas" / "graph_schema.json"

# Create a temporary schema if it doesn't exist (for pre-commit environment)
if not _schema_path.exists():
    import tempfile

    _schema_path = Path(tempfile.mktemp(suffix=".json"))
    _schema_path.write_text(json.dumps({"type": "object", "properties": {}}))

os.environ["GRAPH_SCHEMA_PATH"] = str(_schema_path)

import services.gateway.services.chat_service as chat_service_mod  # noqa: E402

# Import after setting environment variable (noqa to suppress import-order warnings)
from services.gateway.models import ChatReq, EmbedReq  # noqa: E402


class TestAsyncChatService:
    """Test suite for AsyncChatService."""

    @pytest.fixture
    def chat_service(self):
        return chat_service_mod.AsyncChatService()

    @pytest.fixture
    def mock_litellm_client(self):
        with patch("services.gateway.services.chat_service.get_async_litellm_client") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    # =========================================================================
    # Test: chat() - 基本聊天功能
    # =========================================================================

    @pytest.mark.asyncio
    async def test_chat_basic_success(self, monkeypatch):
        """Test basic chat completion with text response."""
        # Mock LiteLLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="This is a test response"))]
        mock_response.model = "gpt-4o-mini"

        from unittest.mock import AsyncMock

        mock_create = AsyncMock(return_value=mock_response)

        class MockChatCompletions:
            create = mock_create

        class MockChat:
            completions = MockChatCompletions()

        class MockClient:
            chat = MockChat()

        async def _mock():
            return MockClient()

        monkeypatch.setattr(
            "services.gateway.services.chat_service.get_async_litellm_client",
            _mock,
        )

        # Create service and test
        service = chat_service_mod.AsyncChatService()
        req = ChatReq(
            model="rag-answer",
            messages=[{"role": "user", "content": "Hello"}],
        )
        result = await service.chat(req, "127.0.0.1")
        # Assertions
        assert result["ok"] is True
        assert result["data"] == "This is a test response"
        assert result["meta"]["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_chat_json_response(self, monkeypatch):
        """Test chat completion with JSON response."""
        # Mock LiteLLM response with JSON
        json_output = {"answer": "42", "reasoning": "It's the answer"}
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps(json_output)))]
        mock_response.model = "gpt-4o-mini"

        from unittest.mock import AsyncMock

        mock_create = AsyncMock(return_value=mock_response)

        class MockChatCompletions:
            create = mock_create

        class MockChat:
            completions = MockChatCompletions()

        class MockClient:
            chat = MockChat()

        async def _mock():
            return MockClient()

        monkeypatch.setattr(
            "services.gateway.services.chat_service.get_async_litellm_client",
            _mock,
        )

        # Create service and test
        service = chat_service_mod.AsyncChatService()
        req = ChatReq(
            model="rag-answer",
            messages=[{"role": "user", "content": "What is the answer?"}],
            json_mode=True,
        )
        result = await service.chat(req, "127.0.0.1")
        # Assertions
        assert result["ok"] is True
        assert result["data"] == json_output
        assert result["meta"]["model"] == "gpt-4o-mini"
        # Verify JSON mode was requested
        call_kwargs = service.client.chat.completions.create.call_args[1]
        assert "response_format" in call_kwargs
        assert call_kwargs["response_format"]["type"] == "json_object"

    @pytest.mark.asyncio
    async def test_chat_with_temperature(self, monkeypatch):
        """Test chat completion with custom temperature."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Creative response"))]
        mock_response.model = "gpt-4o-mini"

        from unittest.mock import AsyncMock

        mock_create = AsyncMock(return_value=mock_response)

        class MockChatCompletions:
            create = mock_create

        class MockChat:
            completions = MockChatCompletions()

        class MockClient:
            chat = MockChat()

        async def _mock():
            return MockClient()

        monkeypatch.setattr(
            "services.gateway.services.chat_service.get_async_litellm_client",
            _mock,
        )

        # Create service and test
        service = chat_service_mod.AsyncChatService()
        req = ChatReq(
            model="rag-answer",
            messages=[{"role": "user", "content": "Be creative"}],
            temperature=1.5,
        )
        await service.chat(req, "127.0.0.1")
        # Verify temperature was passed
        call_kwargs = service.client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 1.5

    @pytest.mark.asyncio
    async def test_chat_client_ip_tracking(self, monkeypatch):
        """Test that client IP is tracked in extra headers."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
        mock_response.model = "gpt-4o-mini"

        from unittest.mock import AsyncMock

        mock_create = AsyncMock(return_value=mock_response)

        class MockChatCompletions:
            create = mock_create

        class MockChat:
            completions = MockChatCompletions()

        class MockClient:
            chat = MockChat()

        async def _mock():
            return MockClient()

        monkeypatch.setattr(
            "services.gateway.services.chat_service.get_async_litellm_client",
            _mock,
        )

        # Create service and test
        service = chat_service_mod.AsyncChatService()
        req = ChatReq(
            model="rag-answer",
            messages=[{"role": "user", "content": "Hello"}],
        )
        await service.chat(req, "192.168.1.100")
        # Verify client IP was passed
        call_kwargs = service.client.chat.completions.create.call_args[1]
        assert call_kwargs["extra_headers"]["X-Client-IP"] == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_chat_with_retry_on_429(self, monkeypatch):
        """Test retry mechanism on 429 error."""
        # First call fails with 429, second succeeds
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Success after retry"))]
        mock_response.model = "gpt-4o-mini"

        from unittest.mock import AsyncMock

        call_count = {"count": 0}

        async def create_mock(**kwargs):
            call_count["count"] += 1
            if call_count["count"] == 1:
                raise Exception("HTTP 429 Too Many Requests")
            return mock_response

        class MockChatCompletions:
            create = AsyncMock(side_effect=create_mock)

        class MockChat:
            completions = MockChatCompletions()

        class MockClient:
            chat = MockChat()

        async def _mock():
            return MockClient()

        monkeypatch.setattr(
            "services.gateway.services.chat_service.get_async_litellm_client",
            _mock,
        )

        # Create service and test
        service = chat_service_mod.AsyncChatService()
        req = ChatReq(
            model="rag-answer",
            messages=[{"role": "user", "content": "Test retry"}],
        )
        result = await service.chat(req, "127.0.0.1")
        # Verify retry happened and succeeded
        assert result["ok"] is True
        assert call_count["count"] == 2

    # =========================================================================
    # Test: embed() - 嵌入生成
    # =========================================================================

    @pytest.mark.asyncio
    async def test_embed_single_text(self, monkeypatch):
        """Test embedding generation for single text."""
        # Mock LiteLLM embeddings response
        mock_data = [MagicMock(embedding=[0.1, 0.2, 0.3, 0.4, 0.5])]
        mock_response = MagicMock()
        mock_response.data = mock_data

        from unittest.mock import AsyncMock

        mock_create = AsyncMock(return_value=mock_response)

        class MockEmbeddings:
            create = mock_create

        class MockClient:
            embeddings = MockEmbeddings()

        async def _mock():
            return MockClient()

        monkeypatch.setattr(
            "services.gateway.services.chat_service.get_async_litellm_client",
            _mock,
        )

        # Create service and test
        service = chat_service_mod.AsyncChatService()
        req = EmbedReq(texts=["Hello world"])
        result = await service.embed(req)
        # Assertions
        assert result["ok"] is True
        assert len(result["vectors"]) == 1
        assert result["vectors"][0] == [0.1, 0.2, 0.3, 0.4, 0.5]
        assert result["dim"] == 5

    @pytest.mark.asyncio
    async def test_embed_multiple_texts(self, monkeypatch):
        """Test embedding generation for multiple texts."""
        # Mock LiteLLM embeddings response with multiple vectors
        mock_data = [
            MagicMock(embedding=[0.1, 0.2, 0.3]),
            MagicMock(embedding=[0.4, 0.5, 0.6]),
            MagicMock(embedding=[0.7, 0.8, 0.9]),
        ]
        mock_response = MagicMock()
        mock_response.data = mock_data

        from unittest.mock import AsyncMock

        mock_create = AsyncMock(return_value=mock_response)

        class MockEmbeddings:
            create = mock_create

        class MockClient:
            embeddings = MockEmbeddings()

        async def _mock():
            return MockClient()

        monkeypatch.setattr(
            "services.gateway.services.chat_service.get_async_litellm_client",
            _mock,
        )

        # Create service and test
        service = chat_service_mod.AsyncChatService()
        req = EmbedReq(texts=["Text 1", "Text 2", "Text 3"])
        result = await service.embed(req)
        # Assertions
        assert result["ok"] is True
        assert len(result["vectors"]) == 3
        assert result["dim"] == 3
        # Verify API call
        call_kwargs = service.client.embeddings.create.call_args[1]
        assert call_kwargs["model"] == "local-embed"
        assert call_kwargs["input"] == ["Text 1", "Text 2", "Text 3"]

    @pytest.mark.asyncio
    async def test_embed_empty_list(self, monkeypatch):
        """Test embedding generation with empty text list."""
        mock_response = MagicMock()
        mock_response.data = []

        class MockEmbeddings:
            async def create(self, **kwargs):
                return mock_response

        class MockClient:
            embeddings = MockEmbeddings()

        async def _mock():
            return MockClient()

        monkeypatch.setattr(
            "services.gateway.services.chat_service.get_async_litellm_client",
            _mock,
        )

        # Create service and test
        service = chat_service_mod.AsyncChatService()
        req = EmbedReq(texts=[])
        result = await service.embed(req)
        # Assertions
        assert result["ok"] is True
        assert result["vectors"] == []
        assert result["dim"] == 0

    # =========================================================================
    # Test: _normalize_model() - 模型名稱正規化
    # =========================================================================

    def test_normalize_model_valid_entrypoint(self):
        """Test normalization with valid entrypoint."""
        result = chat_service_mod.AsyncChatService._normalize_model("rag-answer", kind="chat")
        assert result == "rag-answer"

    def test_normalize_model_invalid_returns_default(self):
        """Test normalization with invalid model returns default."""
        result = chat_service_mod.AsyncChatService._normalize_model("invalid-model", kind="chat")
        # Should return default chat model
        from services.gateway.config import DEFAULTS

        assert result == DEFAULTS["chat"]

    def test_normalize_model_none_returns_default(self):
        """Test normalization with None returns default."""
        result = chat_service_mod.AsyncChatService._normalize_model(None, kind="chat")
        from services.gateway.config import DEFAULTS

        assert result == DEFAULTS["chat"]

    def test_normalize_model_empty_string_returns_default(self):
        """Test normalization with empty string returns default."""
        result = chat_service_mod.AsyncChatService._normalize_model("", kind="chat")
        from services.gateway.config import DEFAULTS

        assert result == DEFAULTS["chat"]

    def test_normalize_model_whitespace_trimmed(self):
        """Test normalization trims whitespace."""
        result = chat_service_mod.AsyncChatService._normalize_model("  rag-answer  ", kind="chat")
        assert result == "rag-answer"

    def test_normalize_model_graph_kind(self):
        """Test normalization for graph kind."""
        result = chat_service_mod.AsyncChatService._normalize_model("graph-extractor", kind="graph")
        assert result == "graph-extractor"

    # =========================================================================
    # Test: 錯誤處理
    # =========================================================================

    @pytest.mark.asyncio
    async def test_chat_api_error_propagates(self, monkeypatch):
        """Test that API errors are propagated."""

        class MockChatCompletions:
            async def create(self, **kwargs):
                raise Exception("API Error")

        class MockChat:
            completions = MockChatCompletions()

        class MockClient:
            chat = MockChat()

        async def _mock():
            return MockClient()

        monkeypatch.setattr(
            "services.gateway.services.chat_service.get_async_litellm_client",
            _mock,
        )

        service = chat_service_mod.AsyncChatService()
        req = ChatReq(
            model="rag-answer",
            messages=[{"role": "user", "content": "Test"}],
        )
        with pytest.raises(Exception, match="API Error"):
            await service.chat(req, "127.0.0.1")

    @pytest.mark.asyncio
    async def test_embed_api_error_propagates(self, monkeypatch):
        """Test that embedding API errors are propagated."""

        class MockEmbeddings:
            async def create(self, **kwargs):
                raise Exception("Embedding Error")

        class MockClient:
            embeddings = MockEmbeddings()

        async def _mock():
            return MockClient()

        monkeypatch.setattr(
            "services.gateway.services.chat_service.get_async_litellm_client",
            _mock,
        )

        service = chat_service_mod.AsyncChatService()
        req = EmbedReq(texts=["Test"])
        with pytest.raises(Exception, match="Embedding Error"):
            await service.embed(req)
