from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.models import HelloWorld
from app.db.session import SessionLocal
from .schemas import HelloWorldRead, HelloWorldCreate

router = APIRouter()


async def get_session() -> AsyncGenerator[Any, Any]:
    async with SessionLocal() as session:
        yield session


@router.post("/hello", response_model=HelloWorldRead)
async def create_hello(hello_create: HelloWorldCreate,
                       session: AsyncSession = Depends(get_session), ):
    db_user = HelloWorld(**hello_create.model_dump())
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


@router.get("/hello", response_model=list[HelloWorldRead])
async def list_hello(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(HelloWorld))
    return result.scalars().all()


@router.delete("/hello/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(content_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(HelloWorld).where(HelloWorld.id == content_id))
    content = result.scalar_one_or_none()

    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="User not found")

    await session.delete(content)
    await session.commit()
