"""Microsoft Entra (Azure AD) OIDC integration.

Authorization Code flow with PKCE. Config (tenant_id / client_id /
client_secret / redirect_uri / auto_provision / default_role) lives in the
`app_settings` row keyed `sso_config`. The client_secret is encrypted at rest
with the same Fernet key as branch credentials.

Flow:
  1. /api/auth/sso/start
       - Generate state, nonce, code_verifier (PKCE)
       - Store them in a short-lived signed cookie (itsdangerous)
       - 302 to https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize
  2. Microsoft authenticates the user and redirects back to
     /api/auth/sso/callback?code=&state=
  3. Callback verifies state cookie, exchanges code+verifier for tokens at
     /oauth2/v2.0/token (confidential client + client_secret), then verifies
     id_token signature against the tenant's JWKS, validates iss / aud / nonce
     / exp, extracts email + name + sub.
  4. Find-or-create user (email match first, then sub). Issue a local
     threatflow_session JWT cookie. Redirect to /overview.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.app_setting import AppSetting
from app.schemas.sso import SsoConfig, SsoConfigUpdate
from app.utils.encryption import decrypt, encrypt

log = logging.getLogger("sso")

CONFIG_KEY = "sso_config"
STATE_COOKIE = "threatflow_sso_state"
STATE_TTL_SECONDS = 600  # 10 minutes


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="sso-state-v1")


def _new_pkce_pair() -> tuple[str, str]:
    """(code_verifier, code_challenge) per RFC 7636 § 4.1-4.2 (S256)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


async def load_config(db: AsyncSession) -> SsoConfig:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == CONFIG_KEY))).scalar_one_or_none()
    if not row or not row.value:
        return SsoConfig()
    v = row.value
    return SsoConfig(
        enabled=bool(v.get("enabled", False)),
        tenant_id=str(v.get("tenant_id", "")),
        client_id=str(v.get("client_id", "")),
        redirect_uri=str(v.get("redirect_uri", "")),
        auto_provision=bool(v.get("auto_provision", True)),
        default_role=v.get("default_role", "viewer"),
        has_client_secret=bool(v.get("encrypted_client_secret")),
    )


async def _load_raw(db: AsyncSession) -> dict[str, Any]:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == CONFIG_KEY))).scalar_one_or_none()
    return dict(row.value) if (row and row.value) else {}


async def save_config(db: AsyncSession, payload: SsoConfigUpdate) -> SsoConfig:
    existing = await _load_raw(db)
    new: dict[str, Any] = {
        "enabled": payload.enabled,
        "tenant_id": payload.tenant_id.strip(),
        "client_id": payload.client_id.strip(),
        "redirect_uri": payload.redirect_uri.strip(),
        "auto_provision": payload.auto_provision,
        "default_role": payload.default_role,
    }
    # Empty client_secret means "keep existing"
    if payload.client_secret:
        new["encrypted_client_secret"] = encrypt(payload.client_secret)
    elif "encrypted_client_secret" in existing:
        new["encrypted_client_secret"] = existing["encrypted_client_secret"]

    row = (await db.execute(select(AppSetting).where(AppSetting.key == CONFIG_KEY))).scalar_one_or_none()
    if row:
        row.value = new
    else:
        db.add(AppSetting(key=CONFIG_KEY, value=new))
    await db.commit()
    return await load_config(db)


async def _client_secret(db: AsyncSession) -> str | None:
    raw = await _load_raw(db)
    return decrypt(raw.get("encrypted_client_secret"))


def _authorize_url(*, tenant_id: str, client_id: str, redirect_uri: str, state: str, nonce: str, code_challenge: str) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?{urlencode(params)}"


def begin(cfg: SsoConfig) -> tuple[str, str]:
    """Returns (authorize_url, state_cookie_value)."""
    if not cfg.enabled or not cfg.tenant_id or not cfg.client_id or not cfg.redirect_uri:
        raise ValueError("SSO not fully configured")
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = _new_pkce_pair()
    cookie = _serializer().dumps({"state": state, "nonce": nonce, "verifier": verifier})
    url = _authorize_url(
        tenant_id=cfg.tenant_id, client_id=cfg.client_id, redirect_uri=cfg.redirect_uri,
        state=state, nonce=nonce, code_challenge=challenge,
    )
    return url, cookie


def _decode_state_cookie(value: str) -> dict[str, str]:
    try:
        return _serializer().loads(value, max_age=STATE_TTL_SECONDS)
    except BadSignature as e:
        raise ValueError(f"invalid sso state cookie: {e}") from e


async def complete(db: AsyncSession, *, code: str, state_from_query: str, state_cookie_value: str) -> dict[str, Any]:
    """Exchange code for tokens, verify id_token, return validated claims."""
    cfg = await load_config(db)
    if not cfg.enabled:
        raise ValueError("SSO disabled")
    cookie = _decode_state_cookie(state_cookie_value)
    if cookie.get("state") != state_from_query:
        raise ValueError("state mismatch")
    secret = await _client_secret(db)
    if not secret:
        raise ValueError("client_secret missing")

    token_url = f"https://login.microsoftonline.com/{cfg.tenant_id}/oauth2/v2.0/token"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": cfg.client_id,
                "client_secret": secret,
                "code": code,
                "redirect_uri": cfg.redirect_uri,
                "code_verifier": cookie["verifier"],
            },
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            log.warning("entra token exchange failed: %s %s", r.status_code, r.text[:300])
            raise ValueError("token_exchange_failed")
        tokens = r.json()
        id_token = tokens.get("id_token")
        if not id_token:
            raise ValueError("no_id_token")

        jwks_url = f"https://login.microsoftonline.com/{cfg.tenant_id}/discovery/v2.0/keys"
        jwk_client = jwt.PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=3600)
        signing_key = jwk_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token, signing_key.key,
            algorithms=["RS256"],
            audience=cfg.client_id,
            issuer=f"https://login.microsoftonline.com/{cfg.tenant_id}/v2.0",
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
        if claims.get("nonce") != cookie.get("nonce"):
            raise ValueError("nonce_mismatch")
    return claims
