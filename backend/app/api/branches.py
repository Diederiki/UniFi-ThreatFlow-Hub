from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.branch import (
    BranchCreate,
    BranchListOut,
    BranchOut,
    BranchUpdate,
    TestConnectionResult,
)
from app.services import branches as svc
from app.services import unifi_test
from app.services.audit import log_action

router = APIRouter(prefix="/branches", tags=["branches"])


@router.get("", response_model=BranchListOut)
async def list_branches(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    rows = await svc.list_branches(db)
    items = [svc.to_out(r) for r in rows]
    return BranchListOut(items=items, total=len(items))


@router.post("", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
async def create_branch(
    payload: BranchCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
):
    if await svc.get_branch_by_code(db, payload.branch_code):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="branch_code_already_exists")
    try:
        branch = await svc.create_branch(db, payload)
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="branch_code_already_exists")

    await log_action(
        db,
        actor=user,
        action="branch.create",
        entity_type="branch",
        entity_id=str(branch.id),
        metadata={"branch_code": branch.branch_code, "name": branch.name},
    )
    await db.commit()
    return svc.to_out(branch)


@router.get("/{branch_id}", response_model=BranchOut)
async def get_branch(
    branch_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    branch = await svc.get_branch(db, branch_id)
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="branch_not_found")
    return svc.to_out(branch)


@router.put("/{branch_id}", response_model=BranchOut)
async def update_branch(
    branch_id: UUID,
    payload: BranchUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
):
    branch = await svc.get_branch(db, branch_id)
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="branch_not_found")
    branch = await svc.update_branch(db, branch, payload)
    await log_action(
        db,
        actor=user,
        action="branch.update",
        entity_type="branch",
        entity_id=str(branch.id),
        metadata=payload.model_dump(exclude={"credentials"}, exclude_unset=True),
    )
    await db.commit()
    return svc.to_out(branch)


@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch(
    branch_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    branch = await svc.get_branch(db, branch_id)
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="branch_not_found")
    code = branch.branch_code
    await svc.delete_branch(db, branch)
    await log_action(
        db,
        actor=user,
        action="branch.delete",
        entity_type="branch",
        entity_id=str(branch_id),
        metadata={"branch_code": code},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{branch_id}/enable", response_model=BranchOut)
async def enable_branch(
    branch_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
):
    branch = await svc.get_branch(db, branch_id)
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="branch_not_found")
    branch = await svc.set_enabled(db, branch, True)
    await log_action(db, actor=user, action="branch.enable", entity_type="branch", entity_id=str(branch.id))
    await db.commit()
    return svc.to_out(branch)


@router.post("/{branch_id}/disable", response_model=BranchOut)
async def disable_branch(
    branch_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
):
    branch = await svc.get_branch(db, branch_id)
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="branch_not_found")
    branch = await svc.set_enabled(db, branch, False)
    await log_action(db, actor=user, action="branch.disable", entity_type="branch", entity_id=str(branch.id))
    await db.commit()
    return svc.to_out(branch)


@router.post("/{branch_id}/test-connection", response_model=TestConnectionResult)
async def test_connection(
    branch_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
):
    branch = await svc.get_branch(db, branch_id)
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="branch_not_found")
    result = await unifi_test.test_connection(branch)
    await log_action(
        db,
        actor=user,
        action="branch.test_connection",
        entity_type="branch",
        entity_id=str(branch.id),
        metadata={"ok": result.ok, "endpoint_used": result.endpoint_used, "is_mock": result.is_mock},
    )
    await db.commit()
    return result


@router.post("/{branch_id}/discover-sites", response_model=TestConnectionResult)
async def discover_sites(
    branch_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
):
    branch = await svc.get_branch(db, branch_id)
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="branch_not_found")
    result = await unifi_test.discover_sites(branch)
    await log_action(
        db,
        actor=user,
        action="branch.discover_sites",
        entity_type="branch",
        entity_id=str(branch.id),
        metadata={"ok": result.ok, "sites_discovered": result.sites_discovered},
    )
    await db.commit()
    return result
