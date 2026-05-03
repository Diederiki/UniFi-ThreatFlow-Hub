"""Auto-pruner — keeps the database from growing unboundedly.

Safe operations only (always-on):
  - DELETE old PG audit_logs (default keep 90 days)
  - DELETE old PG collector_runs (default keep 14 days)
  - OPTIMIZE TABLE on CH rollups (background compaction)

Disk watchdog (escalates only if root disk > 85%):
  - Tightens CH raw TTLs by 25% (floor: 30 days)
  - Tightens CH rollup_1m TTL by 25% (floor: 60 days)
  Does NOT touch docker — the VPS is shared with other apps so we never
  shell out to `docker prune`. Use scripts/reclaim.sh manually for that.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clickhouse import client as ch
from app.db.session import SessionLocal

log = logging.getLogger("pruner")

AUDIT_LOG_RETENTION_DAYS = 90
COLLECTOR_RUNS_RETENTION_DAYS = 14
DISK_WATCHDOG_PERCENT = 85
ROLLUP_TABLES_TO_OPTIMIZE = ["rollup_1m", "rollup_5m", "rollup_15m", "rollup_1h", "rollup_1d"]
RAW_TABLES = ["raw_flow_events", "raw_threat_events"]


@dataclass
class PruneReport:
    started_at: datetime
    finished_at: datetime
    audit_logs_deleted: int
    collector_runs_deleted: int
    rollups_optimized: list[str]
    disk_percent: float
    disk_free_bytes: int
    watchdog_fired: bool
    actions_taken: list[str]
    errors: list[str]


_last_report: PruneReport | None = None
LAST_REPORT_KEY = "pruner_last_report"


def last_report() -> PruneReport | None:
    """Read the last report from the in-process cache. Multi-worker callers
    should prefer last_report_persisted() which round-trips through PG."""
    return _last_report


async def last_report_persisted() -> PruneReport | None:
    """Cross-worker access — reads the most recent report from app_settings."""
    from sqlalchemy import select
    from app.models.app_setting import AppSetting
    async with SessionLocal() as db:
        row = (await db.execute(select(AppSetting).where(AppSetting.key == LAST_REPORT_KEY))).scalar_one_or_none()
        if not row or not row.value:
            return None
        v = row.value
        return PruneReport(
            started_at=datetime.fromisoformat(v["started_at"]),
            finished_at=datetime.fromisoformat(v["finished_at"]),
            audit_logs_deleted=int(v.get("audit_logs_deleted", 0)),
            collector_runs_deleted=int(v.get("collector_runs_deleted", 0)),
            rollups_optimized=list(v.get("rollups_optimized", [])),
            disk_percent=float(v.get("disk_percent", 0)),
            disk_free_bytes=int(v.get("disk_free_bytes", 0)),
            watchdog_fired=bool(v.get("watchdog_fired", False)),
            actions_taken=list(v.get("actions_taken", [])),
            errors=list(v.get("errors", [])),
        )


async def _persist_report(report: PruneReport) -> None:
    """Upsert the latest report into app_settings so other workers see it."""
    from sqlalchemy import select
    from app.models.app_setting import AppSetting
    payload = {
        "started_at": report.started_at.isoformat(),
        "finished_at": report.finished_at.isoformat(),
        "audit_logs_deleted": report.audit_logs_deleted,
        "collector_runs_deleted": report.collector_runs_deleted,
        "rollups_optimized": report.rollups_optimized,
        "disk_percent": report.disk_percent,
        "disk_free_bytes": report.disk_free_bytes,
        "watchdog_fired": report.watchdog_fired,
        "actions_taken": report.actions_taken,
        "errors": report.errors,
    }
    async with SessionLocal() as db:
        existing = (await db.execute(select(AppSetting).where(AppSetting.key == LAST_REPORT_KEY))).scalar_one_or_none()
        if existing:
            existing.value = payload
        else:
            db.add(AppSetting(key=LAST_REPORT_KEY, value=payload))
        await db.commit()


async def _prune_pg(db: AsyncSession) -> tuple[int, int]:
    audit_sql = text(f"DELETE FROM audit_logs WHERE created_at < now() - INTERVAL '{AUDIT_LOG_RETENTION_DAYS} days'")
    runs_sql = text(f"DELETE FROM collector_runs WHERE started_at < now() - INTERVAL '{COLLECTOR_RUNS_RETENTION_DAYS} days'")
    audit_res = await db.execute(audit_sql)
    runs_res = await db.execute(runs_sql)
    await db.commit()
    return (audit_res.rowcount or 0, runs_res.rowcount or 0)


async def _optimize_ch_rollups() -> list[str]:
    optimized = []
    for tbl in ROLLUP_TABLES_TO_OPTIMIZE:
        try:
            await ch.execute(f"OPTIMIZE TABLE threatflow.{tbl} FINAL DEDUPLICATE")
            optimized.append(tbl)
        except Exception as e:  # noqa: BLE001
            log.warning("OPTIMIZE %s failed: %s", tbl, e)
    return optimized


async def _disk_watchdog() -> tuple[float, int, bool, list[str]]:
    """If disk usage exceeds DISK_WATCHDOG_PERCENT, tighten CH TTLs."""
    actions: list[str] = []
    try:
        usage = shutil.disk_usage("/")
        percent = (usage.used / usage.total) * 100 if usage.total else 0
        free = int(usage.free)
    except Exception:  # noqa: BLE001
        return 0, 0, False, []

    if percent < DISK_WATCHDOG_PERCENT:
        return percent, free, False, []

    log.warning("disk watchdog FIRED: %.1f%% used", percent)
    # Tighten raw TTLs to 75% of current, floor 30 days
    for tbl in RAW_TABLES:
        try:
            row = await ch.query_one(
                "SELECT create_table_query FROM system.tables WHERE database='threatflow' AND name={t:String}",
                {"t": tbl},
            )
            ddl = (row or {}).get("create_table_query") or ""
            import re
            m = re.search(r"toIntervalDay\((\d+)\)", ddl)
            if not m:
                continue
            cur = int(m.group(1))
            new = max(30, int(cur * 0.75))
            if new < cur:
                col = "event_time"
                await ch.execute(f"ALTER TABLE threatflow.{tbl} MODIFY TTL toDateTime({col}) + toIntervalDay({new}) DELETE")
                actions.append(f"{tbl} TTL {cur}→{new} days")
        except Exception as e:  # noqa: BLE001
            log.warning("watchdog ALTER %s failed: %s", tbl, e)

    return percent, free, True, actions


async def run_once() -> PruneReport:
    started = datetime.now(timezone.utc)
    errors: list[str] = []

    audit_n = runs_n = 0
    try:
        async with SessionLocal() as db:
            audit_n, runs_n = await _prune_pg(db)
    except Exception as e:  # noqa: BLE001
        errors.append(f"pg_prune: {e}")
        log.exception("pg prune failed")

    optimized: list[str] = []
    try:
        optimized = await _optimize_ch_rollups()
    except Exception as e:  # noqa: BLE001
        errors.append(f"ch_optimize: {e}")
        log.exception("ch optimize failed")

    disk_percent = 0.0
    disk_free = 0
    watchdog_fired = False
    watchdog_actions: list[str] = []
    try:
        disk_percent, disk_free, watchdog_fired, watchdog_actions = await _disk_watchdog()
    except Exception as e:  # noqa: BLE001
        errors.append(f"disk_watchdog: {e}")
        log.exception("disk watchdog failed")

    finished = datetime.now(timezone.utc)
    report = PruneReport(
        started_at=started, finished_at=finished,
        audit_logs_deleted=audit_n, collector_runs_deleted=runs_n,
        rollups_optimized=optimized,
        disk_percent=disk_percent, disk_free_bytes=disk_free,
        watchdog_fired=watchdog_fired,
        actions_taken=watchdog_actions,
        errors=errors,
    )
    global _last_report
    _last_report = report
    try:
        await _persist_report(report)
    except Exception as e:  # noqa: BLE001
        log.warning("could not persist pruner report: %s", e)
    log.info("pruner done: audit=%d runs=%d optimized=%d disk=%.1f%% watchdog=%s",
             audit_n, runs_n, len(optimized), disk_percent, watchdog_fired)
    return report


async def background_loop(interval_seconds: int = 3600) -> None:
    """Run forever — first sweep after 60s warmup, then every interval_seconds."""
    await asyncio.sleep(60)
    while True:
        try:
            await run_once()
        except Exception:  # noqa: BLE001
            log.exception("pruner sweep raised; continuing")
        await asyncio.sleep(interval_seconds)
