#!/usr/bin/env bash
# Restore from a backup directory.
#   - Postgres: drops + recreates the database, replays the dump.
#   - ClickHouse: extracts shadow tarball into /var/lib/clickhouse/shadow then
#     ATTACH PARTITION FROM the snapshot. (Manual review recommended for
#     production restores — see docs/RESTORE.md if you want this scripted.)
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <backup-dir>"
    exit 1
fi

# shellcheck disable=SC1091
source .env

DIR="$1"
[[ -d "${DIR}" ]] || { echo "no such dir: ${DIR}"; exit 1; }
[[ -f "${DIR}/postgres.sql.gz" ]] || { echo "missing postgres.sql.gz"; exit 1; }

echo "[restore] postgres ← ${DIR}/postgres.sql.gz"
gunzip -c "${DIR}/postgres.sql.gz" | docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

if [[ -f "${DIR}/clickhouse.tar.gz" ]]; then
    echo "[restore] clickhouse shadow ← ${DIR}/clickhouse.tar.gz"
    docker compose exec -T clickhouse sh -c "cd /var/lib/clickhouse && tar xzf -" < "${DIR}/clickhouse.tar.gz"
    echo "[restore] shadow extracted to /var/lib/clickhouse/shadow/."
    echo "[restore] manual step: ALTER TABLE <name> ATTACH PARTITION '<part>' FROM '<shadow path>'"
    echo "[restore] (per-table because partition keys differ; see docs/RESTORE.md)."
fi

echo "[restore] done"
