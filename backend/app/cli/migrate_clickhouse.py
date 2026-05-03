"""Idempotently apply the ClickHouse schema.

ClickHouse's docker-entrypoint-initdb only runs on a fresh data dir. For an
existing cluster, run this from inside the backend container:

    python -m app.cli.migrate_clickhouse

Every statement uses CREATE … IF NOT EXISTS, so re-running is a no-op.
"""
import asyncio
import sys

from app.clickhouse.client import _new_client
from app.clickhouse.schema import load_schema, split_statements


async def main() -> int:
    sql = load_schema()
    stmts = split_statements(sql)
    print(f"[ch-migrate] applying {len(stmts)} statement(s)…")
    client = _new_client()  # one client for the whole serial migration is fine
    try:
        applied = 0
        for stmt in stmts:
            try:
                await asyncio.to_thread(client.command, stmt)
                applied += 1
            except Exception as e:  # noqa: BLE001
                print(f"[ch-migrate] FAILED on statement {applied + 1}: {e}", file=sys.stderr)
                print(f"---\n{stmt[:300]}\n---", file=sys.stderr)
                return 2
        print(f"[ch-migrate] {applied}/{len(stmts)} ok")
        return 0
    finally:
        try: client.close()
        except Exception: pass


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
