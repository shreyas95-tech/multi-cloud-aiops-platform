"""Database configuration and session management.

Uses SQLite for local development (no external services required).
Switch DATABASE_URL to postgresql+asyncpg://... for production.
"""

import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Default to SQLite for local development
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./email_reports.db",
)

# SQLite needs special handling
_is_sqlite = DATABASE_URL.startswith("sqlite")

engine_kwargs = {
    "echo": os.environ.get("DATABASE_ECHO", "false").lower() == "true",
}

if _is_sqlite:
    # SQLite doesn't support pool_size/max_overflow
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 20
    engine_kwargs["max_overflow"] = 10

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


async def init_db():
    """Create all tables (for SQLite local dev). Call on app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """Dependency that yields an async database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
