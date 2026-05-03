"""branches + branch_credentials + collector_status + collector_runs

Revision ID: 20260503_0002
Revises: 20260503_0001
Create Date: 2026-05-03 17:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260503_0002"
down_revision = "20260503_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("branch_code", sa.String(64), nullable=False, unique=True),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("city", sa.String(128), nullable=True),
        sa.Column("tags", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("controller_url", sa.String(512), nullable=False),
        sa.Column("site_id", sa.String(128), nullable=False, server_default="default"),
        sa.Column("gateway_model", sa.String(64), nullable=True),
        sa.Column("auth_method", sa.String(32), nullable=False, server_default="local"),
        sa.Column("ssl_verify", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("polling_interval_seconds", sa.Integer, nullable=False, server_default="30"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_branches_branch_code", "branches", ["branch_code"], unique=True)
    op.create_index("ix_branches_enabled", "branches", ["enabled"])

    op.create_table(
        "branch_credentials",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("encrypted_username", sa.Text, nullable=True),
        sa.Column("encrypted_password", sa.Text, nullable=True),
        sa.Column("encrypted_api_key", sa.Text, nullable=True),
        sa.Column("encrypted_token", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "collector_status",
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_duration_ms", sa.Integer, nullable=True),
        sa.Column("last_event_count", sa.Integer, nullable=True),
        sa.Column("last_endpoint_used", sa.String(512), nullable=True),
        sa.Column("unifi_os_version", sa.String(64), nullable=True),
        sa.Column("network_app_version", sa.String(64), nullable=True),
        sa.Column("collector_version", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "collector_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("branch_id", UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("event_count", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("endpoint_used", sa.String(512), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
    )
    op.create_index("ix_collector_runs_branch_id", "collector_runs", ["branch_id"])
    op.create_index("ix_collector_runs_started_at", "collector_runs", ["started_at"])

    # gen_random_uuid() needs pgcrypto extension on Postgres < 13. PG 16 has it built-in via uuid-ossp or pgcrypto.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def downgrade() -> None:
    op.drop_index("ix_collector_runs_started_at", table_name="collector_runs")
    op.drop_index("ix_collector_runs_branch_id", table_name="collector_runs")
    op.drop_table("collector_runs")
    op.drop_table("collector_status")
    op.drop_table("branch_credentials")
    op.drop_index("ix_branches_enabled", table_name="branches")
    op.drop_index("ix_branches_branch_code", table_name="branches")
    op.drop_table("branches")
