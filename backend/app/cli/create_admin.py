"""Idempotently create the bootstrap admin user.

Reads ADMIN_EMAIL and ADMIN_PASSWORD from env. Run from inside the backend
container: `python -m app.cli.create_admin`.
"""
import asyncio
import os
import sys

from sqlalchemy import select

from app.auth.passwords import hash_password
from app.db.session import SessionLocal
from app.models.user import User


async def main() -> int:
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not email or not password:
        print("ADMIN_EMAIL and ADMIN_PASSWORD must be set in env", file=sys.stderr)
        return 2

    async with SessionLocal() as db:
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing is not None:
            existing.password_hash = hash_password(password)
            existing.enabled = True
            existing.role = existing.role or "admin"
            await db.commit()
            print(f"[create-admin] reset password for existing user {email}")
            return 0
        user = User(
            email=email,
            name="Admin",
            password_hash=hash_password(password),
            role="admin",
            enabled=True,
        )
        db.add(user)
        await db.commit()
        print(f"[create-admin] created {email} (role=admin)")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
