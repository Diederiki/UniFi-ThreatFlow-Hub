"""/api/collectors — read-side surface for the Collector Health page."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.db.session import get_db
from app.models.branch import Branch, CollectorRun, CollectorStatus
from app.models.user import User
from app.schemas.collector import (
    CollectorBranchStatus,
    CollectorRunOut,
    CollectorRunsList,
    CollectorStatusList,
)

router = APIRouter(prefix="/collectors", tags=["collectors"])


@router.get("/status", response_model=CollectorStatusList)
async def collector_status(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(Branch, CollectorStatus)
            .outerjoin(CollectorStatus, CollectorStatus.branch_id == Branch.id)
            .order_by(Branch.name)
        )
    ).all()
    items: list[CollectorBranchStatus] = []
    for branch, st in rows:
        items.append(
            CollectorBranchStatus(
                branch_id=branch.id,
                branch_name=branch.name,
                branch_code=branch.branch_code,
                enabled=branch.enabled,
                status=st.status if st else "unknown",
                last_success_at=st.last_success_at if st else None,
                last_error_at=st.last_error_at if st else None,
                last_error=st.last_error if st else None,
                last_duration_ms=st.last_duration_ms if st else None,
                last_event_count=st.last_event_count if st else None,
                last_endpoint_used=st.last_endpoint_used if st else None,
                unifi_os_version=st.unifi_os_version if st else None,
                network_app_version=st.network_app_version if st else None,
                collector_version=st.collector_version if st else None,
                updated_at=st.updated_at if st else None,
            )
        )
    return CollectorStatusList(items=items, total=len(items))


@router.get("/runs", response_model=CollectorRunsList)
async def collector_runs(
    branch_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = select(CollectorRun).order_by(desc(CollectorRun.started_at)).limit(limit)
    if branch_id:
        stmt = stmt.where(CollectorRun.branch_id == branch_id)
    rows = (await db.execute(stmt)).scalars().all()
    return CollectorRunsList(items=[CollectorRunOut.model_validate(r) for r in rows])


@router.post("/run-branch/{branch_id}", status_code=status.HTTP_202_ACCEPTED)
async def run_branch(
    branch_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
):
    """Manual-run hook. Phase 4 just acknowledges — the scheduler picks up
    on its next 30s tick (mock collectors run every tick anyway). Phase 4.x
    can wire a Redis pub/sub kick that the scheduler watches."""
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="branch_not_found")
    return {"queued": True, "branch_id": str(branch_id)}


@router.post("/run-all", status_code=status.HTTP_202_ACCEPTED)
async def run_all(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
):
    """Acknowledge a 'kick all enabled branches' request. The scheduler is
    already polling every 30s; this endpoint exists for the blueprint surface
    and as a future Redis-pubsub trigger point."""
    enabled = (await db.execute(select(Branch).where(Branch.enabled.is_(True)))).scalars().all()
    return {"queued": True, "branches_queued": [str(b.id) for b in enabled], "count": len(enabled)}
