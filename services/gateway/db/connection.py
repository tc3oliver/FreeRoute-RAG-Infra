"""
Tenant 資料庫連線管理 (SQLAlchemy ORM)
"""

import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base

# Database URL from environment
DATABASE_URL = os.getenv("TENANT_DB_URL", "postgresql://gateway:gateway123@localhost:9432/tenants").replace(
    "postgresql://", "postgresql+asyncpg://"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Initialize database (create tables if needed)."""
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connections."""
    await engine.dispose()


@asynccontextmanager
async def get_db_session():
    """Get async database session (context manager)."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Legacy compatibility functions
async def connect_tenant_db():
    """Initialize database on startup."""
    await init_db()


async def disconnect_tenant_db():
    """Close database on shutdown."""
    await close_db()
