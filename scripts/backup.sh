#!/usr/bin/env bash
# Full backup: Postgres dump + ClickHouse FREEZE → tar of shadow dir.
# ClickHouse FREEZE is hard-link-based so it's near-instant and consistent.
set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
source .env

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="backups/${STAMP}"
mkdir -p "${OUT}"

echo "[backup] postgres → ${OUT}/postgres.sql.gz"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "${OUT}/postgres.sql.gz"

echo "[backup] clickhouse FREEZE (snapshot to /var/lib/clickhouse/shadow/${STAMP})"
docker compose exec -T clickhouse clickhouse-client \
    -u "${CLICKHOUSE_USER}" --password "${CLICKHOUSE_PASSWORD}" -d "${CLICKHOUSE_DB}" \
    -q "ALTER TABLE raw_flow_events FREEZE WITH NAME '${STAMP}'" || true
docker compose exec -T clickhouse clickhouse-client \
    -u "${CLICKHOUSE_USER}" --password "${CLICKHOUSE_PASSWORD}" -d "${CLICKHOUSE_DB}" \
    -q "ALTER TABLE raw_threat_events FREEZE WITH NAME '${STAMP}'" || true
for tbl in rollup_1m rollup_5m rollup_15m rollup_1h rollup_1d; do
    docker compose exec -T clickhouse clickhouse-client \
        -u "${CLICKHOUSE_USER}" --password "${CLICKHOUSE_PASSWORD}" -d "${CLICKHOUSE_DB}" \
        -q "ALTER TABLE ${tbl} FREEZE WITH NAME '${STAMP}'" || true
done

echo "[backup] clickhouse → ${OUT}/clickhouse.tar.gz"
docker compose exec -T clickhouse sh -c \
    "cd /var/lib/clickhouse && tar czf - shadow/${STAMP}" > "${OUT}/clickhouse.tar.gz" || true

# Drop the shadow dir so we don't accumulate
docker compose exec -T clickhouse sh -c "rm -rf /var/lib/clickhouse/shadow/${STAMP}" || true

echo "[backup] env (redacted) → ${OUT}/env.txt"
grep -E '^(APP_|MOCK_|HOST_|COLLECTOR_|CH_|CORS_|ADMIN_EMAIL)=' .env > "${OUT}/env.txt" || true

echo "[backup] done → ${OUT}"
ls -lh "${OUT}/"
