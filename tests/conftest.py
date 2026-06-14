import asyncio
import os
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import Base, engine, AsyncSessionLocal
from app.config import get_settings

os.environ["TESTING"] = "1"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    await engine.dispose()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session

@pytest.fixture
async def client():
    await engine.dispose()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await engine.dispose()

@pytest.fixture
def admin_token():
    # Will implement later or mock
    pass
