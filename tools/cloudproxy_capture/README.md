# Cloud-proxy capture → ThreatFlow ingest

A local Python tool that:
1. attaches to your running Chrome (which is already logged into ui.com)
2. opens a UniFi console URL
3. listens to the WebRTC data channel that carries the controller's event stream
4. decodes the zlib-compressed JSON chunks
5. maps relevant events (firewall blocks, IDS/IPS hits) to `raw_flow_events` /
   `raw_threat_events` rows
6. POSTs them to `/api/admin/ingest/cloudproxy` on threatflow.amspec.group

Result: dashboards on threatflow.amspec.group light up with real data from
that console for the duration captured.

## Why this exists

UniFi's cloud-proxy auth is non-trivial (AWS Cognito → SigV4 IoT MQTT →
WebRTC peer-to-peer with DTLS). A clean server-side reimplementation is
weeks of fragile work. This tool is a pragmatic bridge: real data into
ThreatFlow today, while the team decides whether to invest in a fully
server-side adapter.

## One-time setup

1. Close every Chrome window — Task Manager → Background processes → end any
   `chrome.exe` that survives.
2. Start Chrome with the debugger port AND a separate user-data-dir
   (Chrome 127+ silently drops the flag on the default profile):
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
       --remote-debugging-port=9222 ^
       --user-data-dir=C:\chrome-debug-profile ^
       https://unifi.ui.com
   ```
3. Log in to ui.com inside that window once. Cookies persist for the next
   ~30 days, so subsequent runs skip this step.
4. Install Python deps:
   ```
   cd C:\UniFi-ThreatFlow-Hub\tools\cloudproxy_capture
   pip install -r requirements.txt
   ```

## Per-run (~1 min)

1. Get an admin JWT for ThreatFlow (one-time per session, lasts ~24h):
   ```
   curl -X POST https://threatflow.amspec.group/api/auth/login \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"diederik.vantienen@amspecgroup.com\",\"password\":\"...\"}"
   ```
   Copy the `access_token` field.

2. Find the branch UUID in ThreatFlow → Branches table (or via PG).

3. Run a capture:
   ```
   set THREATFLOW_TOKEN=eyJ...
   python capture.py --branch-id <uuid> ^
        --console-url "https://unifi.ui.com/consoles/<id>/network/default/insights/flows" ^
        --seconds 60
   ```

   - `--seconds 60` is reasonable; longer runs catch more events.
   - The Insights/Flows view auto-subscribes to firewall + IDS/IPS events.
     The plain `/dashboard` URL captures only aggregate counters (no
     per-event data) so the threat tables stay empty.
   - `--dry-run` maps locally + writes `ingest_preview.json` instead of
     posting. Use this once on a new console to sanity-check the mapping
     before sending data to the live cluster.

## What gets sent

Currently only:
- `EVT_IDS_*`, `EVT_IPS_*`, `EVT_GW_DPI_*`, `EVT_GW_TM_*` → `raw_threat_events`
- `EVT_FW_*` (deny/block flavours) → `raw_flow_events` with `action='block'`

LU/WU connect/disconnect, AD logins, and AP/SW device events are intentionally
skipped — they don't carry per-flow IP/port/byte data and would only pollute
the dashboards.

## Limitations & next steps

- One console per run. To cover multiple branches, run sequentially with
  a different `--branch-id` + `--console-url` each time, or wrap in a loop.
- Chrome must stay open in the debugged profile.
- Auth: relies on your personal ui.com cookies. If MFA is enforced
  organisation-wide, expect to re-auth ~weekly.
- Long-term: replace this with a server-side adapter that does AWS Cognito
  login + SigV4 IoT MQTT + Python WebRTC peer (`aiortc`) per branch. That's
  ~2-3 weeks of focused engineering. The mapper module here is reusable.
