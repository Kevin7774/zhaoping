from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_project_session
from app.models import Organization, User
from app.schemas.auth import AuthOrgResponse, AuthSessionResponse, AuthUserResponse

EMAIL_RE = re.compile(r"^[^@\s]+@([^@\s]+\.[^@\s]+)$")
PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "icloud.com",
    "me.com",
    "qq.com",
    "163.com",
    "126.com",
    "sina.com",
    "sohu.com",
    "foxmail.com",
}


def normalize_company_email(email: str) -> tuple[str, str]:
    normalized = " ".join(str(email or "").strip().lower().split())
    match = EMAIL_RE.match(normalized)
    if not match:
        raise HTTPException(status_code=422, detail="A valid company email is required.")
    domain = match.group(1)
    allowed_domains = _allowed_company_domains()
    if allowed_domains and domain not in allowed_domains:
        raise HTTPException(status_code=422, detail="Email domain is not allowed for company login.")
    if not allowed_domains and domain in PUBLIC_EMAIL_DOMAINS and os.getenv("ALLOW_PUBLIC_EMAIL_LOGIN") != "1":
        raise HTTPException(status_code=422, detail="A company email is required; public email domains are not allowed.")
    return normalized, domain


def upsert_user_for_company_email(session: Session, *, email: str, name: str | None = None) -> User:
    normalized_email, domain = normalize_company_email(email)
    org_id = _org_id_for_domain(domain)
    user_id = _user_id_for_email(normalized_email)
    org = session.get(Organization, org_id)
    if org is None:
        org = Organization(id=org_id, domain=domain, name=domain)
        session.add(org)
    user = session.get(User, user_id)
    if user is None:
        user = User(id=user_id, org_id=org_id, email=normalized_email, name=_clean_name(name))
        session.add(user)
    else:
        user.org_id = org_id
        user.email = normalized_email
        if _clean_name(name):
            user.name = _clean_name(name)
    session.commit()
    session.refresh(user)
    return user


def create_access_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "org": user.org_id,
        "email": user.email,
        "iat": int(time.time()),
    }
    encoded_payload = _b64encode(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    signature = _sign(encoded_payload)
    return f"{encoded_payload}.{signature}"


def session_response(user: User, org: Organization | None = None) -> AuthSessionResponse:
    organization = org or user.organization
    return AuthSessionResponse(
        access_token=create_access_token(user),
        user=AuthUserResponse(user_id=user.id, org_id=user.org_id, email=user.email, name=user.name),
        org=AuthOrgResponse(org_id=organization.id, name=organization.name, domain=organization.domain),
    )


def get_optional_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: Session = Depends(get_project_session),
) -> User | None:
    if not authorization:
        return None
    token = _bearer_token(authorization)
    payload = _decode_token(token)
    user_id = str(payload.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid auth token.")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Authenticated user no longer exists.")
    return user


def get_current_user(current_user: User | None = Depends(get_optional_current_user)) -> User:
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return current_user


def get_current_org(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_project_session),
) -> Organization:
    org = session.get(Organization, current_user.org_id)
    if org is None:
        raise HTTPException(status_code=401, detail="Authenticated organization no longer exists.")
    return org


def _decode_token(token: str) -> dict[str, Any]:
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid auth token.") from exc
    expected = _sign(encoded_payload)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid auth token signature.")
    try:
        payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid auth token payload.") from exc
    return payload if isinstance(payload, dict) else {}


def _bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Authorization must use Bearer token.")
    return token.strip()


def _allowed_company_domains() -> set[str]:
    raw = os.getenv("COMPANY_EMAIL_DOMAINS", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _org_id_for_domain(domain: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", domain.lower()).strip("_")
    return f"org_{slug[:52]}"


def _user_id_for_email(email: str) -> str:
    return f"user_{hashlib.sha256(email.encode('utf-8')).hexdigest()[:16]}"


def _clean_name(name: str | None) -> str | None:
    value = str(name or "").strip()
    return value[:128] if value else None


def _token_secret() -> bytes:
    secret = os.getenv("AUTH_TOKEN_SECRET")
    if secret:
        return secret.encode("utf-8")
    app_env = str(os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("ZHAOPING_ENV") or "").lower()
    if app_env in {"production", "prod"}:
        raise RuntimeError("AUTH_TOKEN_SECRET is required in production.")
    return b"zhaoping-local-dev-auth-secret"


def _sign(encoded_payload: str) -> str:
    return _b64encode(hmac.new(_token_secret(), encoded_payload.encode("utf-8"), hashlib.sha256).digest())


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
