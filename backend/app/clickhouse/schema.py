"""Embedded copy of the ClickHouse schema, served by the migrate CLI.

We keep the canonical SQL in `infra/clickhouse/init/01-schema.sql` for
docker-entrypoint-initdb on first boot. For existing databases we read the
same file and apply it idempotently via the migrate CLI.
"""
from pathlib import Path

# In-container path; matches WORKDIR /app and the Dockerfile COPY layout
SCHEMA_PATH = Path("/app/clickhouse_schema/01-schema.sql")


def load_schema() -> str:
    if SCHEMA_PATH.exists():
        return SCHEMA_PATH.read_text(encoding="utf-8")
    # Fall back to repo-relative path for local dev
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "infra" / "clickhouse" / "init" / "01-schema.sql",
        here.parents[2] / "infra" / "clickhouse" / "init" / "01-schema.sql",
    ]
    for c in candidates:
        if c.exists():
            return c.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"clickhouse schema not found at {SCHEMA_PATH} or any of {candidates}"
    )


def split_statements(sql: str) -> list[str]:
    """Split on top-level `;` while ignoring those inside string literals.
    Safe enough for our DDL since we don't have semicolons inside identifiers
    or strings."""
    stmts: list[str] = []
    buf: list[str] = []
    in_quote = False
    quote_char = ""
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_quote:
            buf.append(ch)
            if ch == quote_char and (i == 0 or sql[i - 1] != "\\"):
                in_quote = False
        else:
            if ch in ("'", '"'):
                in_quote = True
                quote_char = ch
                buf.append(ch)
            elif ch == ";":
                stmt = "".join(buf).strip()
                if stmt:
                    stmts.append(stmt)
                buf = []
            else:
                buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return [
        s for s in stmts
        if not all(line.strip().startswith("--") or not line.strip() for line in s.splitlines())
    ]
