from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import SQLModel

from app.db.session import engine
from app.fraud import RandomFraudDetector
from app.short_code import Sha256ShortCodeGenerator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize application resources and tear them down on shutdown.

    Sets up the database schema, attaches service dependencies to
    ``app.state``, and disposes of the engine on exit.
    """
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    app.state.short_code_generator = Sha256ShortCodeGenerator()
    app.state.fraud_detector = RandomFraudDetector()
    yield
    await engine.dispose()
