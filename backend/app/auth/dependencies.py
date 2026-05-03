from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_tokens import TokenError, decode_token
from app.db.session import get_db
from app.models.user import User

SESSION_COOKIE = "threatflow_session"


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        # Also accept Authorization: Bearer for API clients
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")

    try:
        payload = decode_token(token)
    except TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_token")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_token")

    user = (await db.execute(select(User).where(User.email == sub))).scalar_one_or_none()
    if user is None or not user.enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="user_disabled")

    # Token revocation: reject any JWT issued before user.min_token_iat.
    if user.min_token_iat is not None:
        iat = payload.get("iat")
        if iat is not None and int(iat) < int(user.min_token_iat.timestamp()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="token_revoked")
    return user


def require_role(*allowed: str):
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if allowed and user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="insufficient_role")
        return user

    return _dep
