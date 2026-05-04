# streamer — continuous cloud-proxy ingestion for all branches

Long-lived headless Chromium that opens one tab per cloud-mode branch,
hooks the WebRTC data channel that carries each console's event stream,
decodes the chunked-zlib JSON, maps to `raw_*_events` rows, and POSTs
to the backend's `/api/admin/ingest/cloudproxy` endpoint.

Replaces the manual `tools/cloudproxy_capture/capture.py` flow with a
service that runs continuously for all 55 branches.

## How to bootstrap (one-time)

The streamer needs a Chromium profile with a valid ui.com session.
Two ways to provide it:

### Option A — programmatic login (works only without MFA)

Add to `.env`:

```
UI_EMAIL=service-account@yourdomain.com
UI_PASSWORD=…
```

On first start, the streamer logs in via the form, persists cookies in
the `streamer_profile` docker volume, then runs normally. If the account
has MFA enabled, the script fails loudly and you fall back to Option B.

### Option B — bake cookies from your local Chrome (recommended)

Easier and avoids putting Ubiquiti creds in env. Run locally on your
already-logged-in Chrome:

```
cd tools\cloudproxy_capture
python export_session.py session.tar.gz
```

(Coming next — see roadmap below.) Then:

```
scp session.tar.gz ubuntu@VPS:/tmp/
ssh ubuntu@VPS 'docker compose stop streamer && \
   docker run --rm -v threatflow_streamer_profile:/dst -v /tmp:/src alpine \
     sh -c "tar xzf /src/session.tar.gz -C /dst" && \
   docker compose up -d streamer'
```

Cookies last ~30 days; re-bake when `streamer` logs persistent 401s.

## Operations

- Logs: `docker compose logs -f streamer` (one INFO line per drain per branch)
- Memory budget: 50-60 tabs ~= 3-4 GB Chromium RSS. The compose file pins
  `shm_size: 2gb` to avoid `/dev/shm` exhaustion under load.
- Restart: `docker compose restart streamer`. The profile volume is sticky
  so cookies survive.

## Tunables (.env)

```
STREAMER_DRAIN_SECONDS=30          # how often each tab flushes its buffer
STREAMER_TAB_SILENT_TIMEOUT=600    # reload tab if no events for this long
STREAMER_MAX_TABS=60               # safety cap
STREAMER_HEADLESS=true             # set false only for VNC bootstrap
STREAMER_BOOTSTRAP_ONLY=false      # one-shot login mode
```

## Roadmap

- Add `tools/cloudproxy_capture/export_session.py` — extracts cookies from
  the user's local Chrome via CDP and packages them for SCP.
- Per-tab metrics surfaced on the Operations / Observability page (events
  per minute, last_seen_at, RSS).
- Sharded mode: split tabs across multiple Chrome processes if RSS gets
  unhealthy.
- Server-side WebRTC adapter (aiortc) replacement — eventual goal, removes
  the headless-browser dependency entirely. Mapper module is reusable.
