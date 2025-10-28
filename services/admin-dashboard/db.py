"""
PostgreSQL/SQLAlchemy connection (moved to package root for imports)
"""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 參考 gateway 寫法，預設用 container name
DATABASE_URL = os.getenv("TENANT_DB_URL", "postgresql://gateway:gateway123@tenant_db:5432/tenants").replace(
    "postgresql://", "postgresql+asyncpg://"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
