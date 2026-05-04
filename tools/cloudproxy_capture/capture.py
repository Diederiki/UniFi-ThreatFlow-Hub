"""Capture UniFi cloud-proxy events from one console + ingest into ThreatFlow.

Pipeline (per run):
  1. Attach to a Chrome instance running with --remote-debugging-port=9222.
     The Chrome session's ui.com login cookies are reused so we don't need
     to replay SSO server-side.
  2. Open the console URL provided. Insights/Flows is the recommended path
     because it auto-subscribes to threat + firewall events.
  3. Hook RTCDataChannel.message via Page.addScriptToEvaluateOnNewDocument
     before any page JS runs. Capture all binary frames on the
     `wss/s/<site>/events` channel for `--seconds`.
  4. Reassemble + zlib-decompress chunks, keep only `meta.message='events'`
     payloads.
  5. Map each event to raw_flow_events / raw_threat_events row(s).
  6. POST the batch to /api/admin/ingest/cloudproxy.

Usage:
  cd tools/cloudproxy_capture
  pip install -r requirements.txt
  set THREATFLOW_TOKEN=<admin-jwt>
  python capture.py --branch-id <uuid> --console-url "<url>" --seconds 60
                    [--api-base https://threatflow.amspec.group]
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import struct
import sys
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from mapper import map_events  # noqa: E402

CDP_URL = "http://localhost:9222"
EVENTS_LABEL_PREFIX = "ws:/proxy/network/wss/s/"
SPY_SOURCE = r"""
(() => {
  if (window.__pocSpy) return;
  window.__pocSpy = { dc: [], installed_at: Date.now() };
  if (typeof RTCPeerConnection === 'undefined') return;
  const proto = RTCPeerConnection.prototype;
  function hookDC(dc, why) {
    window.__pocSpy.dc.push({ ts: Date.now(), kind: why, label: dc.label });
    dc.addEventListener('message', (ev) => {
      if (!(ev.data instanceof ArrayBuffer)) return;
      if (!String(dc.label).startsWith('ws:/proxy/network/wss/s/')) return;  // events channel only
      const bytes = new Uint8Array(ev.data, 0, Math.min(ev.data.byteLength, 65536));
      let bin = '';
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      window.__pocSpy.dc.push({
        ts: Date.now(), kind: 'msg', label: dc.label,
        size: ev.data.byteLength, sample: btoa(bin),
      });
    });
  }
  const oCreate = proto.createDataChannel;
  proto.createDataChannel = function(label, init) {
    const dc = oCreate.call(this, label, init);
    hookDC(dc, 'created');
    return dc;
  };
  const oSetRemote = proto.setRemoteDescription;
  proto.setRemoteDescription = function(desc) {
    const self = this;
    self.addEventListener('datachannel', (ev) => hookDC(ev.channel, 'received'));
    return oSetRemote.apply(this, arguments);
  };
})();
"""


def _decode_chunks(buf: bytes) -> tuple[list[dict], bytes]:
    """Parse [4-byte tag][4-byte BE length][zlib JSON] frames out of buf,
    returning (list_of_decoded_jsons, leftover_bytes_for_next_message)."""
    out: list[dict] = []
    i = 0
    while i + 8 <= len(buf):
        length = struct.unpack(">I", buf[i + 4 : i + 8])[0]
        if i + 8 + length > len(buf):
            return out, buf[i:]
        body = buf[i + 8 : i + 8 + length]
        try:
            out.append(json.loads(zlib.decompress(body).decode("utf-8")))
        except Exception:
            pass
        i += 8 + length
    return out, b""


async def capture(console_url: str, seconds: int) -> list[dict]:
    """Drive Chrome via CDP, return the list of decoded UniFi events
    (i.e. message bodies where meta.message=='events')."""
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome has no contexts. Open at least one window.")
        ctx = browser.contexts[0]
        page = await ctx.new_page()
        cdp = await ctx.new_cdp_session(page)
        await cdp.send("Page.enable")
        await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": SPY_SOURCE})

        try:
            await page.goto(console_url, wait_until="domcontentloaded", timeout=20_000)
        except Exception as e:
            print(f"navigate warning (continuing): {e}", flush=True)

        print(f"capturing for {seconds}s ...", flush=True)
        await asyncio.sleep(seconds)
        spy = await page.evaluate("JSON.stringify(window.__pocSpy || {})")
        await page.close()
        await browser.close()

    spy_data = json.loads(spy)
    msgs = [e for e in spy_data.get("dc", []) if e.get("kind") == "msg"]

    # Reassemble across DC messages per channel label
    by_label: dict[str, bytearray] = {}
    decoded_per_label: dict[str, list[dict]] = {}
    for m in msgs:
        label = m["label"]
        by_label.setdefault(label, bytearray()).extend(base64.b64decode(m["sample"]))
        decoded, leftover = _decode_chunks(by_label[label])
        decoded_per_label.setdefault(label, []).extend(decoded)
        by_label[label] = bytearray(leftover)

    # Keep only events-channel messages whose meta.message=='events'.
    events: list[dict] = []
    for label, blocks in decoded_per_label.items():
        if not label.startswith(EVENTS_LABEL_PREFIX):
            continue
        for j in blocks:
            meta = j.get("meta") or {}
            if meta.get("message") != "events":
                continue
            data = j.get("data") or []
            if isinstance(data, list):
                events.extend(d for d in data if isinstance(d, dict))
    return events


def post_to_threatflow(api_base: str, token: str, branch_id: str,
                      flow_rows: list[dict], threat_rows: list[dict]) -> dict:
    body = json.dumps({
        "branch_id":   branch_id,
        "flow_rows":   _serialize(flow_rows),
        "threat_rows": _serialize(threat_rows),
    }).encode("utf-8")
    req = urllib.request.Request(
        api_base.rstrip("/") + "/api/admin/ingest/cloudproxy",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"ingest failed: {e.code} {e.read()[:300]!r}")


def _serialize(rows: list[dict]) -> list[dict]:
    """JSON-safe: datetime -> isoformat, leave the rest alone."""
    out: list[dict] = []
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


async def main_async(args: argparse.Namespace) -> int:
    events = await capture(args.console_url, args.seconds)
    print(f"captured {len(events)} UniFi event(s) on the events channel")
    if events:
        keys = {}
        for e in events:
            keys[e.get("key", "(none)")] = keys.get(e.get("key", "(none)"), 0) + 1
        for k, c in sorted(keys.items(), key=lambda x: -x[1]):
            print(f"  {c:3d}  {k}")

    flows, threats = map_events(
        events,
        branch_id=args.branch_id,
        branch_name="(server-supplied)",
        branch_code="(server-supplied)",
    )
    print(f"mapped: {len(flows)} flow row(s), {len(threats)} threat row(s)")

    if not flows and not threats:
        print("nothing to ingest — exiting cleanly")
        return 0

    if args.dry_run:
        out = Path(__file__).parent / "ingest_preview.json"
        out.write_text(json.dumps({"flow_rows": _serialize(flows), "threat_rows": _serialize(threats)}, indent=2), encoding="utf-8")
        print(f"DRY RUN — wrote {out}")
        return 0

    token = os.environ.get("THREATFLOW_TOKEN")
    if not token:
        print("ERROR: set THREATFLOW_TOKEN env var (admin JWT)", file=sys.stderr)
        return 2
    res = post_to_threatflow(args.api_base, token, args.branch_id, flows, threats)
    print(f"ingest OK: {res}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--branch-id", required=True, help="ThreatFlow branch UUID")
    p.add_argument("--console-url", required=True, help="https://unifi.ui.com/consoles/<id>/network/default/insights/flows")
    p.add_argument("--seconds", type=int, default=60)
    p.add_argument("--api-base", default="https://threatflow.amspec.group")
    p.add_argument("--dry-run", action="store_true", help="map locally + write ingest_preview.json, do not POST")
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
