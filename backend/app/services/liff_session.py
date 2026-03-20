from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

from fastapi import HTTPException

from ..config import settings
from .auth import VerifiedLineIdentity


def _session_secret() -> bytes:
    secret = settings.liff_session_secret or settings.line_channel_secret
    if not secret:
        raise HTTPException(status_code=503, detail="LIFF session secret is not configured")
    return secret.encode("utf-8")


def _b64url_encode(raw: bytes) -> str:
    return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return urlsafe_b64decode((raw + padding).encode("ascii"))


def create_liff_session(identity: VerifiedLineIdentity) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=max(settings.liff_session_ttl_hours, 1))
    payload = {
        "sub": identity.line_user_id,
        "name": identity.display_name,
        "picture": identity.picture_url,
        "exp": int(expires_at.timestamp()),
        "v": 1,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_token = _b64url_encode(payload_bytes)
    signature = hmac.new(_session_secret(), payload_token.encode("ascii"), hashlib.sha256).digest()
    token = f"{payload_token}.{_b64url_encode(signature)}"
    return token, expires_at


def verify_liff_session(token: str) -> VerifiedLineIdentity:
    try:
        payload_token, signature_token = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid app session token") from exc

    expected_signature = hmac.new(_session_secret(), payload_token.encode("ascii"), hashlib.sha256).digest()
    actual_signature = _b64url_decode(signature_token)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise HTTPException(status_code=401, detail="Invalid app session token")

    try:
        payload = json.loads(_b64url_decode(payload_token).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid app session token") from exc

    expires_at = payload.get("exp")
    line_user_id = payload.get("sub")
    if not isinstance(expires_at, int) or not line_user_id:
        raise HTTPException(status_code=401, detail="Invalid app session token")
    if expires_at < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=401, detail="App session token expired")

    return VerifiedLineIdentity(
        line_user_id=str(line_user_id),
        display_name=str(payload.get("name") or "LINE User"),
        picture_url=payload.get("picture"),
    )
