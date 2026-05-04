"""Streamer entry point.

  1. Launch (or attach to) a persistent Chromium profile via Playwright.
  2. Verify ui.com session is alive; programmatic-login if not (fails on MFA).
  3. Pull the list of cloud-mode branches from Postgres.
  4. Open one tab per branch, hook the WebRTC data channel.
  5. Loop: every drain_seconds, drain each tab + ingest. Restart silent tabs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time

from playwright.async_api import BrowserContext, async_playwright

from app import auth, branches as branches_mod
from app.config import settings
from app.tab import BranchTab

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("streamer.main")

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    # We don't need media devices for data-channel-only WebRTC, but Chrome
    # is fussier about WebRTC without these:
    "--use-fake-ui-for-media-stream",
    "--autoplay-policy=no-user-gesture-required",
]


async def _import_cookies_if_present(ctx: BrowserContext) -> int:
    """If ui-cookies.json was dropped into the profile volume by the
    operator, load + add it to the context. Returns the number imported."""
    p = os.path.join(settings.profile_dir, "ui-cookies.json")
    if not os.path.exists(p):
        return 0
    try:
        with open(p, encoding="utf-8") as f:
            cookies = json.load(f)
        if not isinstance(cookies, list) or not cookies:
            return 0
        # Playwright requires either url or (domain + path); coerce the
        # exporter's shape if needed and drop fields it rejects.
        cleaned = []
        for c in cookies:
            cc = {k: v for k, v in c.items() if k in (
                "name", "value", "domain", "path", "expires", "httpOnly",
                "secure", "sameSite", "url",
            )}
            if "sameSite" in cc and cc["sameSite"] not in ("Strict", "Lax", "None"):
                cc.pop("sameSite", None)
            cleaned.append(cc)
        await ctx.add_cookies(cleaned)
        log.info("imported %d cookie(s) from %s", len(cleaned), p)
        # Cookies import is idempotent (add_cookies overwrites by
        # name+domain), so we leave the file in place. On subsequent
        # restarts we re-import which is harmless and protects against a
        # corrupted persistent profile.
        return len(cleaned)
    except Exception as e:
        log.error("cookie import failed: %s", e)
        return 0


async def _ensure_logged_in(ctx: BrowserContext) -> bool:
    await _import_cookies_if_present(ctx)
    page = await ctx.new_page()
    try:
        if await auth.is_logged_in(page):
            log.info("ui.com session already valid")
            return True
        if not (settings.ui_email and settings.ui_password):
            log.error("ui.com session not valid AND UI_EMAIL / UI_PASSWORD not set. "
                      "Drop ui-cookies.json into the streamer_profile volume "
                      "(see tools/cloudproxy_capture/export_session.py) "
                      "OR set UI_EMAIL+UI_PASSWORD in .env.")
            return False
        return await auth.login(page, settings.ui_email, settings.ui_password)
    finally:
        await page.close()


async def _open_tabs(ctx: BrowserContext) -> list[BranchTab]:
    all_branches = await branches_mod.fetch_cloud_branches()
    streamable = branches_mod.filter_streamable(all_branches)
    if len(streamable) > settings.max_tabs:
        log.warning(
            "%d streamable branches but max_tabs=%d; capping",
            len(streamable), settings.max_tabs,
        )
        streamable = streamable[: settings.max_tabs]
    log.info("opening %d branch tab(s)", len(streamable))
    tabs: list[BranchTab] = []
    for b in streamable:
        t = BranchTab(ctx, b)
        await t.open()
        tabs.append(t)
        # Stagger opens so 55 simultaneous WebRTC handshakes don't drown
        # the network or the Cloudflare TURN service.
        await asyncio.sleep(1.0)
    return tabs


async def _supervisor_loop(tabs: list[BranchTab], stop: asyncio.Event) -> None:
    """Periodic drain + restart of silent tabs."""
    next_drain = time.time() + settings.drain_seconds
    next_stats = time.time() + 60
    while not stop.is_set():
        await asyncio.sleep(1.0)
        now = time.time()
        if now >= next_drain:
            next_drain = now + settings.drain_seconds
            # Drain all tabs in parallel; each ingests on its own thread.
            await asyncio.gather(*(t.drain_once() for t in tabs), return_exceptions=True)
        if now >= next_stats:
            next_stats = now + 60
            alive = sum(1 for t in tabs if t.stats.last_event_at)
            with_events = sum(1 for t in tabs if t.stats.drained_messages > 0)
            total_threats = sum(t.stats.rows_threat for t in tabs)
            total_flows = sum(t.stats.rows_flow for t in tabs)
            top_active = sorted(tabs, key=lambda t: -t.stats.drained_messages)[:5]
            log.info(
                "stats: %d/%d tabs receiving WS, %d/%d ever-drained-events, "
                "lifetime: flows=%d threats=%d. top: %s",
                alive, len(tabs), with_events, len(tabs),
                total_flows, total_threats,
                ", ".join(f"{t.branch.branch_code}={t.stats.drained_messages}"
                          for t in top_active),
            )
        # Cheap silent-tab check on the same tick: pick one tab per pass.
        # Avoids stampeding restarts if many tabs go silent at once.
        for t in tabs:
            if await t.is_silent():
                log.warning("[%s] silent for too long, reloading tab", t.branch.branch_code)
                try:
                    await t.close()
                    await t.open()
                    t.stats.started_at = time.time()
                    t.stats.last_event_at = 0.0
                except Exception as e:
                    log.error("[%s] reload failed: %s", t.branch.branch_code, e)
                break  # only one restart per loop iteration


async def main_async() -> int:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass  # windows

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            settings.profile_dir,
            headless=settings.headless,
            args=CHROMIUM_ARGS,
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=False,
        )
        try:
            ok = await _ensure_logged_in(ctx)
            if not ok:
                if settings.bootstrap_only:
                    log.info("bootstrap mode: leaving Chrome open for manual login. "
                             "Complete login in the visible browser, then stop the container.")
                    await stop.wait()
                else:
                    log.error("not logged in to ui.com and cannot bootstrap; exiting")
                    return 2
                return 0
            if settings.bootstrap_only:
                log.info("bootstrap-only: cookies are persisted; exiting")
                return 0

            tabs = await _open_tabs(ctx)
            log.info("supervisor running; %d tab(s) live", len(tabs))
            # One-shot diagnostic on a single tab so we can confirm the
            # page actually rendered + the spy is in place. If it isn't,
            # opening 54 more tabs is just multiplying the same bug.
            if tabs:
                await asyncio.sleep(20)
                diag = await tabs[0].diagnose()
                log.info("first-tab diagnostic: %s", diag)
            await _supervisor_loop(tabs, stop)
        finally:
            try: await ctx.close()
            except Exception: pass
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
