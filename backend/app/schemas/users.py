from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

ROLES = ("admin", "operator", "viewer")
RoleLiteral = Literal["admin", "operator", "viewer"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str | None = None
    role: RoleLiteral
    enabled: bool
    auth_method: str
    sso_subject: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserList(BaseModel):
    items: list[UserOut]
    total: int


class UserCreate(BaseModel):
    email: EmailStr
    name: str | None = None
    role: RoleLiteral = "viewer"
    enabled: bool = True
    password: str = Field(min_length=8, max_length=255)


class UserUpdate(BaseModel):
    name: str | None = None
    role: RoleLiteral | None = None
    enabled: bool | None = None


class PasswordReset(BaseModel):
    """Admin sets a new password for any user."""
    new_password: str = Field(min_length=8, max_length=255)


class ChangePassword(BaseModel):
    """Self-service: caller proves they know the current password."""
    current_password: str
    new_password: str = Field(min_length=8, max_length=255)


class ProfileUpdate(BaseModel):
    name: str | None = None
