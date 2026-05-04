"""Pull the list of cloud-mode branches the streamer should track.

Re-uses the same Postgres connection details the rest of the stack does.
We only ever READ from Postgres here — branch state is owned by the
backend / collector. The streamer just needs (id, branch_code, console_url)
so it knows which Insights URL to open per branch.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Iterable

import asyncpg

log = logging.getLogger("streamer.branches")


@dataclass(frozen=True)
class Branch:
    id: str
    name: str
    branch_code: str
    controller_url: str
    site_id: str

    def insights_url(self) -> str | None:
        """Derive the Insights/Flows URL by appending to the stored
        controller_url (which is already the full unifi.ui.com console URL,
        e.g. `https://unifi.ui.com/consoles/<HOST:COSMOS>/network/<site_id>`).
        Insights/Flows auto-subscribes the WebRTC channel to events,
        which is what the streamer needs."""
        u = (self.controller_url or "").strip().rstrip("/")
        if "unifi.ui.com/consoles/" not in u:
            log.warning("branch %s has non-cloud controller_url=%r", self.branch_code, u)
            return None
        return f"{u}/insights/flows"


_DSN_FROM_ENV = re.compile(r"\$\{([A-Z_]+)\}")


def _dsn() -> str:
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db   = os.environ.get("POSTGRES_DB",   "threatflow")
    user = os.environ.get("POSTGRES_USER", "threatflow")
    pwd  = os.environ.get("POSTGRES_PASSWORD", "")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


async def fetch_cloud_branches() -> list[Branch]:
    conn = await asyncpg.connect(_dsn())
    try:
        rows = await conn.fetch(
            """
            SELECT id::text AS id, name, branch_code, controller_url, site_id
            FROM branches
            WHERE enabled = TRUE
              AND auth_method = 'api_key'
              AND controller_url ILIKE '%ui.com%'
            ORDER BY name
            """
        )
    finally:
        await conn.close()
    return [
        Branch(
            id=r["id"], name=r["name"], branch_code=r["branch_code"],
            controller_url=r["controller_url"], site_id=r["site_id"],
        )
        for r in rows
    ]


def filter_streamable(branches: Iterable[Branch]) -> list[Branch]:
    """Drop branches we can't derive an Insights URL for."""
    out: list[Branch] = []
    for b in branches:
        if b.insights_url():
            out.append(b)
        else:
            log.warning("skipping unstreamable branch: %s (%s)", b.branch_code, b.site_id)
    return out
