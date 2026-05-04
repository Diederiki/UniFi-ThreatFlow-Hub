"""Env-driven config for the IPFIX collector."""
from __future__ import annotations

import os


def _e(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


class Settings:
    bind_host = _e("IPFIX_BIND_HOST", "0.0.0.0")
    bind_port = int(_e("IPFIX_BIND_PORT", "2055"))

    # Postgres for branch lookup. Re-uses the standard threatflow vars.
    pg_host = _e("POSTGRES_HOST", "postgres")
    pg_port = int(_e("POSTGRES_PORT", "5432"))
    pg_db   = _e("POSTGRES_DB", "threatflow")
    pg_user = _e("POSTGRES_USER", "threatflow")
    pg_pwd  = _e("POSTGRES_PASSWORD", "")

    # ClickHouse insert target.
    ch_host = _e("CLICKHOUSE_HOST", "clickhouse")
    ch_port = int(_e("CLICKHOUSE_HTTP_PORT", "8123"))
    ch_db   = _e("CLICKHOUSE_DB", "threatflow")
    ch_user = _e("CLICKHOUSE_USER", "default")
    ch_pwd  = _e("CLICKHOUSE_PASSWORD", "")

    # Batch tuning.
    batch_size = int(_e("IPFIX_BATCH_SIZE", "500"))
    flush_ms   = int(_e("IPFIX_FLUSH_INTERVAL_MS", "2000"))

    # How often to refresh the source-ip → branch lookup cache. Branches
    # don't change often so 5 min is plenty; first lookup misses warm it up.
    branch_lookup_refresh_seconds = int(_e("IPFIX_BRANCH_LOOKUP_REFRESH", "300"))


settings = Settings()
