"""/api/users — admin user management."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.users import (
    PasswordReset,
    UserCreate,
    UserList,
    UserOut,
    UserUpdate,
)
from app.services import users as svc
from app.services.audit import log_action

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserList)
async def list_users(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> UserList:
    rows = await svc.list_users(db)
    return UserList(items=[UserOut.model_validate(u) for u in rows], total=len(rows))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
) -> UserOut:
    user = await svc.create(db, payload)
    await log_action(db, actor=actor, action="user.create", entity_type="user", entity_id=str(user.id),
                     metadata={"email": user.email, "role": user.role, "enabled": user.enabled})
    await db.commit()
    return UserOut.model_validate(user)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> UserOut:
    u = await svc.get(db, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user_not_found")
    return UserOut.model_validate(u)


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
) -> UserOut:
    u = await svc.get(db, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user_not_found")
    u = await svc.update(db, u, payload, actor=actor)
    await log_action(db, actor=actor, action="user.update", entity_type="user", entity_id=str(u.id),
                     metadata=payload.model_dump(exclude_none=True))
    await db.commit()
    return UserOut.model_validate(u)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
) -> Response:
    u = await svc.get(db, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user_not_found")
    email = u.email
    await svc.delete(db, u, actor=actor)
    await log_action(db, actor=actor, action="user.delete", entity_type="user", entity_id=str(user_id),
                     metadata={"email": email})
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: int,
    payload: PasswordReset,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
) -> Response:
    """Admin sets a new password for any user. Also bumps min_token_iat to
    invalidate that user's existing sessions everywhere."""
    u = await svc.get(db, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user_not_found")
    await svc.admin_set_password(db, u, payload.new_password)
    u.min_token_iat = datetime.now(timezone.utc) + timedelta(seconds=1)
    await db.commit()
    await log_action(db, actor=actor, action="user.password_reset", entity_type="user", entity_id=str(u.id),
                     metadata={"email": u.email})
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
