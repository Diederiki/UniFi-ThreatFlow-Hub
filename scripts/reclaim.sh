#!/usr/bin/env bash
# Reclaim disk on the HOST.
# Safe-by-default — never touches images / containers / volumes that don't
# belong to the threatflow stack. The VPS is shared with other apps so we
# explicitly filter.
#
# Usage:  ./scripts/reclaim.sh           # report only
#         ./scripts/reclaim.sh --apply   # actually delete
set -euo pipefail
cd "$(dirname "$0")/.."

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

say() { echo "[reclaim] $*"; }

say "system disk usage:"
df -h / | tail -1

say ""
say "docker disk usage (informational):"
docker system df 2>&1 | tail -10 || true

# 1) Build cache older than 24h — safe; just slows next build
say ""
say "build cache older than 24h:"
docker builder du --filter type=exec.cachemount 2>/dev/null | tail -3 || true
if [[ "$APPLY" == "1" ]]; then
    docker builder prune --filter unused-for=24h --force 2>&1 | tail -5 || true
else
    say "  (would: docker builder prune --filter unused-for=24h --force)"
fi

# 2) Dangling images (no tag, no container) — safe
say ""
say "dangling images:"
docker images --filter dangling=true --format '{{.ID}} {{.Size}}' | head -10 || true
if [[ "$APPLY" == "1" ]]; then
    docker image prune --force 2>&1 | tail -3 || true
else
    say "  (would: docker image prune --force)"
fi

# 3) Stopped containers belonging to threatflow only — safe (we know we own them)
say ""
say "stopped threatflow containers:"
docker ps -a --filter status=exited --filter label=com.docker.compose.project=threatflow --format '{{.Names}}' || true
if [[ "$APPLY" == "1" ]]; then
    docker ps -aq --filter status=exited --filter label=com.docker.compose.project=threatflow \
        | xargs -r docker rm 2>&1 | tail -3 || true
else
    say "  (would: docker rm \$(docker ps -aq --filter status=exited --filter label=com.docker.compose.project=threatflow))"
fi

# 4) Unused threatflow volumes — DANGEROUS but filtered to our project
say ""
say "unused threatflow volumes (would only delete ours):"
docker volume ls --filter dangling=true --filter label=com.docker.compose.project=threatflow --format '{{.Name}}' || true
if [[ "$APPLY" == "1" ]]; then
    docker volume ls -q --filter dangling=true --filter label=com.docker.compose.project=threatflow \
        | xargs -r docker volume rm 2>&1 | tail -3 || true
else
    say "  (would: docker volume rm \$(docker volume ls -q --filter dangling=true --filter label=com.docker.compose.project=threatflow))"
fi

# 5) Old local backups (keep last 7)
say ""
if [[ -d backups ]]; then
    OLD=$(ls -1t backups/ 2>/dev/null | tail -n +8 | wc -l || echo 0)
    say "local backups older than the most recent 7: ${OLD} dir(s)"
    if [[ "$APPLY" == "1" && "$OLD" -gt 0 ]]; then
        ls -1t backups/ | tail -n +8 | while read -r d; do rm -rf "backups/${d}"; done
        say "  removed ${OLD} backup dir(s)"
    fi
fi

say ""
say "DONE — disk now:"
df -h / | tail -1
say ""
[[ "$APPLY" == "0" ]] && say "(report-only mode; rerun with --apply to actually delete)"
