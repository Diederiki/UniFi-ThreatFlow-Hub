"""Shared pytest fixtures.

These tests run in-process against a sqlite-backed Alembic-free schema for
the unit-level checks. End-to-end / API tests (test_api.py) are skipped if
PostgreSQL isn't reachable — they're run in CI / on the VPS where it is.
"""
import os

import pytest

# Provide the secrets that pydantic-settings requires before importing anything else
os.environ.setdefault("SESSION_SECRET", "test-session-secret-for-pytest-only")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-pytest-only")
# 32 zero bytes base64-encoded — valid Fernet key
os.environ.setdefault("FERNET_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("APP_ENV", "test")


@pytest.fixture
def fernet_key() -> str:
    return os.environ["FERNET_KEY"]
