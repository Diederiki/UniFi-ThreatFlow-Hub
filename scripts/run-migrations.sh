#!/usr/bin/env bash
# Run Alembic migrations inside the backend container.
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose exec -T backend alembic upgrade head
echo "[migrations] alembic upgrade head — done"
