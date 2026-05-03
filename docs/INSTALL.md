# UniFi ThreatFlow Hub

Central web platform that pulls near-real-time network security and traffic-flow data **directly from each UniFi UDM Pro / UDM Pro Max** every 30 seconds and surfaces it in a dark NOC/SOC dashboard.

> **This is not** an IPFIX collector, a generic SIEM, or a syslog aggregator. It speaks the UniFi Network Web API and falls back to legacy IPS endpoints when needed.

The blueprint that drives this project is in the [original spec](https://github.com/Diederiki/UniFi-ThreatFlow-Hub). Phase progress is tracked in [`PHASE_CHECKPOINTS.md`](./PHASE_CHECKPOINTS.md).

## What it shows

- IDS/IPS events, blocked traffic, allowed traffic, suspicious traffic
- Top branches, top domains, top apps, top categories, top risky clients, top external destinations
- Threat signatures, policy actions, branch health, collector status
- Long-term trend summaries (5 minutes → 1 year)

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 15 + React + TypeScript + TailwindCSS + Recharts |
| Backend | FastAPI + Python 3.12 + SQLAlchemy + Alembic + Pydantic v2 |
| Control-plane DB | PostgreSQL 16 |
| Analytics DB | ClickHouse 24 (MergeTree + rollups + TTL) |
| Queue / locks / cache | Redis 7 |
| Collector | Python 3.12 async workers (httpx) |
| Reverse proxy | Whatever the host already runs (nginx in our case) |
| Container | Docker Compose |

## Requirements

- Ubuntu 24.04 (or any Docker host)
- Docker 24+ with Compose v2
- ~2 GB RAM minimum for a single-tenant dev box; see *Sizing* below for production

## Installation

```bash
git clone https://github.com/Diederiki/UniFi-ThreatFlow-Hub.git
cd UniFi-ThreatFlow-Hub
cp .env.example .env
./scripts/init.sh          # generates SESSION_SECRET / JWT_SECRET / FERNET_KEY / POSTGRES_PASSWORD / etc.
docker compose up -d --build
./scripts/run-migrations.sh
./scripts/create-admin.sh  # prints the auto-generated admin password
./scripts/healthcheck.sh
```

## First login

Open `http://localhost:18090` (or your reverse-proxied URL) and sign in with the admin email + the password printed by `scripts/create-admin.sh`.

## Adding your first branch

1. Go to **Branches → Add branch**.
2. Fill in the controller URL (e.g. `https://192.168.1.1`), site ID (often `default`), credentials.
3. Click **Test Connection** → green check.
4. Click **Discover Sites** if you don't know the site ID.
5. Click **Save & Start Collector**.

If you don't have UniFi gear handy, leave `MOCK_DATA=true` in `.env` — the collector will generate realistic fake flows/threats so the UI is fully exercisable.

## Viewing the dashboard

The sidebar groups everything you'd expect:

```
Overview · Threats · Blocked Traffic · Top Visited
Branches · Clients · Destinations · Categories
Suspicion Score · Collector Health · Storage Health · Settings
```

A global timeframe selector at the top of every page lets you jump between **5m / 15m / 1h / 4h / 12h / 24h / 3d / 7d / 14d / 1m / 6m / 1y**. Long timeframes are served from rollups, never raw scans.

## Backup & restore

```bash
./scripts/backup.sh    # writes to ./backups/<UTC>/{postgres.sql,clickhouse.tar.gz}
./scripts/restore.sh ./backups/<UTC>
```

## Production notes

- All container ports bind `127.0.0.1` only. Put a real reverse proxy (nginx/Caddy/Traefik) in front and terminate TLS there.
- Set `APP_ENV=production` in `.env` to disable verbose error pages.
- `MOCK_DATA=false` once real branches are configured.
- Configure backups to an off-host destination (S3, Backblaze, restic).

## Sizing

Minimum production single-server:
- 24 cores
- 128 GB RAM
- 15 TB usable enterprise NVMe (power-loss-protected)
- 1 Gbps network minimum, 10 Gbps preferred

Recommended split:
- App / collector node: 12–16 cores, 64 GB RAM, 1 TB NVMe
- DB node: 32 cores, 256 GB ECC RAM, 30 TB enterprise NVMe, 10 Gbps NIC

Avoid spinning disks for live ClickHouse storage.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Collector stuck in `error` | UniFi controller cert is self-signed | Set `ssl_verify=false` on the branch (warned in UI) |
| Test Connection 401 | Wrong endpoint family | Try the legacy adapter — endpoint differs by Network app version |
| Dashboard slow on `1y` timeframe | Hitting raw tables | Verify `rollup_1d` MV is populated; see Storage Health |
| ClickHouse out of disk | TTL too long | Lower `CH_TTL_*` in `.env` or `Settings → Retention` |

## License

Internal AmSpec project.
