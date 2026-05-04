"""POC: capture WebSocket frames from unifi.ui.com via Playwright CDP-attach.

What it does
------------
Attaches to a Chrome instance you already have running (so your existing
ui.com login is reused — no re-auth, no MFA replay). Opens a new tab in your
profile, navigates to the console URL you pass, and listens for every
WebSocket created during page bootstrap. For each WS it logs the handshake
URL plus the first N frames in each direction, decoding as UTF-8 when
possible (most UniFi frames are JSON) and falling back to base64 otherwise.

Usage
-----
1. Close every Chrome window. Check Task Manager → Background processes →
   kill any lingering `chrome.exe` (Chrome runs background tasks even when
   no window is visible). Important: a debugger-port flag is ignored if a
   normal Chrome is already attached to the same profile.

2. Start Chrome with the debugger port (this reuses your normal profile so
   your ui.com session stays logged in):

       "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222

   Verify by opening http://localhost:9222/json/version in any tab — it
   should return JSON describing your Chrome.

3. Make sure you're still logged in to https://unifi.ui.com.

4. Install + run this POC:

       cd C:\\UniFi-ThreatFlow-Hub\\tools\\cloudproxy_poc
       pip install -r requirements.txt
       python poc.py <console-url>

   Example console-url:
   https://unifi.ui.com/consoles/0CEA141A19B100000000085700810000000008C87B2A0000000066F0272E:659718018/network/default/dashboard

   Pick a console you know is healthy (avoid ones whose tunnel was 503
   in earlier probes).

5. Output:
   - stdout: live summary as frames arrive
   - frames.jsonl: one line per frame in JSON for analysis
   - summary.json: counts + handshake URLs + first 5 frames each direction
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
from pathlib import Path

from playwright.async_api import Playwright, async_playwright

CDP_URL = "http://localhost:9222"
CAPTURE_SECONDS = 30
MAX_FRAMES_PER_WS = 200  # cap so a chatty WS doesn't blow up the file
FRAMES_FILE = Path(__file__).parent / "frames.jsonl"
SUMMARY_FILE = Path(__file__).parent / "summary.json"


def _decode(payload) -> tuple[str, str]:
    """Best-effort: try UTF-8, fall back to base64. Returns (encoding, text)."""
    if isinstance(payload, str):
        return ("utf-8", payload)
    if isinstance(payload, (bytes, bytearray)):
        try:
            return ("utf-8", payload.decode("utf-8"))
        except UnicodeDecodeError:
            return ("base64", base64.b64encode(payload).decode("ascii"))
    return ("repr", repr(payload))


async def main(console_url: str) -> int:
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"FAILED to attach to Chrome at {CDP_URL}: {e}", file=sys.stderr)
            print("Did you start Chrome with --remote-debugging-port=9222?", file=sys.stderr)
            return 2

        if not browser.contexts:
            print("Chrome has no contexts (windows). Open at least one window.", file=sys.stderr)
            return 2
        ctx = browser.contexts[0]
        page = await ctx.new_page()

        sockets: list[dict] = []
        frames_log: list[dict] = []
        FRAMES_FILE.write_text("")  # truncate

        def on_websocket(ws):
            entry = {
                "url": ws.url,
                "opened_at": time.time(),
                "in_count": 0,
                "out_count": 0,
                "first_in": [],
                "first_out": [],
            }
            sockets.append(entry)
            print(f"[ws-open] {ws.url}", flush=True)

            def log(direction: str, payload):
                enc, text = _decode(payload)
                size = len(text) if enc == "utf-8" else len(payload) if hasattr(payload, "__len__") else 0
                rec = {
                    "ts": time.time(),
                    "ws": ws.url,
                    "dir": direction,
                    "encoding": enc,
                    "size": size,
                    "payload": text[:8000],  # cap each frame
                }
                with FRAMES_FILE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec) + "\n")
                if direction == "in":
                    entry["in_count"] += 1
                    if len(entry["first_in"]) < 5:
                        entry["first_in"].append(rec)
                else:
                    entry["out_count"] += 1
                    if len(entry["first_out"]) < 5:
                        entry["first_out"].append(rec)
                if (entry["in_count"] + entry["out_count"]) <= 8:
                    preview = text.replace("\n", " ")[:120]
                    print(f"  [{direction}] {size:>5d}b  {preview}", flush=True)

            ws.on("framereceived", lambda payload: log("in", payload))
            ws.on("framesent",     lambda payload: log("out", payload))
            ws.on("close",         lambda: print(f"[ws-close] {ws.url}", flush=True))

        page.on("websocket", on_websocket)

        print(f"navigating to {console_url}", flush=True)
        try:
            await page.goto(console_url, wait_until="domcontentloaded", timeout=20_000)
        except Exception as e:
            print(f"navigate warning (continuing): {e}", flush=True)

        print(f"capturing for {CAPTURE_SECONDS}s …", flush=True)
        await asyncio.sleep(CAPTURE_SECONDS)

        # Don't close the user's tab; just close our page.
        await page.close()
        await browser.close()

        summary = {
            "console_url": console_url,
            "captured_seconds": CAPTURE_SECONDS,
            "websockets": sockets,
        }
        SUMMARY_FILE.write_text(json.dumps(summary, indent=2, default=str))
        total_frames = sum(s["in_count"] + s["out_count"] for s in sockets)
        print(f"\ndone. {len(sockets)} websocket(s), {total_frames} frame(s)", flush=True)
        print(f"  frames → {FRAMES_FILE}")
        print(f"  summary → {SUMMARY_FILE}")
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python poc.py <console-url>", file=sys.stderr)
        sys.exit(1)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
