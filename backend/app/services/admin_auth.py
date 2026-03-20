from __future__ import annotations

from datetime import timedelta, timezone
from hashlib import sha256
from secrets import compare_digest, token_urlsafe

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import AdminSession, utcnow


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def ensure_admin_auth_configured() -> None:
    if settings.observability_admin_passcode:
        return
    raise HTTPException(status_code=503, detail="Observability admin passcode is not configured")


def validate_admin_passcode(passcode: str) -> bool:
    ensure_admin_auth_configured()
    return compare_digest(passcode, settings.observability_admin_passcode or "")


def create_admin_session(db: Session, *, label: str = "observability-admin") -> tuple[str, AdminSession]:
    ensure_admin_auth_configured()
    token = token_urlsafe(32)
    now = utcnow()
    row = AdminSession(
        token_hash=_token_hash(token),
        label=label,
        status="active",
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.observability_admin_session_ttl_hours),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return token, row


def get_admin_session(db: Session, token: str) -> AdminSession | None:
    ensure_admin_auth_configured()
    row = db.query(AdminSession).filter(AdminSession.token_hash == _token_hash(token)).one_or_none()
    if row is None:
        return None
    now = utcnow()
    if row.status != "active":
        return None
    expires_at = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at.astimezone(timezone.utc)
    if expires_at <= now:
        row.status = "expired"
        db.add(row)
        db.commit()
        return None
    row.last_seen_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def revoke_admin_session(db: Session, token: str) -> AdminSession | None:
    ensure_admin_auth_configured()
    row = db.query(AdminSession).filter(AdminSession.token_hash == _token_hash(token)).one_or_none()
    if row is None:
        return None
    row.status = "revoked"
    row.last_seen_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def require_admin_session(
    x_admin_session: str | None = Header(default=None, alias="X-Admin-Session"),
    db: Session = Depends(get_db),
) -> AdminSession:
    if not x_admin_session:
        raise HTTPException(status_code=401, detail="Missing admin session")
    session = get_admin_session(db, x_admin_session)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired admin session")
    return session
