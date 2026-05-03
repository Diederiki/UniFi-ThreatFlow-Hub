"""/api/settings GET/PUT — generic key/value app settings.

Per-key validators live in code (collector concurrency / polling / retention
all overridable). Stored in app_settings table (JSON value), audit-logged on PUT.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.config import settings as env_settings
from app.db.session import get_db
from app.models.app_setting import AppSetting
from app.models.user import User
from app.services.audit import log_action

router = APIRouter(prefix="/settings", tags=["settings"])

SETTINGS_KEY = "general"


class GeneralSettings(BaseModel):
    collector_max_concurrent: int = Field(default=10, ge=1, le=100)
    polling_interval_seconds_default: int = Field(default=30, ge=10, le=3600)
    timeframe_default: str = Field(default="24h")
    auto_refresh_seconds: int = Field(default=30, ge=5, le=600)


def _defaults() -> GeneralSettings:
    return GeneralSettings(
        collector_max_concurrent=env_settings.collector_max_concurrent,
        polling_interval_seconds_default=env_settings.collector_interval_seconds,
        timeframe_default="24h",
        auto_refresh_seconds=30,
    )


async def _load(db: AsyncSession) -> GeneralSettings:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == SETTINGS_KEY))).scalar_one_or_none()
    if not row:
        return _defaults()
    base = _defaults().model_dump()
    base.update(row.value or {})
    return GeneralSettings(**base)


@router.get("", response_model=GeneralSettings)
async def get_settings(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)) -> GeneralSettings:
    return await _load(db)


@router.put("", response_model=GeneralSettings)
async def put_settings(
    payload: GeneralSettings,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> GeneralSettings:
    existing = (await db.execute(select(AppSetting).where(AppSetting.key == SETTINGS_KEY))).scalar_one_or_none()
    if existing:
        existing.value = payload.model_dump()
    else:
        db.add(AppSetting(key=SETTINGS_KEY, value=payload.model_dump()))
    await log_action(db, actor=user, action="settings.update", entity_type="settings", metadata=payload.model_dump())
    await db.commit()
    return payload
