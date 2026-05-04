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
        ctx = browser.contexts[0]
        cookies = await ctx.cookies()
        kept = [c for c in cookies if any(d in c.get("domain", "") for d in RELEVANT_DOMAINS)]

        # Dump localStorage for the unifi.ui.com / account.ui.com origins too.
        # AWS Cognito Identity Pool stashes its identity ID + temporary
        # creds in localStorage on the unifi.ui.com origin, and without it
        # AWS IoT will reject PUBLISH with "Device not linked".
        local_storage: dict[str, dict[str, str]] = {}
        for page in ctx.pages:
            url = page.url or ""
            origin = ""
            for h in ("unifi.ui.com", "account.ui.com", "sso.ui.com"):
                if h in url:
                    origin = "https://" + h
                    break
            if not origin:
                continue
            try:
                items = await page.evaluate(
                    "Array.from({length: localStorage.length}, (_, i) => "
                    "  [localStorage.key(i), localStorage.getItem(localStorage.key(i))])"
                )
                if items:
                    local_storage.setdefault(origin, {})
                    for k, v in items:
                        local_storage[origin][k] = v
            except Exception as e:
                print(f"  could not read localStorage on {url[:60]}: {e}", file=sys.stderr)

        payload = {"cookies": kept, "local_storage": local_storage}
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        await browser.close()
    print(f"wrote {len(kept)} cookie(s) + localStorage from {len(local_storage)} origin(s) to {out_path}")
    print("\nNext steps:")
    print(f"  scp {out_path} ubuntu@51.195.82.50:/tmp/")
    print('  ssh ubuntu@51.195.82.50 \'docker compose -f /home/ubuntu/threatflow/docker-compose.yml stop streamer && \\')
    print('     docker run --rm -v threatflow_streamer_profile:/dst -v /tmp:/src alpine \\')
    print('       sh -c "cp /src/ui-cookies.json /dst/chrome-profile/ui-cookies.json && \\')
    print('              chown 1000:1000 /dst/chrome-profile/ui-cookies.json" && \\')
    print('     docker compose -f /home/ubuntu/threatflow/docker-compose.yml up -d streamer\'')
    return 0


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "ui-cookies.json")
    raise SystemExit(asyncio.run(main(out)))
