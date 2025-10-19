import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Setup schema path before any gateway imports
ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "graph_schema.json"
os.environ.setdefault("GRAPH_SCHEMA_PATH", str(SCHEMA_PATH))


@pytest.mark.asyncio
async def test_get_async_litellm_client_returns_client(monkeypatch):
    # 直接 patch 模組內已綁定的 AsyncOpenAI 符號，並重置單例
    with patch("services.gateway.repositories.litellm_client.AsyncOpenAI", autospec=True) as mock_cls:
        import services.gateway.repositories.litellm_client as lcmod

        lcmod._async_client = None
        from services.gateway.repositories.litellm_client import get_async_litellm_client

        client = await get_async_litellm_client()
        mock_cls.assert_called_once()
        assert client is mock_cls.return_value


@pytest.mark.asyncio
async def test_get_async_neo4j_driver_success(monkeypatch):
    # 環境變數需在 import 前設定，且需 reload config 與目標模組
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost")
    monkeypatch.setenv("NEO4J_PASSWORD", "test")
    import importlib as _il

    from services.gateway import config as cfg

    _il.reload(cfg)
    import services.gateway.repositories.neo4j_client as nmod

    _il.reload(nmod)
    nmod._async_driver = None
    with patch("services.gateway.repositories.neo4j_client.importlib.import_module") as import_mod:
        mock_mod = type(
            "M", (), {"AsyncGraphDatabase": type("G", (), {"driver": staticmethod(lambda uri, auth=None: "driver")})}
        )
        import_mod.return_value = mock_mod
        driver = await nmod.get_async_neo4j_driver()
        assert driver == "driver"


@pytest.mark.asyncio
async def test_get_async_qdrant_client_success(monkeypatch):
    # 同理，需先設定環境變數並 reload config/模組
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    import importlib as _il

    from services.gateway import config as cfg

    _il.reload(cfg)
    import services.gateway.repositories.qdrant_client as qmod

    _il.reload(qmod)
    qmod._async_client = None
    with patch("services.gateway.repositories.qdrant_client.importlib.import_module") as import_mod:
        mock_mod = type("M", (), {"AsyncQdrantClient": staticmethod(lambda **kwargs: "client")})
        import_mod.return_value = mock_mod
        client = await qmod.get_async_qdrant_client()
        assert client == "client"


@pytest.mark.asyncio
async def test_ensure_qdrant_collection_async(monkeypatch):
    from services.gateway.repositories.qdrant_client import ensure_qdrant_collection_async

    mock_client = AsyncMock()
    mock_client.get_collection = AsyncMock(side_effect=Exception("Not found"))
    mock_client.recreate_collection = AsyncMock()
    with patch("services.gateway.repositories.qdrant_client.importlib.import_module") as import_mod:
        mock_models = type(
            "M",
            (),
            {
                "Distance": type("D", (), {"COSINE": "cosine"}),
                "VectorParams": lambda size, distance: {"size": size, "distance": distance},
            },
        )
        import_mod.return_value = mock_models
        await ensure_qdrant_collection_async(mock_client, "test", 384)
        mock_client.recreate_collection.assert_awaited_once()


@pytest.mark.asyncio
async def test_call_reranker_async(monkeypatch):
    from services.gateway.repositories.reranker_client import call_reranker_async

    with patch("services.gateway.repositories.reranker_client.httpx.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_client.post = AsyncMock(
            return_value=type("Resp", (), {"raise_for_status": lambda s: None, "json": lambda s: {"results": [1]}})()
        )
        result = await call_reranker_async("query", ["doc1"], top_n=1)
        assert "results" in result
