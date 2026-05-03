from typing import Literal
from pydantic import BaseModel, Field, HttpUrl

from app.schemas.users import RoleLiteral


class SsoConfig(BaseModel):
    """Public SSO config — secret is never sent to the frontend."""
    enabled: bool = False
    tenant_id: str = ""
    client_id: str = ""
    redirect_uri: str = ""
    auto_provision: bool = True
    default_role: RoleLiteral = "viewer"
    has_client_secret: bool = False


class SsoConfigUpdate(BaseModel):
    enabled: bool = False
    tenant_id: str = Field(default="", max_length=128)
    client_id: str = Field(default="", max_length=128)
    # Empty string means "keep existing secret". A new value rotates it.
    client_secret: str = Field(default="", max_length=512)
    redirect_uri: str = Field(default="", max_length=512)
    auto_provision: bool = True
    default_role: RoleLiteral = "viewer"


class SsoInfo(BaseModel):
    """What the login page needs to know."""
    enabled: bool
    button_label: str = "Sign in with Microsoft"
    start_url: str = "/api/auth/sso/start"
