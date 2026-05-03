from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class BranchCredentialsIn(BaseModel):
    """Plaintext creds from the client. Encrypted before persisting."""
    username: str | None = None
    password: str | None = None
    api_key: str | None = None
    token: str | None = None


class BranchCredentialsMeta(BaseModel):
    """What we tell the frontend about creds — never the plaintext."""
    has_username: bool = False
    has_password: bool = False
    has_api_key: bool = False
    has_token: bool = False


class BranchBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    branch_code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    country: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=128)
    tags: list[str] = Field(default_factory=list)
    controller_url: str = Field(min_length=1, max_length=512)
    site_id: str = Field(default="default", min_length=1, max_length=128)
    gateway_model: str | None = Field(default=None, max_length=64)
    auth_method: Literal["local", "api_key"] = "local"
    ssl_verify: bool = True
    polling_interval_seconds: int = Field(default=30, ge=10, le=3600)
    enabled: bool = True
    notes: str | None = None


class BranchCreate(BranchBase):
    credentials: BranchCredentialsIn = Field(default_factory=BranchCredentialsIn)


class BranchUpdate(BaseModel):
    name: str | None = None
    country: str | None = None
    city: str | None = None
    tags: list[str] | None = None
    controller_url: str | None = None
    site_id: str | None = None
    gateway_model: str | None = None
    auth_method: Literal["local", "api_key"] | None = None
    ssl_verify: bool | None = None
    polling_interval_seconds: int | None = Field(default=None, ge=10, le=3600)
    enabled: bool | None = None
    notes: str | None = None
    credentials: BranchCredentialsIn | None = None


class CollectorStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str = "unknown"
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


class BranchOut(BranchBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    credentials_meta: BranchCredentialsMeta = Field(default_factory=BranchCredentialsMeta)
    status: CollectorStatusOut | None = None


class BranchListOut(BaseModel):
    items: list[BranchOut]
    total: int


class TestConnectionResult(BaseModel):
    ok: bool
    endpoint_used: str | None = None
    unifi_os_version: str | None = None
    network_app_version: str | None = None
    sites_discovered: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None
    is_mock: bool = False
