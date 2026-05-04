"""Continuous multi-tab cloud-proxy capture from the user's normal Chrome.

This is the working replacement for the VPS-side streamer service. The VPS
streamer hits "Device not linked" errors from AWS IoT because its Cognito
identity differs from the user's real Chrome session. Running here against
the user's actual Chrome via CDP-attach uses the same identity that already
has all 55 devices linked.

Trade-off: requires the user's Windows PC to be awake with Chrome running
in debug mode. Acceptable until/unless the device-link flow is reverse-
engineered for the VPS path.

Setup
-----
1. Close every Chrome window (Task Manager → end every chrome.exe).
2. Start Chrome with the debugger port + a separate profile dir:

       "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ^
           --remote-debugging-port=9222 ^
           --user-data-dir=C:\\chrome-debug-profile ^
           https://unifi.ui.com

3. Log in to ui.com once (handle MFA).
4. Get an admin JWT for ThreatFlow:
       curl -s -i -X POST https://threatflow.amspec.group/api/auth/login ^
            -H "Content-Type: application/json" ^
            -d "{\"email\":\"<admin>\",\"password\":\"<pwd>\"}" | findstr threatflow_session

   Copy the cookie value into the THREATFLOW_TOKEN env var.

5. Run the streamer:

       cd tools\\local_streamer
       pip install -r requirements.txt
       set THREATFLOW_TOKEN=<jwt>
       python local_streamer.py
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

# Reuse the proven decoder + mapper from the streamer package by adding
# its parent dir to sys.path. We don't want to duplicate the logic.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "streamer"))
from app.chunk_parser import ChunkParser  # noqa: E402
from app.mapper import map_event  # noqa: E402
from app.spy import SPY_SOURCE  # noqa: E402

from playwright.async_api import async_playwright

CDP_URL = os.environ.get("CHROME_CDP_URL", "http://localhost:9222")
API_BASE = os.environ.get("THREATFLOW_API_BASE", "https://threatflow.amspec.group")
DRAIN_SECONDS = int(os.environ.get("STREAMER_DRAIN_SECONDS", "30"))
TAB_STAGGER = float(os.environ.get("STREAMER_TAB_STAGGER", "6.0"))
MAX_TABS = int(os.environ.get("STREAMER_MAX_TABS", "55"))
BRANCH_FILTER = os.environ.get("STREAMER_BRANCH_FILTER", "").lower()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s :: %(message)s",
)
log = logging.getLogger("local_streamer")


def _api(method: str, path: str, body: dict | None = None) -> dict:
    """Authenticated JSON request to the ThreatFlow backend."""
    token = os.environ.get("THREATFLOW_TOKEN")
    if not token:
        raise SystemExit("set THREATFLOW_TOKEN env var (admin JWT)")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urlrequest.Request(
        API_BASE.rstrip("/") + path,
        data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urlerror.HTTPError as e:
        body = e.read()[:300] if hasattr(e, "read") else b""
        raise SystemExit(f"{method} {path} -> {e.code}: {body!r}")


def _serialize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        clean: dict = {}
        for k, v in r.items():
            if isinstance(v, datetime):
                if v.tzinfo is None:
                    v = v.replace(tzinfo=timezone.utc)
                clean[k] = v.isoformat()
            else:
                clean[k] = v
        out.append(clean)
    return out


def _ingest(branch_id: str, flows: list[dict], threats: list[dict]) -> tuple[int, int]:
    if not flows and not threats:
        return 0, 0
    res = _api("POST", "/api/admin/ingest/cloudproxy", {
        "branch_id":   branch_id,
        "flow_rows":   _serialize(flows),
        "threat_rows": _serialize(threats),
    })
    return int(res.get("flows_inserted", 0)), int(res.get("threats_inserted", 0))


class BranchTab:
    """One open tab in the user's Chrome, hooked + draining periodically."""

    def __init__(self, ctx, branch: dict) -> None:
        self.ctx = ctx
        self.branch = branch
        self.page = None
        self.parsers: dict[str, ChunkParser] = {}
        self.last_seen = 0.0
        self.started_at = time.time()
        self.events_total = 0
        self.flows_total = 0
        self.threats_total = 0

    def insights_url(self) -> str:
        u = (self.branch["controller_url"] or "").strip().rstrip("/")
        return f"{u}/insights/flows"

    async def open(self) -> None:
        self.page = await self.ctx.new_page()
        cdp = await self.ctx.new_cdp_session(self.page)
        await cdp.send("Page.enable")
        await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": SPY_SOURCE})
        url = self.insights_url()
        log.info("[%s] opening %s", self.branch["branch_code"], url)
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        except Exception as e:
            log.warning("[%s] navigate warning: %s", self.branch["branch_code"], e)

    async def drain(self) -> None:
        if self.page is None:
            return
        try:
            raw, last_seen, _ = await self.page.evaluate(
                "[(window.__streamerDrain||(()=>[]))(),"
                " (window.__streamer&&window.__streamer.last_seen)||0,"
                " (window.__streamer&&window.__streamer.any_count)||0]"
            )
        except Exception as e:
            log.warning("[%s] drain failed: %s", self.branch["branch_code"], e)
            return
        if last_seen:
            self.last_seen = last_seen / 1000.0
        if not raw:
            return

        # Group raw frames by channel label so each parser keeps its own
        # state (logical chunks span multiple data-channel frames).
        grouped: dict[str, list[bytes]] = {}
        for frame in raw:
            label = frame.get("label", "")
            if not label.startswith("ws:/proxy/network/wss/s/"):
                continue
            try:
                grouped.setdefault(label, []).append(base64.b64decode(frame["sample"]))
            except Exception:
                continue
        decoded: list[dict] = []
        for label, blocks in grouped.items():
            parser = self.parsers.setdefault(label, ChunkParser())
            for b in blocks:
                for obj in parser.feed(b):
                    decoded.append(obj)

        unifi_events: list[dict] = []
        for obj in decoded:
            meta = obj.get("meta") or {}
            if meta.get("message") != "events":
                continue
            data = obj.get("data") or []
            if isinstance(data, list):
                unifi_events.extend(d for d in data if isinstance(d, dict))
        if not unifi_events:
            return

        flows, threats = [], []
        for ev in unifi_events:
            f, t = map_event(
                ev,
                branch_id=self.branch["id"],
                branch_name=self.branch["name"],
                branch_code=self.branch["branch_code"],
                collector_version="local_streamer/0.1",
            )
            flows.extend(f)
            threats.extend(t)

        self.events_total += len(unifi_events)
        try:
            fi, ti = await asyncio.to_thread(_ingest, self.branch["id"], flows, threats)
            self.flows_total += fi
            self.threats_total += ti
            log.info(
                "[%s] events=%d flows=%d threats=%d (lifetime: events=%d flows=%d threats=%d)",
                self.branch["branch_code"], len(unifi_events), fi, ti,
                self.events_total, self.flows_total, self.threats_total,
            )
        except Exception as e:
            log.warning("[%s] ingest failed: %s", self.branch["branch_code"], e)


async def fetch_branches() -> list[dict]:
    """Get the list of cloud-mode branches from ThreatFlow's branches API."""
    res = _api("GET", "/api/branches")
    items = res.get("items", res) if isinstance(res, dict) else res
    branches = [
        b for b in items
        if "unifi.ui.com" in (b.get("controller_url") or "")
        and b.get("enabled", True)
    ]
    if BRANCH_FILTER:
        branches = [b for b in branches if BRANCH_FILTER in (b.get("branch_code") or "").lower()]
    return branches[:MAX_TABS]


async def main_async() -> int:
    branches = await fetch_branches()
    log.info("opening %d branch tab(s) in your Chrome (stagger=%ss, drain=%ss)",
             len(branches), TAB_STAGGER, DRAIN_SECONDS)

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            log.error("Could not attach to Chrome at %s: %s", CDP_URL, e)
            log.error("Start Chrome with --remote-debugging-port=9222")
            return 2
        if not browser.contexts:
            log.error("Chrome has no windows open. Open one and re-run.")
            return 2
        ctx = browser.contexts[0]

        tabs: list[BranchTab] = []
        for b in branches:
            tab = BranchTab(ctx, b)
            await tab.open()
            tabs.append(tab)
            await asyncio.sleep(TAB_STAGGER)

        log.info("supervisor running; %d tab(s) live", len(tabs))
        next_drain = time.time() + DRAIN_SECONDS
        next_stats = time.time() + 60
        while True:
            await asyncio.sleep(1.0)
            now = time.time()
            if now >= next_drain:
                next_drain = now + DRAIN_SECONDS
                await asyncio.gather(*(t.drain() for t in tabs), return_exceptions=True)
            if now >= next_stats:
                next_stats = now + 60
                alive = sum(1 for t in tabs if t.last_seen)
                tot_flows = sum(t.flows_total for t in tabs)
                tot_threats = sum(t.threats_total for t in tabs)
                log.info("stats: %d/%d tabs alive, lifetime ingested: flows=%d threats=%d",
                         alive, len(tabs), tot_flows, tot_threats)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--filter", help="branch_code substring filter (overrides env)")
    args = p.parse_args()
    global BRANCH_FILTER
    if args.filter:
        BRANCH_FILTER = args.filter.lower()
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
