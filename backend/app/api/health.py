from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import engine

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/deep")
async def health_deep() -> dict:
    """Verifies Postgres reachable. ClickHouse + Redis added in later phases."""
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        pass
    return {"status": "ok" if db_ok else "degraded", "postgres": db_ok}
