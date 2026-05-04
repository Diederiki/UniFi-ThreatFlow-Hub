# ipfix_collector

UDP listener that accepts NetFlow v9 (RFC 3954) and IPFIX (RFC 7011)
flow exports from UniFi UDM Pro / Pro Max gateways and writes them
into ClickHouse `raw_flow_events`. The dashboards (Top Visited,
Destinations, Suspicion Score, Branch Heatmap, etc.) read from that
table directly so they light up the moment IPFIX traffic arrives.

## Why this exists

This is the architecturally-clean alternative to the cloud-proxy
WebRTC streamer: zero auth, no Cognito, no headless Chromium — just
UDP packets on a port. The UDM's IPFIX export carries strictly more
flow detail than the unifi.ui.com dashboard does, mapped 1:1 to our
schema.

## Per-branch UDM Pro config

Console UI → CyberSecure → Traffic Logging → NetFlow (IPFIX):

- ✅ enable NetFlow (IPFIX)
- Version: 10 (IPFIX). v9 also works but IPFIX is preferred for the
  variable-length / enterprise IE support.
- Collector Address: `<VPS public IP>`
- Port: `2055`
- Sampling Mode: Hash, Sampling Rate: 1 (or 512 for high-throughput
  branches; 1 = every flow)
- Flow Logging: All Traffic
- Apply Changes

## Deployment / firewall notes

The collector binds `0.0.0.0:2055/udp`. Lock down at the host iptables
layer rather than at the container — IP allowlisting per-branch is in
`infra/scripts/ipfix-firewall.sh`. Until that lands the listener will
accept exports from anywhere; spoofed packets just fail parsing.

## Branch attribution

Each parsed flow is stamped with the branch derived from the source IP
(the UDM's NAT'd WAN address). Mapping table:
`infra/sql/branch_wan_ips.sql` (`wan_ip → branches.id`). If a UDM's
exports arrive from an IP we don't yet know about, we synthesise an
`unknown-<ip>` branch_code so the data still lands and you can wire
it up later.
