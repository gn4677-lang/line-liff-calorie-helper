from __future__ import annotations

import base64
import hashlib
import hmac

import httpx
from fastapi import HTTPException

from ..config import settings
from .storage import store_attachment_bytes


def verify_line_signature(body: bytes, signature: str | None) -> bool:
    if not settings.line_channel_secret:
        return True
    if not signature:
        return False
    digest = hmac.new(settings.line_channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    computed = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(computed, signature)


async def fetch_line_content(message_id: str, *, line_user_id: str) -> tuple[bytes, dict]:
    if not settings.line_channel_access_token:
        raise HTTPException(status_code=503, detail="LINE content retrieval is not configured")
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.get(
            f"https://api-data.line.me/v2/bot/message/{message_id}/content",
            headers={"Authorization": f"Bearer {settings.line_channel_access_token}"},
        )
        response.raise_for_status()
        content = response.content
        mime_type = response.headers.get("content-type", "application/octet-stream")

    source_type = "image" if mime_type.startswith("image/") else "audio" if mime_type.startswith("audio/") else "file"
    payload = store_attachment_bytes(
        content=content,
        mime_type=mime_type,
        source_type=source_type,
        source_id=message_id,
        user_scope=line_user_id,
    )
    if mime_type.startswith("image/"):
        payload["content_base64"] = base64.b64encode(content).decode("utf-8")
    return content, payload


async def reply_line_message(reply_token: str, text: str) -> None:
    if not settings.line_channel_access_token:
        return
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={"Authorization": f"Bearer {settings.line_channel_access_token}"},
            json={"replyToken": reply_token, "messages": [{"type": "text", "text": text[:4900]}]},
        )
        response.raise_for_status()
