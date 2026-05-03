from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _revoke_now() -> datetime:
    """Stamp the revocation cutoff at *now*. Because iat is float-seconds, any
    token issued at or before this instant is rejected, and a re-login that
    happens microseconds later gets a strictly-larger iat and passes."""
    return datetime.now(timezone.utc)

from app.auth.dependencies import SESSION_COOKIE, get_current_user
from app.auth.jwt_tokens import create_access_token
from app.auth.passwords import hash_password, verify_password
from app.config import settings
from app.db.session import get_db
from app.limiter import limiter
from app.models.user import User
from app.schemas.auth import CurrentUser, LoginRequest, LoginResponse
from app.schemas.users import ChangePassword, ProfileUpdate, UserOut
from app.services.audit import log_action

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.jwt_ttl_minutes * 60,
        httponly=True,
        # strict so cross-site form posts can't carry the cookie. The SSO redirect
        # uses its own short-lived state cookie (lax), so this doesn't break SSO.
        samesite="strict",
        secure=settings.is_production,
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == payload.email.lower()))).scalar_one_or_none()
    if user is None or not user.enabled or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    # Block password login for SSO-only users — admin-set passwords are the
    # only way to unlock; otherwise force the SSO flow.
    if user.auth_method == "sso":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="sso_required")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    token = create_access_token(subject=user.email, extra={"role": user.role, "via": "password"})
    _set_session_cookie(response, token)
    return LoginResponse(email=user.email, name=user.name, role=user.role)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.put("/me", response_model=UserOut)
async def update_me(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.name is not None:
        user.name = payload.name
    await db.commit()
    await db.refresh(user)
    await log_action(db, actor=user, action="auth.profile.update", entity_type="user",
                     entity_id=str(user.id), metadata=payload.model_dump(exclude_none=True))
    await db.commit()
    return UserOut.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePassword,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="current_password_incorrect")
    user.password_hash = hash_password(payload.new_password)
    user.min_token_iat = _revoke_now()  # invalidate every other session
    await db.commit()
    await log_action(db, actor=user, action="auth.change_password", entity_type="user",
                     entity_id=str(user.id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sign-out-everywhere", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out_everywhere(
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Bumps min_token_iat so every existing JWT for this user is rejected."""
    user.min_token_iat = _revoke_now()
    await db.commit()
    await log_action(db, actor=user, action="auth.sign_out_everywhere", entity_type="user",
                     entity_id=str(user.id))
    await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
