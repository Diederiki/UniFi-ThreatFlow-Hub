#!/usr/bin/env bash
# Generate .env from .env.example and fill auto-generated secrets.
# Idempotent: existing values in .env are preserved.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
    cp .env.example .env
    chmod 600 .env
    echo "[init] created .env from .env.example (mode 0600)"
fi

# Helper: set KEY=VAL in .env only if KEY is empty/missing
fill_if_empty() {
    local key="$1" val="$2"
    local current
    current="$(grep -E "^${key}=" .env | head -n1 | cut -d= -f2- || true)"
    # strip optional surrounding quotes
    current="${current%\"}"; current="${current#\"}"
    if [[ -z "${current}" ]]; then
        # use a delimiter unlikely to appear in random base64
        if grep -qE "^${key}=" .env; then
            sed -i.bak "s|^${key}=.*|${key}=${val}|" .env && rm -f .env.bak
        else
            printf '%s=%s\n' "${key}" "${val}" >> .env
        fi
        echo "[init] generated ${key}"
    else
        echo "[init] ${key} already set, leaving alone"
    fi
}

# 32-byte URL-safe random for session/JWT secrets
gen_secret() { python3 -c "import secrets; print(secrets.token_urlsafe(48))"; }

# 32-byte URL-safe base64 for Fernet (44 chars with padding)
gen_fernet() { python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null \
    || python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"; }

# Strong password (no shell-special chars)
gen_password() { python3 -c "import secrets, string; a=string.ascii_letters+string.digits; print(''.join(secrets.choice(a) for _ in range(40)))"; }

fill_if_empty SESSION_SECRET     "$(gen_secret)"
fill_if_empty JWT_SECRET         "$(gen_secret)"
fill_if_empty FERNET_KEY         "$(gen_fernet)"
fill_if_empty POSTGRES_PASSWORD  "$(gen_password)"
fill_if_empty CLICKHOUSE_PASSWORD "$(gen_password)"
fill_if_empty REDIS_PASSWORD     "$(gen_password)"

echo
echo "[init] .env is ready. Next steps:"
echo "       docker compose up -d --build"
echo "       ./scripts/run-migrations.sh"
echo "       ./scripts/create-admin.sh"
