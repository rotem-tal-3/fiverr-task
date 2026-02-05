from typing import Optional
from sqlmodel import SQLModel, Field


class HelloWorld(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    text: str = Field(index=True, unique=True)
