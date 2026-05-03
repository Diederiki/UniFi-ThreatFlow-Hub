from fastapi import APIRouter

from app.api import auth, health

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
