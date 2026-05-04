"""One BranchTab = one Chrome tab, one console URL, one streaming session."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field

from playwright.async_api import BrowserContext, Page

from app import ingest
from app.branches import Branch
from app.chunk_parser import ChunkParser
from app.config import settings
from app.mapper import map_event
from app.spy import SPY_SOURCE

log = logging.getLogger("streamer.tab")


@dataclass
class TabStats:
    branch_code: str
    started_at: float = field(default_factory=time.time)
    last_event_at: float = 0.0
    last_drain_at: float = 0.0
    drained_messages: int = 0
    decoded_chunks: int = 0
    rows_flow: int = 0
    rows_threat: int = 0
    drain_errors: int = 0
    ingest_errors: int = 0


class BranchTab:
    def __init__(self, ctx: BrowserContext, branch: Branch) -> None:
        self.ctx = ctx
        self.branch = branch
        self.page: Page | None = None
        self.stats = TabStats(branch_code=branch.branch_code)
        self._parsers: dict[str, ChunkParser] = {}

    async def open(self) -> None:
        self.page = await self.ctx.new_page()
        # Capture page-side errors so we can see what's blocking the WebRTC
        # / MQTT handshake. Limited to a few lines per tab to avoid log spam.
        self._page_errors: list[str] = []
        self.page.on("pageerror", lambda e: self._page_errors.append(f"pageerror: {str(e)[:200]}"))
        self.page.on("console", lambda m: (
            self._page_errors.append(f"console.{m.type}: {m.text[:200]}")
            if m.type in ("error", "warning") and len(self._page_errors) < 30
            else None
        ))
        cdp = await self.ctx.new_cdp_session(self.page)
        await cdp.send("Page.enable")
        await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": SPY_SOURCE})
        # Two-step navigation: first land on the Site Manager root so the
        # account/device linking calls run in the normal order. Skipping
        # straight to /insights/flows leaves the device "unlinked" from the
        # IoT MQTT topic — AWS replies with `Device not linked` and the
        # WebRTC offer never gets answered.
        try:
            await self.page.goto("https://unifi.ui.com/", wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(3)
        except Exception as e:
            log.warning("[%s] warmup nav: %s", self.branch.branch_code, e)
        url = self.branch.insights_url()
        log.info("[%s] opening %s", self.branch.branch_code, url)
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        except Exception as e:
            log.warning("[%s] navigate warning: %s", self.branch.branch_code, e)

    def page_errors(self) -> list[str]:
        return list(getattr(self, "_page_errors", []))[:20]

    async def diagnose(self) -> dict:
        """One-time post-navigation diagnostic. Returns observable state
        about whether the spy is in place + whether the page loaded."""
        if self.page is None:
            return {"error": "no page"}
        try:
            return await self.page.evaluate(
                "({"
                "url: location.href.slice(0,200),"
                "title: document.title.slice(0,80),"
                "spy_installed: !!window.__streamer,"
                "any_count: (window.__streamer&&window.__streamer.any_count)||0,"
                "buffered: (window.__streamer&&window.__streamer.dc.length)||0,"
                "ws_opens: (window.__streamer&&window.__streamer.ws_opens)||[],"
                "pc_states: (window.__streamer&&window.__streamer.pc_states)||[],"
                "rtcpc: typeof RTCPeerConnection,"
                "ua: navigator.userAgent.slice(0,140),"
                "webdriver: navigator.webdriver"
                "})"
            )
        except Exception as e:
            return {"error": str(e)}

    async def drain_once(self) -> tuple[int, int]:
        """Pull buffered frames out of the page, decode, map, ingest.
        Returns (flow_rows_inserted, threat_rows_inserted)."""
        if self.page is None:
            return 0, 0
        try:
            raw_drain, last_seen, any_count = await self.page.evaluate(
                "[(window.__streamerDrain||(()=>[]))(),"
                " (window.__streamer&&window.__streamer.last_seen)||0,"
                " (window.__streamer&&window.__streamer.any_count)||0]"
            )
        except Exception as e:
            self.stats.drain_errors += 1
            log.warning("[%s] drain failed: %s", self.branch.branch_code, e)
            return 0, 0

        self.stats.last_drain_at = time.time()
        # last_event_at = JS-side last frame on any ws:/… channel, in ms.
        # Treat it as our liveness proxy — we want a quiet branch to stay
        # alive so long as the WebRTC peer is healthy.
        if last_seen:
            self.stats.last_event_at = last_seen / 1000.0
        if not raw_drain:
            return 0, 0
        self.stats.drained_messages += len(raw_drain)

        # Group frames by channel label so each ChunkParser only sees its
        # own stream (logical msgs span DC frames per-channel).
        grouped: dict[str, list[bytes]] = {}
        for frame in raw_drain:
            label = frame.get("label", "")
            if not label.startswith("ws:/proxy/network/wss/s/"):
                continue
            try:
                grouped.setdefault(label, []).append(base64.b64decode(frame["sample"]))
            except Exception:
                continue

        decoded: list[dict] = []
        for label, blocks in grouped.items():
            parser = self._parsers.setdefault(label, ChunkParser())
            for b in blocks:
                for obj in parser.feed(b):
                    decoded.append(obj)
        self.stats.decoded_chunks += len(decoded)

        # Filter for `events` payloads (the IDS/IPS/firewall stream).
        unifi_events: list[dict] = []
        for obj in decoded:
            meta = obj.get("meta") or {}
            if meta.get("message") != "events":
                continue
            data = obj.get("data") or []
            if isinstance(data, list):
                unifi_events.extend(d for d in data if isinstance(d, dict))

        if not unifi_events:
            return 0, 0

        flows: list[dict] = []
        threats: list[dict] = []
        for ev in unifi_events:
            f, t = map_event(
                ev,
                branch_id=self.branch.id,
                branch_name=self.branch.name,
                branch_code=self.branch.branch_code,
                collector_version="streamer/0.1",
            )
            flows.extend(f)
            threats.extend(t)

        if not flows and not threats:
            return 0, 0

        try:
            fi, ti = await asyncio.to_thread(
                ingest.post_batch, self.branch.id, flows, threats,
            )
            self.stats.rows_flow += fi
            self.stats.rows_threat += ti
            keys = Counter(ev.get("key", "") for ev in unifi_events)
            log.info(
                "[%s] drained=%d events=%d flows=%d threats=%d keys=%s",
                self.branch.branch_code, len(raw_drain), len(unifi_events),
                fi, ti, dict(keys.most_common(3)),
            )
            return fi, ti
        except Exception as e:
            self.stats.ingest_errors += 1
            log.warning("[%s] ingest failed: %s", self.branch.branch_code, e)
            return 0, 0

    async def is_silent(self) -> bool:
        """True if no data-channel frames have arrived in too long.
        Liveness counts *any* WS-tunnelled frame (dashboard:sync,
        client:sync, events, ...) — not just security events — so quiet
        branches with healthy WebRTC peers don't get false-positive
        reloaded. The new-tab grace matches the silent-timeout to handle
        slow handshakes."""
        deadline = settings.tab_silent_timeout_seconds
        if not self.stats.last_event_at:
            return time.time() - self.stats.started_at > deadline
        return time.time() - self.stats.last_event_at > deadline

    async def close(self) -> None:
        if self.page is None:
            return
        try:
            await self.page.close()
        except Exception:
            pass
        self.page = None
