# Restore runbook

A complete restore replays Postgres (control-plane) and ClickHouse (analytics) from a snapshot taken by `scripts/backup.sh`.

## 1. Postgres

`scripts/restore.sh <backup-dir>` does this for you. It pipes `postgres.sql.gz` into the running container's `psql`. Existing rows with conflicting primary keys cause failures — DROP/CREATE the database first if you want a hard restore:

```bash
docker compose exec -T postgres psql -U $POSTGRES_USER -d postgres -c "DROP DATABASE $POSTGRES_DB"
docker compose exec -T postgres psql -U $POSTGRES_USER -d postgres -c "CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER"
./scripts/restore.sh ./backups/<stamp>
```

## 2. ClickHouse

Snapshot format: `ALTER TABLE … FREEZE WITH NAME '<stamp>'` produces hard-linked parts under `/var/lib/clickhouse/shadow/<stamp>/`. The backup script tar-gzips the whole shadow directory.

`scripts/restore.sh` extracts the tarball back into `/var/lib/clickhouse/shadow/<stamp>/`. To re-attach the parts:

```bash
docker compose exec -T clickhouse clickhouse-client -u $CLICKHOUSE_USER --password "$CLICKHOUSE_PASSWORD" -d threatflow -q "
SYSTEM STOP MERGES raw_flow_events;
ALTER TABLE raw_flow_events ATTACH PARTITION '202605' FROM '/var/lib/clickhouse/shadow/<stamp>/store/...';
SYSTEM START MERGES raw_flow_events;
"
```

The exact `FROM '<path>'` differs per part — list them with:

```bash
docker compose exec -T clickhouse find /var/lib/clickhouse/shadow/<stamp>/ -maxdepth 5 -type d
```

For a faster operational path consider [clickhouse-backup](https://github.com/AlexAkulov/clickhouse-backup) which automates the FREEZE + ATTACH cycle.

## 3. Validate

After both steps:

```bash
./scripts/healthcheck.sh
docker compose exec -T postgres psql -U $POSTGRES_USER $POSTGRES_DB -c "SELECT count(*) FROM branches;"
docker compose exec -T clickhouse clickhouse-client -u $CLICKHOUSE_USER --password "$CLICKHOUSE_PASSWORD" -d threatflow -q "SELECT count() FROM raw_flow_events;"
```
