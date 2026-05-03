# UniFi Data Model — what we mirror, what we don't (yet)

UI's help center is behind Cloudflare's bot challenge so I couldn't fetch the
two articles you linked verbatim. This doc captures the data model from prior
knowledge of the UniFi Network Application + CyberSecure subscription, and
the live screenshot of the Traffic Flows view you shared earlier.

## A. UniFi Network — Traffic Flows (built-in, no subscription)

Traffic Flows is the DPI-driven view at `/network/{site}/insights/flows`.
Each row is one Layer-4 session enriched with Layer-7 application detection,
optional GeoIP, and a risk score derived from app category + destination
reputation + policy outcome.

### Per-flow fields (left side of the table in your screenshot)

| Field | UniFi label | Where in our schema | Status |
|---|---|---|---|
| Source client (hostname or MAC label) | "Source" | `raw_flow_events.source_hostname` | ✅ ingest, displayed |
| Destination IP / hostname | "Destination" | `destination_ip` + `destination_hostname` | ✅ |
| Destination country (flag) | "Destination" | `destination_country` (LowCardinality) | ✅ |
| Service / app | "Service" (HTTPS, DNS, Other…) | `application` | ✅ |
| Risk indicator (green/yellow/red bars) | "Risk" | `risk` (low/medium/high) | ✅ |
| Direction arrow | "Dir." | `direction` (outbound/inbound/lan-to-lan) | ✅ |
| Source zone (VLAN) | "In" | `source_vlan` | ✅ ingest, surfaced on detail |
| Egress interface | "Out" (e.g. "Hallo.eu Fiber") | not stored | ⚠️ **missing — would need new column** |
| Action | "Action" (Allow / Block / Reject) | `action` | ✅ |
| Date / Time | "Date / Time" | `event_time` (DateTime64) | ✅ |
| Bytes up / down | not in main grid; in detail | `bytes_up` + `bytes_down` | ✅ ingest |
| Packets up / down | not in main grid | `packets_up` + `packets_down` | ✅ ingest, not displayed |
| Duration | not in main grid | `duration_ms` | ✅ ingest |
| Source MAC | shown on hover | `source_mac` | ✅ ingest, not displayed |
| Source port | shown on detail | `source_port` | ✅ |
| Destination port | shown on detail | `destination_port` | ✅ |
| Protocol | shown on detail | `protocol` | ✅ |
| Application category | shown on filters | `application_category` | ✅ |
| Policy name (e.g. "VLAN 14") | "Policy" | `policy_name` | ✅ |
| Encryption / TLS info | rare, on detail | not stored | ⚠️ missing |
| Connection state (NEW / EST / FIN) | not in UI | not stored | n/a |

### Flow Summary panel (top of your screenshot)

| UniFi panel | Our equivalent |
|---|---|
| Total flows | Overview KPI `total_flows` ✅ |
| Low / Suspicious / Concerning counts | We split as low_risk / medium_risk / high_risk_events ✅ |
| Top Destinations (right column) | `/api/top/destinations` ✅ |
| Top Clients | `/api/top/clients` ✅ |
| Top Apps with bytes | `/api/top/applications` ✅ — **but we show event count, not bytes** ⚠️ |

### Left sidebar filters (UniFi)

| UniFi filter | Our equivalent |
|---|---|
| Risk: green / yellow / red | AdvancedFilters → Risk ✅ |
| Time: 1h / 1D / 1W / 1M | Global timeframe selector (we have 12 windows) ✅ |
| Flows: All / Blocked / Threats | Threats page + Blocked page + Overview ✅ |
| Direction: ↓ / ↑ / ↔ | not exposed yet ⚠️ |
| Source / Source Zone | filterable via source_ip ✅ |
| Flows on Map (geo viz) | not built ⚠️ — needs a map library |

### Egress / WAN labeling
UniFi labels each flow with the WAN it left through (e.g. "Hallo.eu Fiber"). Useful for multi-WAN branches. **Gap:** add `egress_interface String LowCardinality` to `raw_flow_events`. Easy.

## B. UniFi CyberSecure (paid IDS/IPS subscription)

CyberSecure uses a Suricata engine with Proofpoint ET Pro rules + UI's own
threat intel (vs ET Open in the free tier).

### Per-event fields

| CyberSecure field | Our equivalent | Status |
|---|---|---|
| Signature ID (SID, Suricata) | `signature` String | ✅ ingest text label |
| Classification ("trojan-activity", "attempted-recon"…) | `threat_category` LowCardinality | ✅ |
| Severity (Critical / High / Medium / Low) | `severity` | ✅ |
| Risk (separate from severity) | `risk` | ✅ |
| Action (Drop / Reject / Pass) | `action` | ✅ |
| Source IP / port / MAC / hostname | source_* columns | ✅ |
| Destination IP / port / hostname / country | destination_* columns | ✅ |
| Protocol | `protocol` | ✅ |
| Triggering client (gateway-detected) | `client_ip` + `client_mac` + `client_hostname` | ✅ |
| Policy / sensor name | `policy_name` ("IDS sensor", "IPS sensor") | ✅ |
| Raw packet payload (bounded) | `raw_json` | ✅ |
| **MITRE ATT&CK technique** | not stored | ⚠️ missing |
| **CVE references** | not stored | ⚠️ missing |
| **Suricata rule SID** (numeric, distinct from text signature) | not stored | ⚠️ missing |
| **Threat reputation** (e.g. CINS Score, AlienVault OTX) | not stored | ⚠️ missing |
| **Geo source country** (in addition to dest) | not stored explicitly | ⚠️ partial |
| **AI-driven threat insight text** | not stored | ⚠️ Ubiquiti-specific feature |

### CyberSecure UI views (vs ours)

| UniFi view | Ours |
|---|---|
| Threats list | /threats ✅ (filterable) |
| Threats by category | /categories shows app categories — would need a separate "threat categories" panel ⚠️ partial |
| Top sources | /api/top/clients ✅ |
| Top destinations | /api/top/destinations ✅ |
| Geo heatmap of sources | not built ⚠️ |
| Sensor health | /collector-health (analogous) ✅ |
| Block / Allow rule editor | not built (would require write-back to UniFi controller) ⚠️ |
| Per-VLAN sensor toggles | not built (controller-side) ⚠️ |

## C. Recommended next-batch additions

If you want to close the most visible gaps in one focused pass:

### Schema additions to `raw_flow_events`
```sql
ALTER TABLE raw_flow_events ADD COLUMN egress_interface LowCardinality(String) DEFAULT '';
ALTER TABLE raw_flow_events ADD COLUMN tls_version LowCardinality(String) DEFAULT '';
```

### Schema additions to `raw_threat_events`
```sql
ALTER TABLE raw_threat_events ADD COLUMN sid UInt32 DEFAULT 0;
ALTER TABLE raw_threat_events ADD COLUMN mitre_techniques Array(LowCardinality(String)) DEFAULT [];
ALTER TABLE raw_threat_events ADD COLUMN cve_refs Array(LowCardinality(String)) DEFAULT [];
ALTER TABLE raw_threat_events ADD COLUMN source_country LowCardinality(String) DEFAULT '';
```

### UI additions
- Top Visited: change app row to show **bytes-up + bytes-down** (we have the data, just sum it instead of count)
- Flow detail drawer (click any row in /threats or /blocked → side panel with all fields including bytes/packets/MAC/duration/policy)
- "Threats by MITRE technique" on /suspicion
- World map heat overlay for Top Countries (use a lightweight SVG world map; D3 / react-simple-maps are options)

### Direction filter
Add `direction` to AdvancedFilters across Threats / Blocked (matches UniFi's ↓/↑/↔).

## D. What we won't mirror

- **Live PCAP / packet capture per session** — UniFi can dump a pcap for a flow; we don't ingest payloads at that depth.
- **Rule writeback** — pushing IDS rule changes back into the UDM Pro requires admin write API access we don't ask for.
- **Per-AP wireless metrics** — our schema is gateway-scoped, not AP-scoped.
- **DPI heuristic signals** (e.g. "TLS Client Hello fingerprints") — UniFi exposes some, but only for paid CyberSecure tiers.

These are all reachable later if needed; flag them when you want to prioritize.
