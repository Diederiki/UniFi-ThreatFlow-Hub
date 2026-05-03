#!/usr/bin/env bash
# Phase 1 stub — a real backup pipeline lands in Phase 7.
# Currently dumps Postgres only; ClickHouse + retention added later.
set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
source .env

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="backups/${STAMP}"
mkdir -p "${OUT}"

echo "[backup] postgres → ${OUT}/postgres.sql.gz"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "${OUT}/postgres.sql.gz"

echo "[backup] (Phase 7 will add clickhouse + redis snapshots)"
echo "[backup] done → ${OUT}"
