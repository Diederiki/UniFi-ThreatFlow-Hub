from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CollectorBranchStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    branch_id: UUID
    branch_name: str
    branch_code: str
    enabled: bool
    status: str
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None
    last_duration_ms: int | None = None
    last_event_count: int | None = None
    last_endpoint_used: str | None = None
    unifi_os_version: str | None = None
    network_app_version: str | None = None
    collector_version: str | None = None
    updated_at: datetime | None = None


class CollectorStatusList(BaseModel):
    items: list[CollectorBranchStatus]
    total: int


class CollectorRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: UUID
    started_at: datetime
    finished_at: datetime | None
    status: str
    event_count: int | None
    error_message: str | None
    endpoint_used: str | None
    duration_ms: int | None


class CollectorRunsList(BaseModel):
    items: list[CollectorRunOut]
