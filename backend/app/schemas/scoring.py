from pydantic import BaseModel, Field
from uuid import UUID


class ScoringWeightsModel(BaseModel):
    high_risk_event: float = Field(default=10.0)
    medium_risk_event: float = Field(default=5.0)
    low_risk_event: float = Field(default=1.0)
    blocked_event: float = Field(default=4.0)
    repeated_client: float = Field(default=8.0)
    outbound_suspicious: float = Field(default=6.0)
    malware_botnet: float = Field(default=15.0)
    large_transfer: float = Field(default=5.0)
    known_false_positive: float = Field(default=-3.0)


class SuspiciousBranch(BaseModel):
    branch_id: UUID
    branch_code: str
    branch_name: str
    flows: int
    blocked: int
    ids_ips: int
    high_risk: int
    medium_risk: int
    low_risk: int
    score: float


class SuspiciousClient(BaseModel):
    client_ip: str
    branch_code: str
    flows: int
    blocked: int
    threats: int
    score: float


class SuspiciousDestination(BaseModel):
    destination_ip: str
    destination_hostname: str | None
    destination_country: str | None
    flows: int
    threats: int
    score: float


class SuspiciousList(BaseModel):
    timeframe: str
    items: list


class SuspiciousBranchList(BaseModel):
    timeframe: str
    items: list[SuspiciousBranch]


class SuspiciousClientList(BaseModel):
    timeframe: str
    items: list[SuspiciousClient]


class SuspiciousDestinationList(BaseModel):
    timeframe: str
    items: list[SuspiciousDestination]
