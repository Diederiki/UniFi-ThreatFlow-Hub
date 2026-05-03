"""Importing this package registers every model with SQLAlchemy's metadata.
Alembic env imports `register_all` so autogenerate sees them all.
"""
from app.models.user import Role, User  # noqa: F401
from app.models.app_setting import AppSetting  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401


def register_all() -> None:
    """No-op — importing this module already pulls every model in."""
