"""Streamer entry point.

  1. Launch (or attach to) a persistent Chromium profile via Playwright.
  2. Verify ui.com session is alive; programmatic-login if not (fails on MFA).
  3. Pull the list of cloud-mode branches from Postgres.
  4. Open one tab per branch, hook the WebRTC data channel.
  5. Loop: every drain_seconds, drain each tab + ingest. Restart silent tabs.
"""
from __future__ import annotations

import asyncio
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


async def _ensure_logged_in(ctx: BrowserContext) -> bool:
    page = await ctx.new_page()
    try:
        if await auth.is_logged_in(page):
            log.info("ui.com session already valid (cookies persisted)")
            return True
        if not (settings.ui_email and settings.ui_password):
            log.error("UI_EMAIL / UI_PASSWORD not set; cannot bootstrap login. "
                      "Provide them via env, OR pre-bake cookies into the volume "
                      "with STREAMER_BOOTSTRAP_ONLY=true STREAMER_HEADLESS=false.")
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
    while not stop.is_set():
        await asyncio.sleep(1.0)
        now = time.time()
        if now >= next_drain:
            next_drain = now + settings.drain_seconds
            # Drain all tabs in parallel; each ingests on its own thread.
            await asyncio.gather(*(t.drain_once() for t in tabs), return_exceptions=True)
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
            await _supervisor_loop(tabs, stop)
        finally:
            try: await ctx.close()
            except Exception: pass
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
