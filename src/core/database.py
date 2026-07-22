"""
NACA AI Chatbot — Database Connection Manager

Async SQLAlchemy engine and session factory for Cloud SQL (PostgreSQL + PostGIS).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
import structlog

from src.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class DatabaseManager:
    """Manages the async database engine and session lifecycle."""

    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def connect(self):
        self.engine = create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            pool_pre_ping=True,
            echo=settings.is_development,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("database_connected", url=settings.database_url.split("@")[-1])

    async def disconnect(self):
        if self.engine:
            await self.engine.dispose()
            logger.info("database_disconnected")

    def get_session(self) -> AsyncSession:
        if not self.session_factory:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self.session_factory()


db_manager = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a database session per request."""
    session = db_manager.get_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
