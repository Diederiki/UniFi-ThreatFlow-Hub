"""Bulk import every Site Manager site as a Threatflow branch.

Uses the same Site Manager API key flow as test-connection. For each row
returned by /ea/sites we upsert a Threatflow branch (matched by branch_code).
The API key is encrypted once and reused for every newly-created branch so
the user only pastes it in one place.

Read-only against UniFi: only GET /ea/hosts and GET /ea/sites are issued.

`firewalls_only=True` (default) keeps gateways with flow/threat data
(UDM family, UDR family, UCG family, Fortress) and skips Cloudkey Plus
controllers, NVRs, software-only hosts.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch, BranchCredential, CollectorStatus
from app.services.unifi_http import make_client
from app.utils.encryption import encrypt

log = logging.getLogger("import_sites")

SITE_MANAGER_BASE = "https://api.ui.com"
_SLUG = re.compile(r"[^A-Za-z0-9_\-]+")

# Substring matchers against /ea/hosts → reportedState.hardware.name
_FIREWALL_HW_KEYWORDS = (
    "dream machine",       # UDM, UDM Pro, UDM Pro Max, UDM SE
    "dream router",        # UDR, UDR7
    "cloud gateway",       # UCG, UCG Max, UCG Ultra, UCG Fiber
    "fortress gateway",    # Enterprise Fortress Gateway
    "express",             # UniFi Express
    " udm", " udr", " ucg", # short forms (defensive)
)


def _is_firewall_hw(model: str | None) -> bool:
    if not model:
        return False
    m = " " + model.lower()
    return any(k in m for k in _FIREWALL_HW_KEYWORDS)


def _slug(s: str) -> str:
    out = _SLUG.sub("-", s).strip("-")
    return (out or "site")[:64]


@dataclass
class ImportItem:
    name: str
    site_id: str
    host_id: str | None
    host_name: str | None
    hardware_model: str | None = None
    is_firewall: bool = False


@dataclass
class ImportSummary:
    total_seen: int
    created: int
    skipped_existing: int
    skipped_non_firewall: int
    failed: int
    errors: list[str]


def _strip_host_suffix(host_id: str | None) -> str | None:
    """/ea/sites returns hostId with a ':NNNNN' suffix that /ea/hosts doesn't."""
    if not host_id:
        return None
    return host_id.split(":", 1)[0]


async def _fetch_sites(api_key: str) -> list[ImportItem]:
    headers = {"X-API-KEY": api_key, "Accept": "application/json"}
    items: list[ImportItem] = []

    async with make_client(timeout=15) as client:
        sites_r = await client.get(f"{SITE_MANAGER_BASE}/ea/sites", headers=headers)
        if sites_r.status_code != 200:
            raise RuntimeError(f"sites_http_{sites_r.status_code}: {sites_r.text[:200]}")

        # Map host_id (no suffix) → {name, hardware}
        hosts_by_id: dict[str, dict[str, str | None]] = {}
        try:
            hosts_r = await client.get(f"{SITE_MANAGER_BASE}/ea/hosts", headers=headers)
            if hosts_r.status_code == 200:
                for h in (hosts_r.json().get("data") or []):
                    if not isinstance(h, dict):
                        continue
                    hid = _strip_host_suffix(h.get("id") or h.get("hostId"))
                    rs = h.get("reportedState") or {}
                    name: str | None = None
                    hw_name: str | None = None
                    if isinstance(rs, dict):
                        name = rs.get("name") or rs.get("hostname")
                        hw = rs.get("hardware") or {}
                        if isinstance(hw, dict):
                            hw_name = hw.get("name") or hw.get("shortname")
                            if not name:
                                name = hw_name
                    name = name or h.get("name")
                    if hid:
                        hosts_by_id[hid] = {
                            "name": str(name).strip() if name else None,
                            "hardware": hw_name,
                        }
        except Exception as e:  # noqa: BLE001
            log.warning("hosts fetch failed: %s", e)

        for s in (sites_r.json().get("data") or []):
            if not isinstance(s, dict):
                continue
            site_id = s.get("siteId") or s.get("id")
            if not site_id:
                continue
            raw_host_id = s.get("hostId") or (s.get("host") or {}).get("id")
            host_id = _strip_host_suffix(raw_host_id) if raw_host_id else None
            host_meta = hosts_by_id.get(host_id) if host_id else None
            host_name = host_meta["name"] if host_meta else None
            hardware_model = host_meta["hardware"] if host_meta else None

            meta = s.get("meta") or {}
            stats = s.get("statistics") or {}
            gateway = stats.get("gateway") if isinstance(stats, dict) else {}
            isp = stats.get("ispInfo") if isinstance(stats, dict) else {}
            site_desc = meta.get("desc") if isinstance(meta, dict) else None
            short = (gateway.get("shortname") if isinstance(gateway, dict) else None)
            isp_org = (isp.get("organization") if isinstance(isp, dict) else None)

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
                hardware_model=hardware_model,
                is_firewall=_is_firewall_hw(hardware_model),
            ))
    return items


async def import_all_sites(db: AsyncSession, api_key: str, *, firewalls_only: bool = True) -> ImportSummary:
    summary = ImportSummary(
        total_seen=0, created=0, skipped_existing=0,
        skipped_non_firewall=0, failed=0, errors=[],
    )

    try:
        items = await _fetch_sites(api_key)
    except Exception as e:  # noqa: BLE001
        summary.errors.append(str(e))
        return summary

    summary.total_seen = len(items)

    if firewalls_only:
        before = len(items)
        items = [it for it in items if it.is_firewall]
        summary.skipped_non_firewall = before - len(items)

    existing = set((await db.execute(select(Branch.branch_code))).scalars().all())
    enc_api_key = encrypt(api_key)

    for it in items:
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
                gateway_model=it.hardware_model,
                auth_method="api_key",
                ssl_verify=True,
                polling_interval_seconds=30,
                enabled=True,
                notes=f"Imported from Site Manager (hardware: {it.hardware_model or 'unknown'}, host: {it.host_name or it.host_id or '?'})",
                tags=["imported"],
            )
            db.add(branch)
            await db.flush()
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
    log.info(
        "import: seen=%d firewall_skipped=%d existing_skipped=%d created=%d failed=%d",
        summary.total_seen, summary.skipped_non_firewall, summary.skipped_existing,
        summary.created, summary.failed,
    )
    return summary
