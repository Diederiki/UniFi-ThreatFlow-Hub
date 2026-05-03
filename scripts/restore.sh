#!/usr/bin/env bash
# Restore from a backup directory. Phase 7 will harden this.
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

echo "[restore] done"
