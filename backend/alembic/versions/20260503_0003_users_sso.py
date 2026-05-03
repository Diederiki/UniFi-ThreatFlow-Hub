"""users.min_token_iat (token revocation) + users.sso_subject (Entra OIDC mapping)

Revision ID: 20260503_0003
Revises: 20260503_0002
Create Date: 2026-05-03 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260503_0003"
down_revision = "20260503_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("min_token_iat", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("sso_subject", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("auth_method", sa.String(32), nullable=False, server_default="local"))
    op.create_index("ix_users_sso_subject", "users", ["sso_subject"], unique=True, postgresql_where=sa.text("sso_subject IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("ix_users_sso_subject", table_name="users")
    op.drop_column("users", "auth_method")
    op.drop_column("users", "sso_subject")
    op.drop_column("users", "min_token_iat")
