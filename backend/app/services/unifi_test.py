"""Connection-test + site-discovery service.

In MOCK_DATA mode this returns canned successful responses so the UI is fully
exercisable. Phase 4 will wire real httpx-based UniFi probing here.
"""
import asyncio
import time
from typing import Any

from app.config import settings
from app.models.branch import Branch
from app.schemas.branch import TestConnectionResult


async def test_connection(branch: Branch, *, plaintext_creds: dict[str, Any] | None = None) -> TestConnectionResult:
    started = time.perf_counter()

    if settings.mock_data:
        # Pretend we hit /proxy/network/v2/api/site/{site_id}/traffic-flows successfully
        await asyncio.sleep(0.25)
        return TestConnectionResult(
            ok=True,
            endpoint_used=f"/proxy/network/v2/api/site/{branch.site_id}/traffic-flows",
            unifi_os_version="9.0.114 (mock)",
            network_app_version="9.0.114 (mock)",
            sites_discovered=[branch.site_id, "default"] if branch.site_id != "default" else ["default"],
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_mock=True,
        )

    # Real probe lands in Phase 4. For now report "not implemented" cleanly.
    return TestConnectionResult(
        ok=False,
        endpoint_used=None,
        duration_ms=int((time.perf_counter() - started) * 1000),
        error="Real UniFi probing arrives in Phase 4. Toggle MOCK_DATA=true for now.",
    )


async def discover_sites(branch: Branch, *, plaintext_creds: dict[str, Any] | None = None) -> TestConnectionResult:
    """Same shape as test_connection — discover_sites is just a richer probe."""
    return await test_connection(branch, plaintext_creds=plaintext_creds)
