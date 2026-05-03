from fastapi import APIRouter
from sqlalchemy import text

from app.clickhouse import client as ch
from app.db.session import engine

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/deep")
async def health_deep() -> dict:
    """Verifies Postgres + ClickHouse reachable."""
    pg_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        pg_ok = True
    except Exception:  # noqa: BLE001
        pass

    ch_ok = await ch.ping()

    overall = "ok" if (pg_ok and ch_ok) else "degraded"
    return {"status": overall, "postgres": pg_ok, "clickhouse": ch_ok}
