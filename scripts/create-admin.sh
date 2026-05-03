#!/usr/bin/env bash
# Create the bootstrap admin user. If ADMIN_PASSWORD is empty, generate one
# and PRINT it to stdout exactly once. Safe to re-run — only inserts if missing.
set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
source .env

PWD_GENERATED=""
if [[ -z "${ADMIN_PASSWORD:-}" ]]; then
    PWD_GENERATED="$(python3 -c "import secrets, string; a=string.ascii_letters+string.digits; print(''.join(secrets.choice(a) for _ in range(20)))")"
    export ADMIN_PASSWORD="${PWD_GENERATED}"
fi

docker compose exec -T \
    -e ADMIN_EMAIL="${ADMIN_EMAIL}" \
    -e ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
    backend python -m app.cli.create_admin

if [[ -n "${PWD_GENERATED}" ]]; then
    echo
    echo "============================================================"
    echo "  Admin email:    ${ADMIN_EMAIL}"
    echo "  Admin password: ${PWD_GENERATED}"
    echo "  STORE THIS NOW — it will not be shown again."
    echo "============================================================"
fi
