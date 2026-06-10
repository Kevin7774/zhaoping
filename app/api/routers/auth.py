from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_org, get_current_user, session_response, upsert_user_for_company_email
from app.db.session import get_project_session
from app.models import Organization, User
from app.schemas.auth import AuthLoginRequest, AuthSessionResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthSessionResponse)
def login_with_company_email(
    request: AuthLoginRequest,
    session: Session = Depends(get_project_session),
) -> AuthSessionResponse:
    user = upsert_user_for_company_email(session, email=request.email, name=request.name)
    org = session.get(Organization, user.org_id)
    return session_response(user, org)


@router.get("/me", response_model=AuthSessionResponse)
def get_current_session(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
) -> AuthSessionResponse:
    return session_response(current_user, current_org)
