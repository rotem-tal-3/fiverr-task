from sqlmodel import SQLModel


class HelloWorldCreate(SQLModel):
    text: str


class HelloWorldRead(SQLModel):
    id: int
    text: str
