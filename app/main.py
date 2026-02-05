from fastapi import FastAPI
from app.lifespan import lifespan
from app.routes import router

app = FastAPI(title="Fiverr task server", lifespan=lifespan)

app.include_router(router)
