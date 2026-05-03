#!/usr/bin/env bash
# Quick post-deploy sanity sweep. Returns non-zero on the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."

# Pull POSTGRES_USER / REDIS_PASSWORD / etc. from .env so the inline auth checks below work
if [[ -f .env ]]; then
    set -a; source .env; set +a
fi

PASS=0; FAIL=0
ok()   { echo "  [OK]   $*"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $*"; FAIL=$((FAIL+1)); }

echo "Containers:"
for svc in postgres clickhouse redis backend collector frontend; do
    state="$(docker compose ps -q "$svc" | xargs -r docker inspect -f '{{.State.Status}}' 2>/dev/null || true)"
    if [[ "$state" == "running" ]]; then ok "$svc running"; else fail "$svc state=$state"; fi
done

echo "Endpoints:"
if curl -fsS http://127.0.0.1:18091/api/health >/dev/null 2>&1; then ok "backend /api/health"; else fail "backend /api/health"; fi
if curl -fsS http://127.0.0.1:18090/ >/dev/null 2>&1; then ok "frontend /"; else fail "frontend /"; fi

echo "Databases:"
if docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-threatflow}" >/dev/null 2>&1; then ok "postgres ready"; else fail "postgres not ready"; fi
if docker compose exec -T clickhouse wget -qO- http://127.0.0.1:8123/ping >/dev/null 2>&1; then ok "clickhouse ping"; else fail "clickhouse ping"; fi
if docker compose exec -T redis redis-cli -a "${REDIS_PASSWORD:-}" ping 2>/dev/null | grep -q PONG; then ok "redis pong"; else fail "redis pong"; fi

echo
echo "Result: ${PASS} OK / ${FAIL} FAIL"
[[ "${FAIL}" -eq 0 ]]
