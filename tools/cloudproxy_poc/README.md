# Cloud-proxy POC — capture WebSocket frames from unifi.ui.com

A 30-second feasibility test for ingesting per-flow / per-threat events from
Ubiquiti's cloud-proxy. Connects Playwright to your existing Chrome over the
DevTools Protocol so your ui.com login session is reused — no re-auth, no MFA.

## What we're proving

We want to see whether the data the unifi.ui.com dashboards render — the live
flow + threat counters — actually flows over a WebSocket we can read, and
whether the frame contents are parseable enough to map into our
`raw_flow_events` / `raw_threat_events` schema.

If the captured frames carry recognizable JSON with flow metadata, the
adapter is realistic to build. If the frames are opaque binary or per-message
encrypted, the cloud-proxy path stays a dead end and we focus on the
LocalControllerAdapter pilot instead.

## Run

1. **Close every Chrome window.** Then check Task Manager → Background
   processes → kill any lingering `chrome.exe`. Important — if a normal
   Chrome instance is already attached to your profile, the
   `--remote-debugging-port` flag silently does nothing.

2. **Start Chrome with the debugger port** (reuses your normal profile so
   ui.com stays logged in):

   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
   ```

   Verify by visiting <http://localhost:9222/json/version> — should return
   JSON.

3. **Confirm you're still logged in to <https://unifi.ui.com>.**

4. **Install + run:**

   ```
   cd C:\UniFi-ThreatFlow-Hub\tools\cloudproxy_poc
   pip install -r requirements.txt
   python poc.py "<console-url>"
   ```

   The console URL is whatever your address bar shows when you open one of
   your consoles (e.g. clicking "Belgium-HQ-UDMProMAX"). Pick a console that
   shows **live updating** numbers in your normal browser — that's the
   strongest signal its tunnel is healthy.

## Output

- `frames.jsonl` — one line per WS frame (in/out, size, payload up to 8KB)
- `summary.json` — counts, handshake URLs, first 5 frames each direction
- stdout — live preview as frames arrive

If `frames.jsonl` is empty, the WebSocket either didn't open (tunnel
unhealthy → try a different console) or the bootstrap took longer than 30s
(bump `CAPTURE_SECONDS` in `poc.py`).

## What I'll do with the output

Send me `summary.json` and the first ~50 lines of `frames.jsonl`. I'll
identify the message types, propose a parser shape, and tell you whether
building a CloudProxyAdapter is realistic vs. whether we should stick with
LocalControllerAdapter for any branch you can VPN into.
