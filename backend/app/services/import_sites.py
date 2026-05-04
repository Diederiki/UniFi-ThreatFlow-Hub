"""Bulk import every Site Manager site as a Threatflow branch.

Uses the same Site Manager API key flow as test-connection. For each row
returned by /ea/sites we upsert a Threatflow branch (matched by branch_code
== siteId — stable identifier). The API key is encrypted once and reused
for every newly-created branch so the user only pastes it in one place.

Read-only against UniFi: only GET /ea/hosts and GET /ea/sites are issued.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch, BranchCredential, CollectorStatus
from app.services.unifi_http import make_client
from app.utils.encryption import encrypt

log = logging.getLogger("import_sites")

SITE_MANAGER_BASE = "https://api.ui.com"
_SLUG = re.compile(r"[^A-Za-z0-9_\-]+")


def _slug(s: str) -> str:
    """branch_code must match ^[A-Za-z0-9_\\-]+$ per the schema; turn the
    site name into something acceptable, capped at 64 chars."""
    out = _SLUG.sub("-", s).strip("-")
    return (out or "site")[:64]


@dataclass
class ImportItem:
    name: str            # human readable
    site_id: str         # UniFi site UUID
    host_id: str | None  # parent console UUID (when discoverable)
    host_name: str | None


@dataclass
class ImportSummary:
    total_seen: int
    created: int
    skipped_existing: int
    failed: int
    errors: list[str]


def _strip_host_suffix(host_id: str | None) -> str | None:
    """/ea/sites returns hostId with a ':NNNNN' suffix that /ea/hosts strips
    on the `id` field. Normalize so the lookup tables match."""
    if not host_id:
        return None
    return host_id.split(":", 1)[0]


async def _fetch_sites(api_key: str) -> list[ImportItem]:
    """Hit /ea/hosts AND /ea/sites and merge so each site gets a real name."""
    headers = {"X-API-KEY": api_key, "Accept": "application/json"}
    items: list[ImportItem] = []

    async with make_client(timeout=15) as client:
        sites_r = await client.get(f"{SITE_MANAGER_BASE}/ea/sites", headers=headers)
        if sites_r.status_code != 200:
            raise RuntimeError(f"sites_http_{sites_r.status_code}: {sites_r.text[:200]}")

        hosts_by_id: dict[str, str] = {}
        try:
            hosts_r = await client.get(f"{SITE_MANAGER_BASE}/ea/hosts", headers=headers)
            if hosts_r.status_code == 200:
                for h in (hosts_r.json().get("data") or []):
                    if not isinstance(h, dict):
                        continue
                    # /ea/hosts.id is the canonical form WITHOUT :NNNN suffix —
                    # /ea/sites.hostId carries that suffix, so we'll strip there.
                    hid = _strip_host_suffix(h.get("id") or h.get("hostId"))
                    rs = h.get("reportedState") or {}
                    name = None
                    if isinstance(rs, dict):
                        name = rs.get("name") or rs.get("hostname")
                        if not name:
                            hw = rs.get("hardware") or {}
                            if isinstance(hw, dict):
                                name = hw.get("name") or hw.get("shortname")
                    name = name or h.get("name")
                    if hid and name:
                        hosts_by_id[hid] = str(name).strip()
        except Exception as e:  # noqa: BLE001
            log.warning("hosts fetch failed (continuing with site-only names): %s", e)

        for s in (sites_r.json().get("data") or []):
            if not isinstance(s, dict):
                continue
            site_id = s.get("siteId") or s.get("id")
            if not site_id:
                continue
            raw_host_id = s.get("hostId") or (s.get("host") or {}).get("id")
            host_id = _strip_host_suffix(raw_host_id) if raw_host_id else None
            host_name = hosts_by_id.get(host_id) if host_id else None

            meta = s.get("meta") or {}
            stats = s.get("statistics") or {}
            gateway = stats.get("gateway") if isinstance(stats, dict) else {}
            isp = stats.get("ispInfo") if isinstance(stats, dict) else {}

            site_internal = meta.get("name") if isinstance(meta, dict) else None  # usually "default"
            site_desc = meta.get("desc") if isinstance(meta, dict) else None
            short = (gateway.get("shortname") if isinstance(gateway, dict) else None)
            isp_org = (isp.get("organization") if isinstance(isp, dict) else None)
            mac = meta.get("gatewayMac") if isinstance(meta, dict) else None

            # Name preference for the branch:
            #   1. Host's reported name (e.g. "AmSpec-Dordrecht")
            #   2. If multiple sites per host: append site internal ref ("HQ - default")
            #   3. Site description if non-default
            #   4. Gateway shortname (a UI-assigned 6-letter code like "UDRULT")
            #   5. ISP org as a hint of location
            #   6. Last 6 chars of siteId — guaranteed unique fallback
            name = host_name
            if not name:
                if site_desc and site_desc.lower() not in ("default", ""):
                    name = site_desc
                elif short:
                    name = f"console {short}"
                elif isp_org:
                    name = f"site at {isp_org}"
                else:
                    name = f"site {str(site_id)[-6:]}"

            items.append(ImportItem(
                name=str(name).strip(),
                site_id=str(site_id),
                host_id=host_id,
                host_name=host_name,
            ))
    return items


async def import_all_sites(db: AsyncSession, api_key: str) -> ImportSummary:
    """Idempotent: existing branches (matched by branch_code == site_id slug)
    are left alone so re-running is safe."""
    summary = ImportSummary(total_seen=0, created=0, skipped_existing=0, failed=0, errors=[])

    try:
        items = await _fetch_sites(api_key)
    except Exception as e:  # noqa: BLE001
        summary.errors.append(str(e))
        return summary

    summary.total_seen = len(items)

    # Pre-fetch existing branch_codes once
    existing = set(
        (await db.execute(select(Branch.branch_code))).scalars().all()
    )

    # Reusable encrypted blob — stored once per branch
    enc_api_key = encrypt(api_key)

    for it in items:
        # Branch code must be unique. Prefer a short slug of the human name,
        # but include a 6-char site-id suffix for uniqueness.
        code_root = _slug(it.name)[:50]
        code = f"{code_root}-{it.site_id[-6:]}" if code_root else it.site_id[:64]

        if code in existing:
            summary.skipped_existing += 1
            continue

        try:
            controller_url = (
                f"https://unifi.ui.com/consoles/{it.host_id}/network/{it.site_id}"
                if it.host_id else "https://unifi.ui.com"
            )
            branch = Branch(
                name=it.name,
                branch_code=code,
                controller_url=controller_url,
                site_id=it.site_id,
                gateway_model=None,
                auth_method="api_key",
                ssl_verify=True,
                polling_interval_seconds=30,
                enabled=True,
                notes=f"Imported from Site Manager (host {it.host_name or it.host_id or '?'})",
                tags=["imported"],
            )
            db.add(branch)
            await db.flush()  # assign branch.id
            db.add(BranchCredential(branch_id=branch.id, encrypted_api_key=enc_api_key))
            db.add(CollectorStatus(branch_id=branch.id, status="never_run"))
            existing.add(code)
            summary.created += 1
        except Exception as e:  # noqa: BLE001
            summary.failed += 1
            summary.errors.append(f"{it.name}: {type(e).__name__}: {e}")
            await db.rollback()
            continue

    await db.commit()
    log.info("site import summary: seen=%d created=%d skipped=%d failed=%d",
             summary.total_seen, summary.created, summary.skipped_existing, summary.failed)
    return summary
