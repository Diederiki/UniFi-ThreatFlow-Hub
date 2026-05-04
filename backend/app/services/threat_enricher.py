"""Decorate raw threat events with MITRE ATT&CK technique IDs and CVE refs.

The enricher is intentionally small and explicit:
  - A signature-substring → technique mapping (case-insensitive)
  - A technique → tactic mapping (so the UI can group techniques by tactic)
  - A regex sweep over the signature + raw_json text for `CVE-YYYY-NNNN`

UniFi's IDS/IPS signatures are mostly Suricata/Emerging Threats rule names.
We classify by the human-readable substring rather than by SID, which means
the table works for both UniFi's internal categorization and ET-PRO names.

If a signature doesn't match any rule, the event still ships — just with
empty `mitre_techniques` / `mitre_tactics`. We never fail an insert because
of enrichment.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# (substring, technique_id). First match wins; order matters for specificity.
_SIGNATURE_RULES: tuple[tuple[str, str], ...] = (
    # Initial Access
    ("phish",                        "T1566"),
    ("spearphish",                   "T1566.001"),
    # Execution
    ("powershell",                   "T1059.001"),
    ("cmd.exe",                      "T1059.003"),
    ("bash",                         "T1059.004"),
    ("javascript",                   "T1059.007"),
    # Persistence / Privilege Escalation
    ("scheduled task",               "T1053.005"),
    ("registry",                     "T1112"),
    # Defense Evasion
    ("obfusc",                       "T1027"),
    ("packed",                       "T1027.002"),
    # Credential Access
    ("brute force",                  "T1110"),
    ("password spray",               "T1110.003"),
    ("credential",                   "T1003"),
    ("kerberoast",                   "T1558.003"),
    # Discovery
    ("port scan",                    "T1046"),
    ("nmap",                         "T1046"),
    ("dns query",                    "T1071.004"),
    # Lateral Movement
    ("smb",                          "T1021.002"),
    ("rdp",                          "T1021.001"),
    ("psexec",                       "T1570"),
    # Collection
    ("keylog",                       "T1056.001"),
    # Command & Control
    ("c2",                           "T1071"),
    ("cobalt strike",                "T1071.001"),
    ("dns tunnel",                   "T1071.004"),
    ("tor",                          "T1090.003"),
    ("proxy",                        "T1090"),
    # Exfiltration
    ("exfiltration",                 "T1041"),
    # Impact
    ("ransomware",                   "T1486"),
    ("ddos",                         "T1498"),
    ("amplification",                "T1498.002"),
    # Web attacks (Suricata signatures often reference these)
    ("sql injection",                "T1190"),
    ("sqli",                         "T1190"),
    ("xss",                          "T1059.007"),
    ("rce",                          "T1190"),
    ("path traversal",               "T1083"),
    ("directory traversal",          "T1083"),
    ("lfi",                          "T1083"),
    ("rfi",                          "T1190"),
    # Malware families (catch-all → C2)
    ("trojan",                       "T1071"),
    ("malware",                      "T1071"),
    ("emotet",                       "T1071.001"),
    ("trickbot",                     "T1071.001"),
    ("qakbot",                       "T1071.001"),
    ("agent tesla",                  "T1056.001"),
    # Generic exploitation
    ("exploit",                      "T1190"),
    ("buffer overflow",              "T1203"),
)

# MITRE ATT&CK technique → kebab-case tactic. Multiple tactics possible per
# technique; we list the most representative.
_TECHNIQUE_TACTICS: dict[str, tuple[str, ...]] = {
    "T1003":     ("credential-access",),
    "T1021.001": ("lateral-movement",),
    "T1021.002": ("lateral-movement",),
    "T1027":     ("defense-evasion",),
    "T1027.002": ("defense-evasion",),
    "T1041":     ("exfiltration",),
    "T1046":     ("discovery",),
    "T1053.005": ("persistence", "privilege-escalation", "execution"),
    "T1056.001": ("collection", "credential-access"),
    "T1059":     ("execution",),
    "T1059.001": ("execution",),
    "T1059.003": ("execution",),
    "T1059.004": ("execution",),
    "T1059.007": ("execution",),
    "T1071":     ("command-and-control",),
    "T1071.001": ("command-and-control",),
    "T1071.004": ("command-and-control",),
    "T1083":     ("discovery",),
    "T1090":     ("command-and-control",),
    "T1090.003": ("command-and-control",),
    "T1110":     ("credential-access",),
    "T1110.003": ("credential-access",),
    "T1112":     ("defense-evasion",),
    "T1190":     ("initial-access",),
    "T1203":     ("execution",),
    "T1486":     ("impact",),
    "T1498":     ("impact",),
    "T1498.002": ("impact",),
    "T1558.003": ("credential-access",),
    "T1566":     ("initial-access",),
    "T1566.001": ("initial-access",),
    "T1570":     ("lateral-movement",),
}

_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
# Compile each needle as a regex with word boundaries so short tokens like
# "tor" / "smb" / "c2" don't match inside unrelated words ("factor", "smbios",
# "etc2"). Multi-word needles ("cobalt strike") still match phrase-by-phrase.
_SIGNATURE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(r"\b" + re.escape(needle) + r"\b", re.IGNORECASE), tech)
    for needle, tech in _SIGNATURE_RULES
)


def _techniques_for(text: str) -> list[str]:
    found: list[str] = []
    for pat, tech_id in _SIGNATURE_PATTERNS:
        if pat.search(text) and tech_id not in found:
            found.append(tech_id)
    return found


def _tactics_for(techniques: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for t in techniques:
        for tac in _TECHNIQUE_TACTICS.get(t, ()):
            if tac not in seen:
                seen.append(tac)
    return seen


def _cves_in(*texts: str) -> list[str]:
    found: list[str] = []
    for t in texts:
        for m in _CVE_RE.findall(t or ""):
            cve = m.upper()
            if cve not in found:
                found.append(cve)
    return found


def enrich_threat(event: dict[str, Any]) -> dict[str, Any]:
    """Mutate a threat event dict to add `mitre_techniques`, `mitre_tactics`,
    `cve_refs`. Safe to call on already-enriched events — preserves any
    existing values and only fills gaps."""
    signature = str(event.get("signature") or "")
    category = str(event.get("threat_category") or "")
    raw = str(event.get("raw_json") or "")

    if not event.get("mitre_techniques"):
        techniques = _techniques_for(f"{signature} {category}")
        event["mitre_techniques"] = techniques
    if not event.get("mitre_tactics"):
        event["mitre_tactics"] = _tactics_for(event["mitre_techniques"])
    if not event.get("cve_refs"):
        event["cve_refs"] = _cves_in(signature, raw)
    return event


def enrich_threats(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for e in events:
        enrich_threat(e)
    return events
