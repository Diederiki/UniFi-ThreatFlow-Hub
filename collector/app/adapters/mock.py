"""Mock collector — generates a realistic stream of flow + threat events per
tick so dashboards / scoring / alerts are exercisable without live UniFi gear.

Distribution per tick (one branch):
  ~80% allow flows
  ~15% block flows
  ~5%  IDS/IPS detections (also written to raw_threat_events)

Source IPs cluster into a per-branch /24 derived from the branch UUID so the
UI can group "clients per branch" naturally.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.adapters.base import BaseUniFiCollector, CollectResult
from app.config import COLLECTOR_VERSION

DOMAINS = [
    "google.com", "github.com", "cloudflare.com", "microsoft.com",
    "aws.amazon.com", "stripe.com", "slack.com", "openai.com",
    "anthropic.com", "spotify.com", "youtube.com", "linkedin.com",
    "office.com", "salesforce.com", "okta.com", "zoom.us",
    "atlassian.com", "datadoghq.com", "1.1.1.1", "8.8.8.8",
]
APPS = [
    ("HTTPS",  "web"),     ("DNS",      "dns"),    ("SSH",        "admin"),
    ("SSL/TLS","web"),     ("MSSQL",    "db"),     ("Spotify",    "streaming"),
    ("YouTube","streaming"),("Office365","saas"),  ("Slack",      "saas"),
    ("Zoom",   "saas"),    ("RDP",      "admin"),  ("PostgreSQL", "db"),
]
COUNTRIES = ["US", "NL", "SG", "DE", "GB", "FR", "JP", "AU", "CA", "BR", "IE"]
SIGNATURES = [
    ("ET POLICY HTTP traffic on port 443 (POST)",          "policy",    "low"),
    ("ET INFO Suspicious User-Agent (curl)",               "info",      "low"),
    ("ET MALWARE Win32/Generic.Trojan",                    "malware",   "high"),
    ("ET TROJAN Cobalt Strike Beacon HTTP Response",       "malware",   "high"),
    ("ET SCAN Nmap NSE Heartbleed Scan",                   "recon",     "medium"),
    ("ET POLICY DNS Query for .onion TLD",                 "policy",    "medium"),
    ("ET CINS Active Threat Intelligence Poor Reputation", "reputation","medium"),
    ("ET WEB_SERVER ColdFusion administrator access",      "intrusion", "high"),
]
POLICY_NAMES = ["LAN→WAN allow", "Block adult", "IDS sensor", "Geo block CN/RU", "Default deny"]


def _stable_octet(branch_id: str, salt: int) -> int:
    return abs(hash(f"{branch_id}:{salt}")) % 254 + 1


class MockCollector(BaseUniFiCollector):
    async def collect(self) -> CollectResult:
        now = datetime.now(timezone.utc)
        result = CollectResult(
            endpoint_used=f"mock://{self.branch_code}/v2/api/site/{self.site_id}/traffic-flows",
            unifi_os_version="9.0.114 (mock)",
            network_app_version="9.0.114 (mock)",
        )

        rng = random.Random(f"{self.branch_id}:{int(now.timestamp() // 30)}")
        n = rng.randint(40, 180)
        # 5% chance of a burst tick
        if rng.random() < 0.05:
            n = rng.randint(400, 700)

        oct_a = _stable_octet(self.branch_id, 1)
        oct_b = _stable_octet(self.branch_id, 2)

        for _ in range(n):
            roll = rng.random()
            if roll < 0.05:
                action, risk, policy_type = "block", rng.choice(["medium", "high", "high"]), "ids_ips"
            elif roll < 0.20:
                action, risk, policy_type = "block", rng.choice(["low", "low", "medium"]), "firewall"
            else:
                action, risk, policy_type = "allow", rng.choice(["low", "low", "low", "medium"]), "allow"

            host = rng.choice(DOMAINS)
            app, cat = rng.choice(APPS)
            evt_time = now - timedelta(milliseconds=rng.randint(0, 28000))

            flow = {
                "branch_id": self.branch_id,
                "branch_name": self.branch_name,
                "branch_code": self.branch_code,
                "event_time": evt_time,
                "action": action,
                "risk": risk,
                "severity": {"low": "informational", "medium": "warning", "high": "critical"}[risk],
                "policy_type": policy_type,
                "policy_name": rng.choice(POLICY_NAMES),
                "source_ip": f"10.{oct_a}.{oct_b}.{rng.randint(2, 254)}",
                "source_port": rng.randint(40000, 60000),
                "source_mac": "",
                "source_hostname": f"{self.branch_code.lower()}-host-{rng.randint(1, 80):02d}",
                "source_vlan": f"VLAN{rng.choice([10, 20, 30, 40])}",
                "destination_ip": f"{rng.randint(1, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
                "destination_port": rng.choice([80, 443, 22, 53, 3389, 1433, 5432]),
                "destination_hostname": host,
                "destination_country": rng.choice(COUNTRIES),
                "protocol": rng.choice(["tcp", "tcp", "tcp", "udp"]),
                "application": app,
                "application_category": cat,
                "bytes_up": int(rng.lognormvariate(7, 2)),
                "bytes_down": int(rng.lognormvariate(8, 2.2)),
                "packets_up": rng.randint(1, 200),
                "packets_down": rng.randint(1, 300),
                "duration_ms": rng.randint(20, 60_000),
                "direction": "outbound",
                "raw_json": "{}",
                "collector_version": COLLECTOR_VERSION,
            }
            result.flows.append(flow)

            # IDS/IPS events also surface as a threat record
            if policy_type == "ids_ips":
                sig, cat_t, sig_risk = rng.choice(SIGNATURES)
                threat = {
                    "branch_id": self.branch_id,
                    "branch_name": self.branch_name,
                    "branch_code": self.branch_code,
                    "event_time": evt_time,
                    "action": action,
                    "severity": flow["severity"],
                    "risk": sig_risk,
                    "signature": sig,
                    "threat_category": cat_t,
                    "policy_type": "ids_ips",
                    "policy_name": rng.choice(["IDS sensor", "IPS sensor"]),
                    "source_ip": flow["source_ip"],
                    "source_port": flow["source_port"],
                    "source_mac": "",
                    "source_hostname": flow["source_hostname"],
                    "destination_ip": flow["destination_ip"],
                    "destination_port": flow["destination_port"],
                    "destination_hostname": host,
                    "destination_country": flow["destination_country"],
                    "protocol": flow["protocol"],
                    "client_ip": flow["source_ip"],
                    "client_mac": "",
                    "client_hostname": flow["source_hostname"],
                    "raw_json": "{}",
                    "collector_version": COLLECTOR_VERSION,
                }
                result.threats.append(threat)

        return result
