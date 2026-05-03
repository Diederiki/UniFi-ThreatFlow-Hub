from fastapi import APIRouter

from app.api import auth, branches, collectors, health, storage

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(branches.router)
api_router.include_router(storage.router)
api_router.include_router(collectors.router)
