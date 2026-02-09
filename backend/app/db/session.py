from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..core.config import settings

engine = create_async_engine(
    str(settings.analytics_db_dsn),
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
