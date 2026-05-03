"""Postgres access for the collector — async SQLAlchemy core (no ORM models
imported; we use raw SQL against the same schema the backend defined)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.postgres_async_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    echo=False,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def list_enabled_branches() -> list[dict[str, Any]]:
    sql = text(
        """
        SELECT b.id, b.name, b.branch_code, b.controller_url, b.site_id, b.gateway_model,
               b.auth_method, b.ssl_verify, b.polling_interval_seconds,
               c.encrypted_username, c.encrypted_password, c.encrypted_api_key, c.encrypted_token
        FROM branches b
        LEFT JOIN branch_credentials c ON c.branch_id = b.id
        WHERE b.enabled = TRUE
        ORDER BY b.name
        """
    )
    async with SessionLocal() as db:
        rows = (await db.execute(sql)).mappings().all()
        return [dict(r) for r in rows]


async def open_run(branch_id: UUID) -> int:
    """Insert a `collector_runs` row in 'running' state and return its id."""
    sql = text(
        """
        INSERT INTO collector_runs (branch_id, started_at, status)
        VALUES (:bid, now(), 'running')
        RETURNING id
        """
    )
    async with SessionLocal() as db:
        result = await db.execute(sql, {"bid": str(branch_id)})
        run_id = result.scalar_one()
        await db.commit()
        return int(run_id)


async def close_run(
    *,
    run_id: int,
    branch_id: UUID,
    status: str,
    event_count: int,
    error_message: str | None,
    endpoint_used: str | None,
    duration_ms: int,
    unifi_os_version: str | None = None,
    network_app_version: str | None = None,
    collector_version: str | None = None,
) -> None:
    """Close the run row and upsert collector_status."""
    finish_sql = text(
        """
        UPDATE collector_runs
        SET finished_at = now(), status = :status, event_count = :ec,
            error_message = :err, endpoint_used = :ep, duration_ms = :dur
        WHERE id = :rid
        """
    )
    upsert_sql = text(
        """
        INSERT INTO collector_status (
            branch_id, status, last_success_at, last_error_at, last_error,
            last_duration_ms, last_event_count, last_endpoint_used,
            unifi_os_version, network_app_version, collector_version, updated_at
        ) VALUES (
            :bid, :status, :ok_at, :err_at, :err, :dur, :ec, :ep, :osv, :napp, :cv, now()
        )
        ON CONFLICT (branch_id) DO UPDATE SET
            status = EXCLUDED.status,
            last_success_at = COALESCE(EXCLUDED.last_success_at, collector_status.last_success_at),
            last_error_at   = COALESCE(EXCLUDED.last_error_at,   collector_status.last_error_at),
            last_error      = EXCLUDED.last_error,
            last_duration_ms = EXCLUDED.last_duration_ms,
            last_event_count = EXCLUDED.last_event_count,
            last_endpoint_used = COALESCE(EXCLUDED.last_endpoint_used, collector_status.last_endpoint_used),
            unifi_os_version = COALESCE(EXCLUDED.unifi_os_version, collector_status.unifi_os_version),
            network_app_version = COALESCE(EXCLUDED.network_app_version, collector_status.network_app_version),
            collector_version = COALESCE(EXCLUDED.collector_version, collector_status.collector_version),
            updated_at = now()
        """
    )
    now_ts = datetime.now(timezone.utc)
    ok_at = now_ts if status == "ok" else None
    err_at = now_ts if status == "error" else None
    async with SessionLocal() as db:
        await db.execute(
            finish_sql,
            {"rid": run_id, "status": status, "ec": event_count, "err": error_message, "ep": endpoint_used, "dur": duration_ms},
        )
        await db.execute(
            upsert_sql,
            {
                "bid": str(branch_id), "status": status,
                "ok_at": ok_at, "err_at": err_at,
                "err": error_message, "dur": duration_ms, "ec": event_count, "ep": endpoint_used,
                "osv": unifi_os_version, "napp": network_app_version, "cv": collector_version,
            },
        )
        await db.commit()
