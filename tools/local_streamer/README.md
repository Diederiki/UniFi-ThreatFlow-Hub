# local_streamer — continuous multi-tab cloud-proxy capture

Runs in YOUR Chrome (via CDP-attach), opens one tab per ThreatFlow branch,
hooks the WebRTC data channel that carries each console's events, decodes
+ maps + ingests continuously.

## Why this exists

The VPS-side `streamer/` service hits `"Device not linked"` from AWS IoT
because its Cognito identity differs from your real Chrome session. Your
Chrome already has all 55 devices linked to its identity, so capturing
from there works. Trade-off: your PC has to stay on with Chrome running.

## One-time setup

1. **Close every Chrome window** (Task Manager → end all `chrome.exe`).
2. **Start Chrome with the debug port + dedicated profile**:
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
       --remote-debugging-port=9222 ^
       --user-data-dir=C:\chrome-debug-profile ^
       https://unifi.ui.com
   ```
3. **Log in to ui.com once** (handle MFA in that window).
4. **Get a ThreatFlow admin JWT** (lasts ~12h):
   ```
   curl -i -X POST https://threatflow.amspec.group/api/auth/login ^
        -H "Content-Type: application/json" ^
        -d "{\"email\":\"diederik.vantienen@amspecgroup.com\",\"password\":\"...\"}"
   ```
   Copy the `threatflow_session=...` cookie value out of the response.
5. **Install Python deps** (one time):
   ```
   cd C:\UniFi-ThreatFlow-Hub\tools\local_streamer
   pip install -r requirements.txt
   ```

## Running

```
cd C:\UniFi-ThreatFlow-Hub\tools\local_streamer
set THREATFLOW_TOKEN=eyJhbGciOiJIUzI1...
python local_streamer.py
```

It will:
- Fetch the branch list from threatflow.amspec.group
- Open one Chrome tab per cloud-mode branch (default 55, capped by
  `STREAMER_MAX_TABS`), staggered 6 seconds apart to dodge ui.com rate limits
- Drain each tab every 30 seconds and POST mapped rows to the ingest API
- Log per-branch lifetime counts and a per-minute aggregate

Press Ctrl+C to stop.

## Tunables (env vars)

```
STREAMER_DRAIN_SECONDS=30      # how often to flush events per tab
STREAMER_TAB_STAGGER=6         # seconds between successive tab opens
STREAMER_MAX_TABS=55           # cap; full sweep needs ~5.5 min to spin up
STREAMER_BRANCH_FILTER=RTC     # substring of branch_code; useful for testing
CHROME_CDP_URL=http://localhost:9222
THREATFLOW_API_BASE=https://threatflow.amspec.group
```

## Operational notes

- Chrome RAM with 55 active WebRTC tabs: ~3-6 GB. Close other heavy apps.
- Your ui.com cookies last ~30 days. Re-login when the streamer logs
  persistent 4xx ingest errors.
- The dedicated profile (`C:\chrome-debug-profile`) means your normal
  browsing isn't affected. Bookmark, history, and extensions live in the
  default Chrome profile.
- For 24/7 operation: leave the PC on, prevent sleep, optionally wrap
  this in a Task Scheduler task that re-launches if it crashes.

## What gets ingested

Same as the manual `tools/cloudproxy_capture/capture.py`:
- `EVT_IDS_*`, `EVT_IPS_*`, `EVT_GW_DPI_*`, `EVT_GW_TM_*` → `raw_threat_events`
- `EVT_FW_*` (deny/block flavours) → `raw_flow_events` action='block'

The backend's threat enricher decorates threat rows with MITRE ATT&CK
technique IDs + CVE refs at ingest time.
