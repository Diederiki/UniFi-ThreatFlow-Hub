from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import settings


class TokenError(Exception):
    pass


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    """JWT iat is float (seconds with µs) so token-revocation comparisons
    against `users.min_token_iat` don't suffer from same-second collisions."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now.timestamp(),  # float; PyJWT accepts NumericDate float per RFC 7519 § 2
        "exp": int((now + timedelta(minutes=settings.jwt_ttl_minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise TokenError(str(e)) from e
