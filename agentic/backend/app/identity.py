from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.services.auth import VerifiedLineIdentity, get_or_create_user, verify_liff_id_token
from backend.app.services.liff_session import verify_liff_session

from .config import get_settings
from .database import get_db


@dataclass(slots=True)
class ResolvedIdentity:
    line_user_id: str
    display_name: str
    auth_mode: str
    verified_identity: VerifiedLineIdentity | None = None


def _maybe_verify_session(token: str | None) -> VerifiedLineIdentity | None:
    if not token:
        return None
    try:
        return verify_liff_session(token)
    except HTTPException:
        return None


async def resolve_request_user(
    request: Request,
    db: Session = Depends(get_db),
    x_line_user_id: str | None = Header(default=None),
    x_display_name: str | None = Header(default=None),
    x_line_id_token: str | None = Header(default=None),
    x_app_session: str | None = Header(default=None),
):
    settings = get_settings()
    cookie_session = request.cookies.get("app_session")
    verified = _maybe_verify_session(cookie_session) or _maybe_verify_session(x_app_session)

    if verified is not None:
        identity = ResolvedIdentity(
            line_user_id=verified.line_user_id,
            display_name=verified.display_name,
            auth_mode="app_session",
            verified_identity=verified,
        )
    elif x_line_id_token:
        verified = await verify_liff_id_token(x_line_id_token)
        identity = ResolvedIdentity(
            line_user_id=verified.line_user_id,
            display_name=verified.display_name,
            auth_mode="liff_id_token",
            verified_identity=verified,
        )
    elif x_line_user_id and settings.allow_demo_headers:
        identity = ResolvedIdentity(
            line_user_id=x_line_user_id,
            display_name=x_display_name or "Demo User",
            auth_mode="header_demo",
        )
    elif settings.allow_demo_headers:
        identity = ResolvedIdentity(
            line_user_id="agentic-demo-user",
            display_name=x_display_name or "Demo User",
            auth_mode="dev_default",
        )
    else:
        raise HTTPException(status_code=401, detail="LINE authentication is required")

    request.state.agentic_auth_mode = identity.auth_mode
    request.state.agentic_verified_identity = identity.verified_identity
    return get_or_create_user(db, line_user_id=identity.line_user_id, display_name=identity.display_name)
