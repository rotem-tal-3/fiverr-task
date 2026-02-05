from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db.session import engine
from sqlmodel import SQLModel

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Sets up the database pool and response provider in the app lifespan.
    """
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    await engine.dispose()
