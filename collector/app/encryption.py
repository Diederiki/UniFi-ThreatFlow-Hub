"""Mirror of backend/app/utils/encryption.py — kept as a separate file because
the two services are independent Docker images. Both use FERNET_KEY from .env."""
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.fernet_key.encode() if isinstance(settings.fernet_key, str) else settings.fernet_key
    return Fernet(key)


def decrypt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
