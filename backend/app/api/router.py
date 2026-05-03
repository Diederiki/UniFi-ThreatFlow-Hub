from fastapi import APIRouter

from app.api import (
    auth, branches, clients, collectors, dashboard, events, health,
    observability, operations, storage, suspicion, top,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(branches.router)
api_router.include_router(storage.router)
api_router.include_router(collectors.router)
api_router.include_router(dashboard.router)
api_router.include_router(events.router)
api_router.include_router(top.router)
api_router.include_router(clients.router)
api_router.include_router(suspicion.router)
api_router.include_router(observability.router)
api_router.include_router(operations.router)
