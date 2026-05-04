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
        cdp = await self.ctx.new_cdp_session(self.page)
        await cdp.send("Page.enable")
        await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": SPY_SOURCE})
        url = self.branch.insights_url()
        log.info("[%s] opening %s", self.branch.branch_code, url)
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        except Exception as e:
            log.warning("[%s] navigate warning: %s", self.branch.branch_code, e)

    async def drain_once(self) -> tuple[int, int]:
        """Pull buffered frames out of the page, decode, map, ingest.
        Returns (flow_rows_inserted, threat_rows_inserted)."""
        if self.page is None:
            return 0, 0
        try:
            raw_drain = await self.page.evaluate("(window.__streamerDrain||(()=>[]))()")
        except Exception as e:
            self.stats.drain_errors += 1
            log.warning("[%s] drain failed: %s", self.branch.branch_code, e)
            return 0, 0

        self.stats.last_drain_at = time.time()
        if not raw_drain:
            return 0, 0
        self.stats.drained_messages += len(raw_drain)
        self.stats.last_event_at = time.time()

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
        """True if no data-channel frames have arrived in too long."""
        if not self.stats.last_event_at:
            # Be lenient on a brand-new tab — the WebRTC handshake takes
            # ~5-10s before the first frame arrives.
            return time.time() - self.stats.started_at > 60
        return time.time() - self.stats.last_event_at > settings.tab_silent_timeout_seconds

    async def close(self) -> None:
        if self.page is None:
            return
        try:
            await self.page.close()
        except Exception:
            pass
        self.page = None
