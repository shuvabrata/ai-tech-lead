
import asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.settings import settings
from app.common.logger import logger

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,  # Verify connections before using them
    pool_recycle=3600,  # Recycle connections after 1 hour
    connect_args={
        "timeout": 10,
        "command_timeout": 10,
    },
)

ASYNC_SESSION_LOCAL = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Dependency for FastAPI (async version)
async def get_async_db():
    try:
        loop = asyncio.get_running_loop()
        logger.debug(f"[get_async_db] Running in loop={id(loop)}")
    except RuntimeError:
        logger.warning("[get_async_db] No running event loop detected")
    
    async with ASYNC_SESSION_LOCAL() as session:
        logger.debug(f"[get_async_db] Session created, yielding for use")
        yield session
