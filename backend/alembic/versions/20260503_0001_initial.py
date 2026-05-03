"""initial control-plane schema (Phase 1 subset)

Phase 2 will add branches, branch_credentials, collector_status, collector_runs.

Revision ID: 20260503_0001
Revises:
Create Date: 2026-05-03 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260503_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("permissions", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(64), nullable=False, server_default="admin"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("metadata_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # Seed canonical roles
    op.bulk_insert(
        sa.table(
            "roles",
            sa.column("name", sa.String),
            sa.column("permissions", sa.JSON),
        ),
        [
            {"name": "admin", "permissions": ["*"]},
            {"name": "operator", "permissions": ["read", "branch.test", "collector.run"]},
            {"name": "viewer", "permissions": ["read"]},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("app_settings")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_table("roles")
