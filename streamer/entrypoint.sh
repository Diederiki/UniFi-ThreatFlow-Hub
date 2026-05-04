#!/bin/sh
# Start Xvfb on display :99 so headed Chromium has a (virtual) screen to draw on.
# This is a deliberate choice over Playwright's headless mode — Chromium's
# WebRTC stack hits ICE host-lookup failures in headless that don't reproduce
# under Xvfb. The streamer service still treats the launch as headless from
# its perspective (no operator interaction), it's just that Chromium thinks
# it has a display.
set -e

# Spawn Xvfb if not already running. Quiet output to avoid log spam.
if ! pgrep Xvfb > /dev/null; then
  Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp >/dev/null 2>&1 &
  # Tiny wait so the server is actually listening before Chromium attaches.
  sleep 1
fi

exec "$@"
