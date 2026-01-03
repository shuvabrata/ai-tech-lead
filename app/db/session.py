
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.settings import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

ASYNC_SESSION_LOCAL = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Dependency for FastAPI (async version)
async def get_async_db():
    async with ASYNC_SESSION_LOCAL() as session:
        yield session
