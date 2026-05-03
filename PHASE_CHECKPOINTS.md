# UniFi ThreatFlow Hub — Phase Checkpoints

**Source of truth:** the blueprint README at `Diederiki/UniFi-ThreatFlow-Hub` (1158 lines). This file tracks phase-by-phase progress so a fresh session can resume cleanly.

## Project facts

| Thing | Value |
|---|---|
| Local clone | `C:\UniFi-ThreatFlow-Hub` |
| GitHub repo | https://github.com/Diederiki/UniFi-ThreatFlow-Hub |
| Default branch | `main` |
| Target VPS | `51.195.82.50` (OVH, Ubuntu 24.04, 24c/92GB, SHARED with 5+ apps) |
| Target domain | `threatflow.amspec.group` (Cloudflare proxy OFF during build) |
| Reverse proxy | **existing nginx** on host (NOT Caddy — would collide) |
| Brand | "UniFi Threatflow Hub for AmSpec" |
| Admin email | `diederik.vantienen@amspecgroup.com` (auto-gen pw printed at init) |
| Default mode | `MOCK_DATA=true` until real UniFi creds shared |

## Co-tenancy contract (MUST NOT VIOLATE)

The VPS already serves `compress.amspec.group`, `secure-share`, `servicedesk`, `expense.amspec.group`, `stock-report.amspec.group`, plus a `amspec-v2` Docker stack and system mysql/postgres. Hard rules:

1. **Never publish a port on `0.0.0.0`** — bind to `127.0.0.1` only.
2. **Never touch system nginx config beyond adding one new server block** for `threatflow.amspec.group`.
3. **Never use system postgres/mysql** — run our own in Docker on an isolated network.
4. **Never enable UFW** without coordination — VPS likely behind OVH cloud firewall and a stray `ufw enable` could lock out other services.
5. **Never restart docker.service** — would kick the amspec-v2 stack. Use `docker compose restart` per-stack only.

Allocated host-loopback ports:
- `127.0.0.1:18090` → frontend (Next.js)
- `127.0.0.1:18091` → backend (FastAPI)

ClickHouse / Postgres / Redis stay inside the docker network only (`threatflow_net`), no host port at all.

## Phase progress

| Phase | Title | Status | Commit | Notes |
|---|---|---|---|---|
| 1 | Monorepo + Docker stack + Postgres + ClickHouse + Redis + FastAPI + Next.js + auth + dark layout | 🔄 in-progress |  |  |
| 2 | PG migrations + branch CRUD + credential encryption + branch UI + test connection stub | ⬜ pending |  |  |
| 3 | ClickHouse schema + raw event tables + rollups + materialized views + storage health API | ⬜ pending |  |  |
| 4 | Collector service + UniFi adapters + traffic-flows + IPS fallback + mock collector + 30s scheduler + dedupe + batch insert | ⬜ pending |  |  |
| 5 | Dashboard APIs + overview/threats/blocked/top-visited/branch-detail/collector-health pages | ⬜ pending |  |  |
| 6 | Suspicion scoring + scoring settings + top suspicious lists + trend charts | ⬜ pending |  |  |
| 7 | Tests + docs + production hardening + backup/restore + deploy to `threatflow.amspec.group` | ⬜ pending |  |  |

## Acceptance criteria per phase

### Phase 1
- [ ] Monorepo dirs exist: `backend/`, `frontend/`, `collector/`, `infra/`, `scripts/`
- [ ] `docker-compose.yml` boots: frontend, backend, collector, postgres, clickhouse, redis
- [ ] All host-bound ports are `127.0.0.1`-only
- [ ] `.env.example` is complete; init script generates real `.env`
- [ ] FastAPI `/api/health` returns `{status:"ok"}`
- [ ] Postgres has at least the `users`, `sessions`, `app_settings` tables seeded by Alembic
- [ ] ClickHouse boots and reports `SELECT 1`
- [ ] Next.js dark-themed login page renders, can authenticate, lands on `/overview` placeholder
- [ ] Auto-generated admin password printed by `scripts/create-admin.sh`
- [ ] `scripts/healthcheck.sh` returns 0

### Phase 2
- [ ] Alembic migrations for all blueprint tables: `users`, `roles`, `branches`, `branch_credentials`, `collector_status`, `collector_runs`, `app_settings`, `audit_logs`
- [ ] Fernet encryption for branch creds (key from `.env`, never logged)
- [ ] Branches CRUD API + RBAC + audit log writes
- [ ] Frontend `/branches` page with add/edit/delete/enable/disable/test-connection buttons
- [ ] Test connection stub returns mock OK in mock mode

### Phase 3
- [ ] ClickHouse schema for `raw_flow_events`, `raw_threat_events`, `rollup_1m`, `rollup_5m`, `rollup_15m`, `rollup_1h`, `rollup_1d`
- [ ] MergeTree, partitioning, ORDER BY tuned per blueprint
- [ ] TTL policies wired (configurable via `.env`)
- [ ] Materialized views OR scheduled aggregation jobs populate rollups
- [ ] `/api/storage/health` returns row counts, GB/day, retention, oldest event

### Phase 4
- [ ] `BaseUniFiCollector` ABC + `UniFiNetworkV2TrafficFlowsCollector` + `LegacyUniFiIpsEventCollector` + mock collector
- [ ] Per-branch lock (Redis) preventing overlap
- [ ] 30s scheduler with default 10 concurrent branches, configurable
- [ ] Dedupe via `event_hash`
- [ ] Batch insert into ClickHouse (configurable size + flush interval)
- [ ] Failed branch must not stop other branches; failures logged + visible in `/api/collectors/status`

### Phase 5
- [ ] Global timeframe selector (12 windows), all dashboard APIs honor it
- [ ] Auto-refresh every 30s on every page
- [ ] Pages: Overview, Threats, Blocked Traffic, Top Visited, Branches (list+detail), Clients (list+detail), Destinations, Categories, Collector Health, Storage Health, Settings
- [ ] Loading + error states; pagination on raw tables
- [ ] Long timeframes (6m / 1y) hit rollups, not raw

### Phase 6
- [ ] Configurable scoring weights in Settings
- [ ] Suspicion Score page with top branches/clients/destinations/signatures + trend
- [ ] Score visible on Overview + Branch detail

### Phase 7
- [ ] Tests for every backend module the blueprint enumerates
- [ ] Backup + restore scripts (PG + ClickHouse)
- [ ] Production hardening (rate limit, security headers, CORS, no debug)
- [ ] Live deploy at https://threatflow.amspec.group with valid LE cert
- [ ] `scripts/healthcheck.sh` returns all-green post-deploy
- [ ] README updated with sizing, troubleshooting, runbooks

## Open coordination

- [ ] User must add Cloudflare A record `threatflow.amspec.group` → `51.195.82.50` (proxy OFF) before Phase 7 cert step.
- [ ] User to share real UniFi controller URLs / site IDs / creds for at least one branch when ready (until then mock-only).
- [ ] User to confirm whether to enable UFW or rely on OVH cloud firewall — defer.
