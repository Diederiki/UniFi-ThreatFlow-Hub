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
| 1 | Monorepo + Docker stack + Postgres + ClickHouse + Redis + FastAPI + Next.js + auth + dark layout | ✅ code-complete | `1019952` | runtime verification pending first VPS deploy |
| 2 | PG migrations + branch CRUD + credential encryption + branch UI + test connection stub | ✅ done | `566e4d9` | E2E verified on VPS — Fernet ciphertext confirmed in DB, 0 plaintext leaks anywhere |
| 3 | ClickHouse schema + raw event tables + rollups + materialized views + storage health API | ✅ done | `f16bd16` | 13 CH tables/MVs live, MV propagation verified, 7 TTLs read correctly |
| 4 | Collector service + UniFi adapters + traffic-flows + IPS fallback + mock collector + 30s scheduler + dedupe + batch insert | ✅ done | `cae91d1` | 5 mock branches × 30s tick → 6823 raw flows + 343 threats in 2 min, 0 failed inserts, all rollups + topK/uniq state verified |
| 5 | Dashboard APIs + overview/threats/blocked/top-visited/branch-detail/collector-health pages | ⬜ pending |  |  |
| 6 | Suspicion scoring + scoring settings + top suspicious lists + trend charts | ⬜ pending |  |  |
| 7 | Tests + docs + production hardening + backup/restore + deploy to `threatflow.amspec.group` | ⬜ pending |  |  |

## Acceptance criteria per phase

### Phase 1
- [x] Monorepo dirs exist: `backend/`, `frontend/`, `collector/`, `infra/`, `scripts/`
- [x] `docker-compose.yml` defines: frontend, backend, collector, postgres, clickhouse, redis (validates with `docker compose config`)
- [x] All host-bound ports are `127.0.0.1`-only
- [x] `.env.example` is complete; `scripts/init.sh` generates real `.env` with auto-gen secrets (Fernet, JWT, session, DB passwords)
- [x] FastAPI `/api/health` + `/api/health/deep` defined
- [x] Alembic migration `20260503_0001` creates `roles`, `users`, `app_settings`, `audit_logs` and seeds 3 canonical roles
- [x] ClickHouse `init/00-create-db.sql` creates `threatflow` database
- [x] Next.js dark-themed login page POSTs to `/api/auth/login`, lands on `/overview` placeholder; full sidebar with all 12 blueprint pages
- [x] `scripts/create-admin.sh` auto-generates admin password and prints once
- [x] **Runtime acceptance — LIVE on `51.195.82.50` as of 2026-05-03**:
  - [x] `docker compose -f docker-compose.yml up -d --build` succeeds (6/6 containers healthy)
  - [x] `scripts/run-migrations.sh` succeeds (`20260503_0001` applied)
  - [x] `scripts/create-admin.sh` prints credentials (admin user inserted)
  - [x] `scripts/healthcheck.sh` returns 0 (11 OK / 0 FAIL after `source .env` fix in 585faf8)
  - [x] Login → JWT cookie → `/api/auth/me` round-trip works through nginx
  - [x] Bad password → 401
  - [x] Collector heartbeats every 30s (mock=True)
  - [x] Existing 5 production sites on the VPS unaffected by the new nginx server block
  - [x] **Browser sign-in at https://threatflow.amspec.group LIVE** — DNS resolved, `certbot --nginx` succeeded, LE cert good till 2026-08-01, `/login` + `/api/health` both 200 over HTTPS, all 5 other VPS sites unaffected (compress 307, share 307, servicedesk 200, expense 200, stock-report 200)

### Phase 2
- [x] Alembic `20260503_0002` adds `branches`, `branch_credentials`, `collector_status`, `collector_runs` (+ pgcrypto extension)
- [x] Fernet at-rest encryption (`app.utils.encryption`); confirmed via plaintext-marker probe — 0 leaks in DB or audit log
- [x] `/api/branches` CRUD + enable/disable/test-connection/discover-sites with role gates (admin / operator / viewer)
- [x] Audit log writes on every mutation, visible via `audit_logs` table
- [x] Frontend `/branches` list with status badges + inline test/enable/disable/delete
- [x] Frontend `/branches/new` and `/branches/[id]` sharing one `BranchForm` with all blueprint-required buttons
- [x] Mock test-connection returns realistic endpoint + UniFi-OS version + sites
- [x] Architecture insight: blueprint assumes per-branch local controller URLs, but user actually accesses everything via the `unifi.ui.com` cloud portal — Phase 4 will ship two adapters (`LocalControllerAdapter` + `UnifiCloudAdapter`)

### Phase 3
- [x] ClickHouse schema for all 7 blueprint tables + 5 MVs + 1 dead-letter table
- [x] ReplacingMergeTree(ingest_time) keyed on event_hash for natural dedup; partition by month; ORDER BY (branch_id, event_time, event_hash)
- [x] AggregatingMergeTree rollups storing sumState counters + uniqState(client/dest) + topKState(20)(clients/dests/domains/apps/categories/countries)
- [x] 5 MVs populating rollups directly from raw (no MV chaining → independently rebuildable)
- [x] TTLs default 90/180/180/365/365/730/1825 (matches blueprint), runtime-tunable via PUT /api/storage/retention
- [x] `/api/storage/health` returns rows, on-disk + uncompressed bytes, compression ratio, parts, oldest/newest, failed_inserts_30d, rollup_freshness, /day estimate
- [x] Frontend `/storage-health` page with auto-refresh 30s
- [x] **Verified**: 100 fake inserts → all 5 rollups auto-populated via MVs, 37× compression on rollup_1m

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
