"""Branch persistence + credential encryption helpers.

The plaintext credentials submitted by the client are encrypted via Fernet
before they ever touch the database. The frontend only sees a `credentials_meta`
flag set per field indicating presence (never the value).
"""
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch, BranchCredential, CollectorStatus
from app.schemas.branch import (
    BranchCreate,
    BranchCredentialsIn,
    BranchCredentialsMeta,
    BranchOut,
    BranchUpdate,
    CollectorStatusOut,
)
from app.utils.encryption import encrypt


def _credentials_meta(c: BranchCredential | None) -> BranchCredentialsMeta:
    if c is None:
        return BranchCredentialsMeta()
    return BranchCredentialsMeta(
        has_username=bool(c.encrypted_username),
        has_password=bool(c.encrypted_password),
        has_api_key=bool(c.encrypted_api_key),
        has_token=bool(c.encrypted_token),
    )


def to_out(branch: Branch) -> BranchOut:
    return BranchOut(
        id=branch.id,
        name=branch.name,
        branch_code=branch.branch_code,
        country=branch.country,
        city=branch.city,
        tags=list(branch.tags or []),
        controller_url=branch.controller_url,
        site_id=branch.site_id,
        gateway_model=branch.gateway_model,
        auth_method=branch.auth_method,
        ssl_verify=branch.ssl_verify,
        polling_interval_seconds=branch.polling_interval_seconds,
        enabled=branch.enabled,
        notes=branch.notes,
        created_at=branch.created_at,
        updated_at=branch.updated_at,
        credentials_meta=_credentials_meta(branch.credentials),
        status=CollectorStatusOut.model_validate(branch.status) if branch.status else None,
    )


def _apply_credential_updates(creds_row: BranchCredential, payload: BranchCredentialsIn) -> bool:
    """Returns True if any credential field was actually changed.
    Empty string explicitly clears the value; None leaves it untouched."""
    changed = False
    mapping: dict[str, str] = {
        "username": "encrypted_username",
        "password": "encrypted_password",
        "api_key": "encrypted_api_key",
        "token": "encrypted_token",
    }
    for plaintext_attr, encrypted_attr in mapping.items():
        v = getattr(payload, plaintext_attr)
        if v is None:
            continue
        if v == "":
            if getattr(creds_row, encrypted_attr) is not None:
                setattr(creds_row, encrypted_attr, None)
                changed = True
        else:
            setattr(creds_row, encrypted_attr, encrypt(v))
            changed = True
    return changed


async def list_branches(db: AsyncSession) -> list[Branch]:
    rows = (await db.execute(select(Branch).order_by(Branch.name))).scalars().all()
    return list(rows)


async def get_branch(db: AsyncSession, branch_id: UUID) -> Branch | None:
    return (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()


async def get_branch_by_code(db: AsyncSession, code: str) -> Branch | None:
    return (await db.execute(select(Branch).where(Branch.branch_code == code))).scalar_one_or_none()


async def create_branch(db: AsyncSession, payload: BranchCreate) -> Branch:
    branch = Branch(
        name=payload.name,
        branch_code=payload.branch_code,
        country=payload.country,
        city=payload.city,
        tags=list(payload.tags),
        controller_url=payload.controller_url,
        site_id=payload.site_id,
        gateway_model=payload.gateway_model,
        auth_method=payload.auth_method,
        ssl_verify=payload.ssl_verify,
        polling_interval_seconds=payload.polling_interval_seconds,
        enabled=payload.enabled,
        notes=payload.notes,
    )
    db.add(branch)
    await db.flush()  # assign id

    creds = BranchCredential(branch_id=branch.id)
    _apply_credential_updates(creds, payload.credentials)
    db.add(creds)

    db.add(CollectorStatus(branch_id=branch.id, status="never_run"))

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(branch)
    return branch


async def update_branch(db: AsyncSession, branch: Branch, payload: BranchUpdate) -> Branch:
    data: dict[str, Any] = payload.model_dump(exclude={"credentials"}, exclude_unset=True)
    for field, value in data.items():
        if field == "tags" and value is not None:
            setattr(branch, field, list(value))
        else:
            setattr(branch, field, value)

    if payload.credentials is not None:
        if branch.credentials is None:
            branch.credentials = BranchCredential(branch_id=branch.id)
        _apply_credential_updates(branch.credentials, payload.credentials)

    await db.commit()
    await db.refresh(branch)
    return branch


async def delete_branch(db: AsyncSession, branch: Branch) -> None:
    await db.delete(branch)
    await db.commit()


async def set_enabled(db: AsyncSession, branch: Branch, enabled: bool) -> Branch:
    branch.enabled = enabled
    await db.commit()
    await db.refresh(branch)
    return branch
