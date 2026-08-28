from collections.abc import AsyncGenerator
from urllib.parse import urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import settings


def _ensure_async_driver(url: str) -> str:
    """Convert postgres:// or postgresql:// to postgresql+asyncpg:// so SQLAlchemy uses asyncpg."""
    parsed = urlparse(url)
    if parsed.scheme in ("postgres", "postgresql"):
        return urlunparse(parsed._replace(scheme="postgresql+asyncpg"))
    return url


engine = create_async_engine(
    _ensure_async_driver(settings.database_url),
    echo=False,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
