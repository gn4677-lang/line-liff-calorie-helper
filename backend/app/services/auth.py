from __future__ import annotations

from dataclasses import dataclass

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Preference, ReportingBias, User


LINE_VERIFY_ID_TOKEN_URL = "https://api.line.me/oauth2/v2.1/verify"


@dataclass
class VerifiedLineIdentity:
    line_user_id: str
    display_name: str
    picture_url: str | None = None


def get_or_create_user(db: Session, line_user_id: str, display_name: str = "Demo User") -> User:
    user = db.scalar(select(User).where(User.line_user_id == line_user_id))
    if user:
        if display_name and user.display_name != display_name:
            user.display_name = display_name
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    user = User(line_user_id=line_user_id, display_name=display_name, daily_calorie_target=settings.default_daily_calorie_target)
    db.add(user)
    db.flush()
    db.add(Preference(user_id=user.id))
    db.add(ReportingBias(user_id=user.id))
    db.commit()
    db.refresh(user)
    return user


async def verify_liff_id_token(id_token: str) -> VerifiedLineIdentity:
    client_id = resolve_line_login_channel_id()
    if not client_id:
        raise HTTPException(status_code=503, detail="LIFF auth is not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            LINE_VERIFY_ID_TOKEN_URL,
            data={"id_token": id_token, "client_id": client_id},
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="Invalid LIFF ID token")

    payload = response.json()
    line_user_id = payload.get("sub")
    if not line_user_id:
        raise HTTPException(status_code=401, detail="LIFF ID token did not include a LINE user ID")

    return VerifiedLineIdentity(
        line_user_id=line_user_id,
        display_name=payload.get("name") or "LINE User",
        picture_url=payload.get("picture"),
    )


def resolve_line_login_channel_id() -> str | None:
    if settings.line_login_channel_id:
        return settings.line_login_channel_id
    if settings.liff_channel_id:
        return settings.liff_channel_id.split("-", 1)[0]
    if settings.line_channel_id:
        return settings.line_channel_id
    return None
