"""POST /api/admin/ingest/cloudproxy — accept pre-mapped events from a
local cloud-proxy capture run and insert them into ClickHouse.

This endpoint is the bridge for `tools/cloudproxy_capture/` which uses
Playwright to attach to a browser session and decode the WebRTC data
channel. The capture script ships pre-mapped rows in the same shape
the in-cluster collector emits, so the only server-side work is:

  1. Verify the branch_id exists and stamp the canonical name/code.
  2. Run the threat_enricher to populate mitre_techniques /
     mitre_tactics / cve_refs (matches behaviour of in-cluster ingest).
  3. Bulk-insert via the existing ClickHouse client.

Auth: admin role required. The CH inserts go straight to the same
tables the collector writes, so a malicious caller could pollute
dashboards — admin-only is the right bar.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.auth.dependencies import require_role
from app.clickhouse import client as ch
from app.db.session import SessionLocal
from app.models.user import User
from app.services.threat_enricher import enrich_threats

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/ingest", tags=["admin"])

FLOW_COLS = [
    "event_hash", "branch_id", "branch_name", "branch_code",
    "event_time", "action", "risk", "severity",
    "policy_type", "policy_name",
    "source_ip", "source_port", "source_mac", "source_hostname", "source_vlan",
    "destination_ip", "destination_port", "destination_hostname", "destination_country",
    "protocol", "application", "application_category",
    "bytes_up", "bytes_down", "packets_up", "packets_down",
    "duration_ms", "direction", "raw_json", "collector_version",
]
THREAT_COLS = [
    "event_hash", "branch_id", "branch_name", "branch_code",
    "event_time", "action", "severity", "risk",
    "signature", "threat_category",
    "policy_type", "policy_name",
    "source_ip", "source_port", "source_mac", "source_hostname",
    "destination_ip", "destination_port", "destination_hostname", "destination_country",
    "protocol",
    "client_ip", "client_mac", "client_hostname",
    "mitre_techniques", "mitre_tactics", "cve_refs",
    "raw_json", "collector_version",
]


class CloudProxyIngestRequest(BaseModel):
    branch_id: UUID
    flow_rows:   list[dict[str, Any]] = Field(default_factory=list)
    threat_rows: list[dict[str, Any]] = Field(default_factory=list)


class CloudProxyIngestResponse(BaseModel):
    branch_id: UUID
    branch_code: str
    flows_inserted: int
    threats_inserted: int


def _stamp(rows: list[dict[str, Any]], branch_id: str, branch_name: str, branch_code: str) -> None:
    """Force the trusted branch identifiers from the DB onto every row,
    so a malicious capture client can't mislabel events into a different
    branch's bucket. Also coerce ISO event_time strings -> tz-aware
    datetimes so the ClickHouse driver can serialize them."""
    for r in rows:
        r["branch_id"] = branch_id
        r["branch_name"] = branch_name
        r["branch_code"] = branch_code
        et = r.get("event_time")
        if isinstance(et, str):
            try:
                dt = datetime.fromisoformat(et.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                r["event_time"] = dt
            except ValueError:
                r["event_time"] = datetime.now(timezone.utc)


@router.post("/cloudproxy", response_model=CloudProxyIngestResponse)
async def ingest_cloudproxy(
    body: CloudProxyIngestRequest,
    _user: User = Depends(require_role("admin")),
) -> CloudProxyIngestResponse:
    bid = str(body.branch_id)

    async with SessionLocal() as db:
        row = (await db.execute(
            text("SELECT name, branch_code FROM branches WHERE id = :bid"),
            {"bid": bid},
        )).mappings().one_or_none()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="branch_not_found")
    branch_name = str(row["name"])
    branch_code = str(row["branch_code"])

    _stamp(body.flow_rows,   bid, branch_name, branch_code)
    _stamp(body.threat_rows, bid, branch_name, branch_code)

    enrich_threats(body.threat_rows)
    # Make sure required columns exist on every row so the CH insert doesn't
    # error out on a missing key — fill with empty defaults matching the
    # ClickHouse column types.
    for r in body.threat_rows:
        r.setdefault("mitre_techniques", [])
        r.setdefault("mitre_tactics", [])
        r.setdefault("cve_refs", [])

    flows_n = await ch.insert_batch("threatflow.raw_flow_events",   body.flow_rows,   FLOW_COLS) if body.flow_rows else 0
    threats_n = await ch.insert_batch("threatflow.raw_threat_events", body.threat_rows, THREAT_COLS) if body.threat_rows else 0

    log.info(
        "cloudproxy ingest by user=%s branch=%s flows=%d threats=%d",
        _user.email, branch_code, flows_n, threats_n,
    )
    return CloudProxyIngestResponse(
        branch_id=body.branch_id, branch_code=branch_code,
        flows_inserted=flows_n, threats_inserted=threats_n,
    )
