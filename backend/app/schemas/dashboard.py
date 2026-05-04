from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class OverviewKpis(BaseModel):
    total_branches: int
    online_collectors: int
    total_flows: int
    allowed_flows: int
    blocked_flows: int
    ids_ips_events: int
    high_risk_events: int
    medium_risk_events: int
    low_risk_events: int
    unique_clients: int
    top_suspicious_branch: str | None = None
    top_suspicious_client: str | None = None


class TrendPoint(BaseModel):
    t: datetime
    value: float


class TrendSeries(BaseModel):
    name: str
    points: list[TrendPoint]


class TrendResponse(BaseModel):
    timeframe: str
    bucket_label: str
    series: list[TrendSeries]


class BranchHeatRow(BaseModel):
    branch_id: UUID
    branch_code: str
    branch_name: str
    flows: int
    blocked: int
    ids_ips: int
    high_risk: int
    suspicion_score: float


class OverviewResponse(BaseModel):
    timeframe: str
    kpis: OverviewKpis
    branch_heat: list[BranchHeatRow]


class TopItem(BaseModel):
    label: str
    value: int


class TopResponse(BaseModel):
    timeframe: str
    items: list[TopItem]


class FlowEvent(BaseModel):
    event_id: str
    event_hash: str
    branch_code: str
    branch_name: str
    event_time: datetime
    action: str
    risk: str
    severity: str
    policy_type: str
    policy_name: str | None
    source_ip: str
    source_hostname: str | None
    destination_ip: str
    destination_port: int | None
    destination_hostname: str | None
    destination_country: str | None
    protocol: str | None
    application: str | None
    application_category: str | None
    bytes_up: int
    bytes_down: int


class ThreatEvent(FlowEvent):
    signature: str
    threat_category: str | None
    client_ip: str | None
    mitre_techniques: list[str] = []
    mitre_tactics: list[str] = []
    cve_refs: list[str] = []


class EventsPage(BaseModel):
    timeframe: str
    items: list[Any]   # FlowEvent or ThreatEvent depending on endpoint
    next_offset: int | None
    total_estimate: int


class ClientSummary(BaseModel):
    client_ip: str
    branch_code: str
    flows: int
    blocked: int
    threats: int
    bytes_up: int
    bytes_down: int


class ClientList(BaseModel):
    timeframe: str
    items: list[ClientSummary]
