"""ThreatFlow cloud-proxy streamer service.

Runs a long-lived headless Chromium with one tab per enabled cloud branch,
hooks the WebRTC data channel that carries each console's event stream,
decodes the chunk-zlib JSON, and POSTs mapped rows to the backend's
/api/admin/ingest/cloudproxy endpoint.

This replaces the manual `tools/cloudproxy_capture/capture.py` flow with
something that runs continuously for all branches.
"""
