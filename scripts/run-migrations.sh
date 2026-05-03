#!/usr/bin/env bash
# Apply Postgres (Alembic) + ClickHouse (idempotent CREATE … IF NOT EXISTS) migrations.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[migrations] postgres (alembic) …"
docker compose exec -T backend alembic upgrade head

echo "[migrations] clickhouse (idempotent schema) …"
docker compose exec -T backend python -m app.cli.migrate_clickhouse

echo "[migrations] done"
