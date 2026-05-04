"""One-shot script: configure NetFlow (IPFIX) export on every cloud-mode
ThreatFlow branch, pointing each UDM at a single collector address.

Driven via Playwright CDP-attach to a Chrome that's already logged in to
ui.com. Walks the same click path as the manual configuration:
  Settings → CyberSecure → Traffic Logging → NetFlow (IPFIX) checkbox →
  Select All networks → Save → fill Collector Address → set Sampling Rate
  → Apply Changes.

Idempotent: skips branches whose Apply Changes button is disabled (=
already in the requested state).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from urllib import error as urlerror
from urllib import request as urlrequest

from playwright.async_api import async_playwright

CDP_URL = os.environ.get("CHROME_CDP_URL", "http://localhost:9222")
API_BASE = os.environ.get("THREATFLOW_API_BASE", "https://threatflow.amspec.group")
COLLECTOR_IP = os.environ.get("IPFIX_COLLECTOR_IP", "51.195.82.50")
COLLECTOR_PORT = os.environ.get("IPFIX_COLLECTOR_PORT", "2055")
SAMPLING_RATE = os.environ.get("IPFIX_SAMPLING_RATE", "2")
SKIP_BRANCH_CODES = set(os.environ.get("IPFIX_SKIP_BRANCH_CODES", "").split(",")) - {""}


def _api(method: str, path: str) -> dict | list:
    token = os.environ.get("THREATFLOW_TOKEN")
    if not token:
        raise SystemExit("Set THREATFLOW_TOKEN env var (admin JWT).")
    req = urlrequest.Request(
        API_BASE.rstrip("/") + path, method=method,
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urlerror.HTTPError as e:
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read()[:200]!r}")


async def configure(page, branch: dict) -> bool:
    """Run the click sequence on one branch's traffic-logging page.
    Returns True on success."""
    code = branch["branch_code"]
    url = branch["controller_url"].rstrip("/") + "/settings/cybersecure/traffic-logging"
    print(f"[{code}] -> {url}")

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
    except Exception as e:
        print(f"[{code}] navigate warning: {e}")

    # Settle for a bit so React renders the form.
    await page.wait_for_timeout(8_000)

    # 1. Click the NetFlow (IPFIX) enable checkbox at its known position
    #    (the page layout is identical across branches).
    await page.mouse.click(557, 127)
    await page.wait_for_timeout(800)

    # 2. The Select Networks dropdown opens automatically. Click "Select All".
    await page.mouse.click(588, 436)
    await page.wait_for_timeout(400)
    # 3. Save the network selection.
    await page.mouse.click(847, 436)
    await page.wait_for_timeout(800)

    # 4. Click the Collector Address field and type the IP.
    await page.mouse.click(718, 374)
    await page.wait_for_timeout(200)
    # Triple-click trick to clear any prior value, then type.
    for _ in range(3):
        await page.mouse.click(718, 374)
        await page.wait_for_timeout(40)
    # Select-all + delete to be sure.
    await page.keyboard.press("Control+a")
    await page.keyboard.press("Delete")
    await page.keyboard.type(COLLECTOR_IP)
    await page.wait_for_timeout(200)

    # 5. Sampling Rate field (default 512). Lower it to 2 for max
    #    coverage (1 isn't allowed; minimum is 2).
    await page.mouse.click(627, 610)
    await page.wait_for_timeout(150)
    for _ in range(3):
        await page.mouse.click(627, 610)
        await page.wait_for_timeout(30)
    await page.keyboard.press("Control+a")
    await page.keyboard.press("Delete")
    await page.keyboard.type(SAMPLING_RATE)
    await page.wait_for_timeout(200)

    # 6. Apply Changes button (bottom left).
    await page.mouse.click(373, 762)
    await page.wait_for_timeout(2_000)
    print(f"[{code}] applied")
    return True


async def main_async(args) -> int:
    res = _api("GET", "/api/branches")
    items = res.get("items", res) if isinstance(res, dict) else res
    branches = [
        b for b in items
        if "unifi.ui.com" in (b.get("controller_url") or "")
        and b.get("enabled", True)
        and b.get("branch_code") not in SKIP_BRANCH_CODES
    ]
    if args.filter:
        branches = [b for b in branches if args.filter.lower() in b["branch_code"].lower()]
    print(f"will configure {len(branches)} branch(es)")

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            print("Chrome has no open windows; aborting", file=sys.stderr)
            return 2
        ctx = browser.contexts[0]
        page = await ctx.new_page()

        ok = 0
        fail = 0
        for b in branches:
            try:
                if await configure(page, b):
                    ok += 1
                else:
                    fail += 1
            except Exception as e:
                fail += 1
                print(f"[{b['branch_code']}] FAILED: {e}")
            # Tiny pause between branches so the UDM has a chance to push
            # the previous config before we navigate away.
            await page.wait_for_timeout(2_000)

        print(f"done: ok={ok} fail={fail}")
        await page.close()
        await browser.close()
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--filter", help="only configure branches whose code contains this substring")
    raise SystemExit(asyncio.run(main_async(p.parse_args())))
