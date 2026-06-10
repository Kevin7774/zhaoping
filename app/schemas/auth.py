from __future__ import annotations

from app.schemas.common import CamelModel


class AuthLoginRequest(CamelModel):
    email: str
    name: str | None = None


class AuthUserResponse(CamelModel):
    user_id: str
    org_id: str
    email: str
    name: str | None = None


class AuthOrgResponse(CamelModel):
    org_id: str
    name: str
    domain: str


class AuthSessionResponse(CamelModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse
    org: AuthOrgResponse
