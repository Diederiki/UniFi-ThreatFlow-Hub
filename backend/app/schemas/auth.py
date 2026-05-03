from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    email: EmailStr
    name: str | None = None
    role: str


class CurrentUser(BaseModel):
    email: EmailStr
    name: str | None = None
    role: str
