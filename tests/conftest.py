from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlmodel import SQLModel

from app.fraud import FraudDetector
from app.main import app
from app.routes import get_session
from app.short_code import Sha256ShortCodeGenerator

TEST_DATABASE_URL = "sqlite+aiosqlite://"


class AlwaysLegitFraudDetector(FraudDetector):
    """Fraud detector stub that always reports legitimate traffic."""

    async def detect(self) -> bool:
        return False


class AlwaysFraudDetector(FraudDetector):
    """Fraud detector stub that always reports fraud."""

    async def detect(self) -> bool:
        return True


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture()
async def db_engine():
    """Create and tear down a per-test async SQLite engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session_factory(db_engine) -> async_sessionmaker:
    """Provide the async session factory bound to the test engine."""
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest_asyncio.fixture()
async def db_session(db_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean async SQLite session per test."""
    async with db_session_factory() as session:
        yield session


@pytest_asyncio.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx AsyncClient wired to the FastAPI app with test overrides."""

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    app.state.short_code_generator = Sha256ShortCodeGenerator()
    app.state.fraud_detector = AlwaysLegitFraudDetector()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()
