"""/api/operations — pruner control + reclaim estimates."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.clickhouse import client as ch
from app.db.session import get_db
from app.models.user import User
from app.schemas.operations import PruneReportOut, ReclaimEstimate
from app.services import pruner
from app.services.audit import log_action

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/last-prune", response_model=PruneReportOut | None)
async def last_prune(_user: User = Depends(get_current_user)) -> PruneReportOut | None:
    r = await pruner.last_report_persisted()
    return None if r is None else PruneReportOut(**r.__dict__)


@router.post("/prune", response_model=PruneReportOut)
async def run_prune(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> PruneReportOut:
    report = await pruner.run_once()
    await log_action(
        db, actor=user, action="operations.prune",
        metadata={
            "audit_logs_deleted": report.audit_logs_deleted,
            "collector_runs_deleted": report.collector_runs_deleted,
            "rollups_optimized": len(report.rollups_optimized),
            "watchdog_fired": report.watchdog_fired,
        },
    )
    await db.commit()
    return PruneReportOut(**report.__dict__)


@router.get("/reclaim-estimate", response_model=ReclaimEstimate)
async def reclaim_estimate(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ReclaimEstimate:
    audit_n = (await db.execute(text(
        f"SELECT count(*) FROM audit_logs WHERE created_at < now() - INTERVAL '{pruner.AUDIT_LOG_RETENTION_DAYS} days'"
    ))).scalar_one()
    runs_n = (await db.execute(text(
        f"SELECT count(*) FROM collector_runs WHERE started_at < now() - INTERVAL '{pruner.COLLECTOR_RUNS_RETENTION_DAYS} days'"
    ))).scalar_one()
    failed = await ch.query_one("SELECT count() AS c FROM threatflow.failed_inserts")
    return ReclaimEstimate(
        audit_logs_rows_to_delete=int(audit_n or 0),
        collector_runs_rows_to_delete=int(runs_n or 0),
        failed_inserts_rows=int((failed or {}).get("c", 0)),
        docker_hint=(
            "Docker reclaim is intentionally NOT auto-run on this shared VPS. "
            "On the host: run `bash scripts/reclaim.sh` (only touches threatflow-*) "
            "or `docker builder prune --filter unused-for=24h` to reclaim build cache."
        ),
    )
