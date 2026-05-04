"""Export ui.com session cookies from the user's running Chrome.

Run this LOCALLY against your normal logged-in Chrome (started with
--remote-debugging-port=9222 and --user-data-dir=C:\\chrome-debug-profile).
SCP the resulting `ui-cookies.json` to the VPS streamer profile, then
restart the streamer.

Usage:
  python export_session.py [output-path]

Default output: tools/cloudproxy_capture/ui-cookies.json
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

CDP_URL = "http://localhost:9222"
RELEVANT_DOMAINS = (".ui.com", ".ubnt.com", ".ui.direct")


async def main(out_path: Path) -> int:
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"FAILED to attach to Chrome at {CDP_URL}: {e}", file=sys.stderr)
            print("Start Chrome with --remote-debugging-port=9222.", file=sys.stderr)
            return 2
        if not browser.contexts:
            print("Chrome has no windows open.", file=sys.stderr)
            return 2
        cookies = await browser.contexts[0].cookies()
        kept = [
            c for c in cookies
            if any(d in c.get("domain", "") for d in RELEVANT_DOMAINS)
        ]
        out_path.write_text(json.dumps(kept, indent=2), encoding="utf-8")
        await browser.close()
    print(f"wrote {len(kept)} cookie(s) to {out_path}")
    print("\nNext steps:")
    print(f"  scp {out_path} ubuntu@51.195.82.50:/tmp/")
    print('  ssh ubuntu@51.195.82.50 \'docker compose -f /home/ubuntu/threatflow/docker-compose.yml stop streamer && \\')
    print('     docker run --rm -v threatflow_streamer_profile:/dst -v /tmp:/src alpine \\')
    print('       cp /src/ui-cookies.json /dst/ui-cookies.json && \\')
    print('     docker compose -f /home/ubuntu/threatflow/docker-compose.yml up -d streamer\'')
    return 0


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "ui-cookies.json")
    raise SystemExit(asyncio.run(main(out)))
