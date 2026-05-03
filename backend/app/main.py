import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-5s %(name)s :: %(message)s",
)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root():
    return {"app": settings.app_name, "status": "ok"}
