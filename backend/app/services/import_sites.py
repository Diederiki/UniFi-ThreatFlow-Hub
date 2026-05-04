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


async def _fetch_sites(api_key: str) -> list[ImportItem]:
    """Hit /ea/hosts AND /ea/sites and merge so each site gets a name."""
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
                    hid = h.get("id") or h.get("hostId")
                    rs = h.get("reportedState") or {}
                    name = (h.get("name")
                            or (rs.get("name") if isinstance(rs, dict) else None)
                            or (rs.get("hostname") if isinstance(rs, dict) else None))
                    if hid and name:
                        hosts_by_id[str(hid)] = str(name)
        except Exception as e:  # noqa: BLE001
            log.warning("hosts fetch failed (continuing with site-only names): %s", e)

        for s in (sites_r.json().get("data") or []):
            if not isinstance(s, dict):
                continue
            site_id = s.get("siteId") or s.get("id")
            if not site_id:
                continue
            host_id = s.get("hostId") or (s.get("host") or {}).get("id")
            host_name = hosts_by_id.get(str(host_id)) if host_id else None
            # Site name preference: meta.name → name → hostName → host_name → siteId
            meta = s.get("meta") or {}
            name = (
                (meta.get("name") if isinstance(meta, dict) else None)
                or s.get("name")
                or s.get("internalReference")
                or host_name
                or str(site_id)
            )
            items.append(ImportItem(
                name=str(name).strip(),
                site_id=str(site_id),
                host_id=str(host_id) if host_id else None,
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
