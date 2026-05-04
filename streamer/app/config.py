"""Environment-driven config for the streamer service."""
from __future__ import annotations

import os


def _env(name: str, default: str | None = None, *, required: bool = False) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        raise RuntimeError(f"required env var missing: {name}")
    return v or ""


class Settings:
    # Where the headless profile lives. Persisted via a docker volume so
    # cookies + login state survive restarts.
    profile_dir = _env("STREAMER_PROFILE_DIR", "/var/lib/streamer/chrome-profile")

    # ui.com credentials. Used only on cold-start when the profile has no
    # valid session; once cookies are baked in, these are unused.
    ui_email    = _env("UI_EMAIL")
    ui_password = _env("UI_PASSWORD")

    # ThreatFlow backend (internal docker host). The streamer uses an admin
    # account to mint a session JWT, then sends ingest POSTs as that user.
    api_base     = _env("THREATFLOW_API_BASE", "http://backend:8000")
    admin_email    = _env("ADMIN_EMAIL", required=True)
    admin_password = _env("ADMIN_PASSWORD", required=True)

    # How often each tab drains its in-page event buffer back to Python +
    # ingests. 30s mirrors the existing collector cadence and gives the WS
    # subscription enough time to coalesce events.
    drain_seconds = int(_env("STREAMER_DRAIN_SECONDS", "30"))

    # If a tab hasn't seen ANY data-channel traffic for this long, the tab
    # is considered dead and the supervisor reloads it. Some quiet branches
    # legitimately go minutes between events, so the threshold is generous.
    tab_silent_timeout_seconds = int(_env("STREAMER_TAB_SILENT_TIMEOUT", "600"))

    # Hard cap so a misconfig doesn't blow up the VPS. Beyond this we'd shard
    # across multiple Chrome processes — see roadmap in README.
    max_tabs = int(_env("STREAMER_MAX_TABS", "60"))

    # Whether to launch Chrome with a head (useful for one-time bootstrap
    # via VNC). Default headless because the service runs unattended.
    headless = _env("STREAMER_HEADLESS", "true").lower() in ("1", "true", "yes")

    # Set true for first-run interactive bootstrap: launches non-headless,
    # logs in, persists cookies, exits.
    bootstrap_only = _env("STREAMER_BOOTSTRAP_ONLY", "false").lower() in ("1", "true", "yes")


settings = Settings()
