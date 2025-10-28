"""
Admin Dashboard FastAPI 入口

此服務主要作為管理後台 API，對外提供 /admin/* 路由給前端呼叫，內部透過 `utils.gateway_client` 與 gateway 溝通。
"""

from contextlib import asynccontextmanager

# Use lifespan for startup/shutdown instead of deprecated on_event
from os import getenv
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import apikeys, graphdb, rag, tenants


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler: initialize DB schema and other resources on startup,
    and clean up on shutdown.

    We avoid using gateway here — admin-dashboard talks directly to DB/Qdrant/Neo4j.
    """
    # Initialize DB schema (use gateway models' Base so we share the same ORM metadata)
    try:
        from gateway.db.models import Base

        from .db import engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        # Log but don't fail startup; in many deployments DB is pre-initialized
        print("Warning: failed to initialize DB schema in admin-dashboard:", e)

    yield

    # Shutdown: dispose engine
    try:
        from .db import engine as _engine

        await _engine.dispose()
    except Exception:
        pass


app = FastAPI(title="FreeRoute-RAG Admin Dashboard", lifespan=lifespan)

# CORS: 允許前端 (可根據部署限制來源)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[getenv("ADMIN_UI_ORIGIN", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"ok": True}


# Register routers under /admin
app.include_router(tenants.router, prefix="/admin/tenants", tags=["tenants"])
app.include_router(apikeys.router, prefix="/admin/apikeys", tags=["apikeys"])
app.include_router(rag.router, prefix="", tags=["rag"])
app.include_router(graphdb.router, prefix="", tags=["graphdb"])

# Serve a minimal admin UI (vanilla SPA) if frontend files exist
try:
    frontend_dir = Path(__file__).resolve().parent / "frontend"
    if frontend_dir.exists():
        app.mount("/admin/ui", StaticFiles(directory=str(frontend_dir), html=True), name="admin_ui")
except Exception as _:
    # don't fail startup if static serving can't be configured
    pass


# Note: we intentionally do not rely on GATEWAY_URL in admin-dashboard; it operates directly on DB/Qdrant/Neo4j
