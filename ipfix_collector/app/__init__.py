"""IPFIX / NetFlow v9 collector for ThreatFlow.

UDP listener that accepts NetFlow v9 (RFC 3954) and IPFIX (RFC 7011) flow
exports from UniFi UDM Pro / Pro Max gateways and writes them into
`raw_flow_events` for the existing dashboards to consume.

This is the architecturally-clean alternative to the cloud-proxy WebRTC
streamer: zero auth, no Cognito, no headless Chromium — just UDP packets
landing on a port. The UDM's IPFIX export carries strictly more flow
detail than the unifi.ui.com dashboard does, mapped 1:1 to our schema.
"""
