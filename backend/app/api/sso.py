"""/api/auth/sso/* — Microsoft Entra OIDC routes."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _set_session_cookie
from app.auth.dependencies import require_role
from app.auth.jwt_tokens import create_access_token
from app.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.sso import SsoConfig, SsoConfigUpdate, SsoInfo
from app.services import sso, users as users_svc
from app.services.audit import log_action
from app.services.users import generate_random_password

log = logging.getLogger("sso.api")
router = APIRouter(prefix="/auth/sso", tags=["sso"])


@router.get("/info", response_model=SsoInfo)
async def sso_info(db: AsyncSession = Depends(get_db)) -> SsoInfo:
    """Public-readable so the login page knows whether to show the SSO button."""
    cfg = await sso.load_config(db)
    return SsoInfo(enabled=cfg.enabled and bool(cfg.tenant_id and cfg.client_id and cfg.has_client_secret))


@router.get("/config", response_model=SsoConfig)
async def get_config(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> SsoConfig:
    return await sso.load_config(db)


@router.put("/config", response_model=SsoConfig)
async def put_config(
    payload: SsoConfigUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
) -> SsoConfig:
    cfg = await sso.save_config(db, payload)
    await log_action(db, actor=actor, action="sso.config.update", entity_type="settings",
                     metadata={"enabled": cfg.enabled, "tenant_id": cfg.tenant_id, "auto_provision": cfg.auto_provision})
    await db.commit()
    return cfg


@router.get("/start")
async def sso_start(db: AsyncSession = Depends(get_db)) -> Response:
    """Redirect the user agent to Microsoft for sign-in."""
    cfg = await sso.load_config(db)
    try:
        url, state_cookie = sso.begin(cfg)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"sso_not_ready:{e}")
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(
        sso.STATE_COOKIE, state_cookie,
        max_age=sso.STATE_TTL_SECONDS,
        httponly=True, secure=settings.is_production, samesite="lax", path="/",
    )
    return response


def _err_with_cookie_clear(status_code: int, detail: str) -> HTTPException:
    """Raise an HTTPException whose handler will also clear the SSO state cookie."""
    exc = HTTPException(status_code, detail=detail)
    exc.headers = {"Set-Cookie": f"{sso.STATE_COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"}
    return exc


@router.get("/callback")
async def sso_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    state_cookie = request.cookies.get(sso.STATE_COOKIE)
    if not state_cookie:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="missing_state_cookie")
    try:
        claims = await sso.complete(db, code=code, state_from_query=state, state_cookie_value=state_cookie)
    except ValueError as e:
        log.warning("sso callback failed: %s", e)
        # Clear the now-burnt state cookie even on failure so it can't be replayed.
        raise _err_with_cookie_clear(status.HTTP_401_UNAUTHORIZED, f"sso_failed:{e}")

    # Microsoft may put email in `email`, `preferred_username`, or `upn`
    email = (claims.get("email") or claims.get("preferred_username") or claims.get("upn") or "").lower().strip()
    sub = claims.get("sub")
    name = claims.get("name") or email
    if not email or not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="sso_missing_claims")

    # Stable match by `sub` first. Fall back to email ONLY when Microsoft says
    # the email is verified — otherwise an attacker controlling any tenant
    # could register an unverified `bob@amspecgroup.com` and take over a
    # local account.
    user = await users_svc.get_by_sso_subject(db, sub)
    if user is None:
        email_verified = bool(claims.get("email_verified", False)) or "verified_primary_email" in (claims.get("xms_edov") or [])
        if email_verified:
            user = await users_svc.get_by_email(db, email)

    cfg = await sso.load_config(db)
    if user is None:
        if not cfg.auto_provision:
            await log_action(db, actor=None, action="sso.login.rejected_no_provision",
                             metadata={"email": email})
            await db.commit()
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="user_not_provisioned")
        from app.schemas.users import UserCreate
        user = await users_svc.create(
            db,
            UserCreate(email=email, name=name, role=cfg.default_role, enabled=True,
                       password=generate_random_password()),
            auth_method="sso", sso_subject=sub,
        )
        await log_action(db, actor=user, action="user.create.via_sso", entity_type="user",
                         entity_id=str(user.id), metadata={"email": email, "role": cfg.default_role})

    if not user.enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="user_disabled")

    # Bind sub on first login if matched-by-email
    if not user.sso_subject:
        user.sso_subject = sub
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    await log_action(db, actor=user, action="auth.login.sso", entity_type="user",
                     entity_id=str(user.id), metadata={"email": email})
    await db.commit()

    # Issue our own session cookie + clear the SSO state cookie + redirect
    token = create_access_token(subject=user.email, extra={"role": user.role, "via": "sso"})
    response = RedirectResponse(url="/overview", status_code=302)
    _set_session_cookie(response, token)
    response.delete_cookie(sso.STATE_COOKIE, path="/")
    return response
