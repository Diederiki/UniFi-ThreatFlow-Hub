"""User service — admin CRUD + admin password reset + safety guards.

Safety:
  - Cannot delete yourself.
  - Cannot delete the last enabled admin.
  - Cannot demote the last enabled admin.
  - SSO-only users may not have a usable password (we still set a random one
    so the column constraint is satisfied; their `auth_method` is 'sso').
"""
from __future__ import annotations

import secrets

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password
from app.models.user import User
from app.schemas.users import UserCreate, UserUpdate


async def list_users(db: AsyncSession) -> list[User]:
    rows = (await db.execute(select(User).order_by(User.email))).scalars().all()
    return list(rows)


async def get(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    return (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()


async def get_by_sso_subject(db: AsyncSession, sub: str) -> User | None:
    return (await db.execute(select(User).where(User.sso_subject == sub))).scalar_one_or_none()


async def _enabled_admin_count(db: AsyncSession, *, exclude_id: int | None = None) -> int:
    stmt = select(func.count(User.id)).where(User.role == "admin", User.enabled.is_(True))
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return int((await db.execute(stmt)).scalar_one())


async def create(db: AsyncSession, payload: UserCreate, *, auth_method: str = "local", sso_subject: str | None = None) -> User:
    if await get_by_email(db, payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="email_already_exists")
    user = User(
        email=payload.email.lower(),
        name=payload.name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        enabled=payload.enabled,
        auth_method=auth_method,
        sso_subject=sso_subject,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update(db: AsyncSession, user: User, payload: UserUpdate, *, actor: User) -> User:
    # Guard: don't strip the last enabled admin
    if payload.role is not None and user.role == "admin" and payload.role != "admin":
        if await _enabled_admin_count(db, exclude_id=user.id) == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cannot_demote_last_admin")
    if payload.enabled is False and user.role == "admin":
        if await _enabled_admin_count(db, exclude_id=user.id) == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cannot_disable_last_admin")
    if payload.name is not None:
        user.name = payload.name
    if payload.role is not None:
        user.role = payload.role
    if payload.enabled is not None:
        user.enabled = payload.enabled
    await db.commit()
    await db.refresh(user)
    return user


async def delete(db: AsyncSession, user: User, *, actor: User) -> None:
    if user.id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cannot_delete_self")
    if user.role == "admin" and await _enabled_admin_count(db, exclude_id=user.id) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cannot_delete_last_admin")
    await db.delete(user)
    await db.commit()


async def admin_set_password(db: AsyncSession, user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    user.auth_method = "local"  # local password takes precedence over SSO once set
    await db.commit()


async def change_own_password(db: AsyncSession, user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    await db.commit()


def generate_random_password(length: int = 24) -> str:
    """Used when an admin creates an SSO-only user — column needs a value."""
    import string
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(chars) for _ in range(length))
