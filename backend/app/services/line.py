from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any

import httpx
from fastapi import HTTPException

from ..config import settings
from .storage import infer_source_type_from_mime, store_attachment_bytes
from .video_intake import enrich_attachment_with_video_probe


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

    source_type = infer_source_type_from_mime(mime_type)
    payload = store_attachment_bytes(
        content=content,
        mime_type=mime_type,
        source_type=source_type,
        source_id=message_id,
        user_scope=line_user_id,
    )
    if source_type == "video":
        payload = enrich_attachment_with_video_probe(payload, content=content, mime_type=mime_type)
    if mime_type.startswith("image/"):
        payload["content_base64"] = base64.b64encode(content).decode("utf-8")
    return content, payload


def build_text_message(text: str, *, quick_reply: list[object] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"type": "text", "text": text[:4900]}
    if quick_reply:
        message["quickReply"] = {"items": _build_quick_reply_items(quick_reply)}
    return message


def build_draft_flex_message(
    *,
    title: str,
    subtitle: str,
    lines: list[str],
    primary_label: str,
    primary_text: str,
    secondary_label: str = "打開今日",
    secondary_uri: str | None = None,
    ) -> dict[str, Any]:
    footer_contents: list[dict[str, Any]] = [
        {
            "type": "button",
            "style": "primary",
            "height": "sm",
            "color": "#10B981",
            "action": {"type": "message", "label": primary_label[:20], "text": primary_text[:300]},
        }
    ]
    if secondary_uri:
        footer_contents.append(
            {
                "type": "button",
                "style": "link",
                "height": "sm",
                "action": {"type": "uri", "label": secondary_label[:20], "uri": secondary_uri},
            }
        )
    return {
        "type": "flex",
        "altText": f"{title} {subtitle}",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": title, "weight": "bold", "size": "lg", "wrap": True},
                    {"type": "text", "text": subtitle, "size": "sm", "color": "#6B7280", "wrap": True},
                ],
                "paddingBottom": "8px",
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [{"type": "text", "text": line, "size": "sm", "wrap": True} for line in lines[:4]],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": footer_contents,
            },
        },
    }


def build_action_flex_message(
    *,
    title: str,
    subtitle: str,
    lines: list[str],
    primary_label: str,
    primary_uri: str | None = None,
    primary_text: str | None = None,
    secondary_label: str | None = None,
    secondary_uri: str | None = None,
) -> dict[str, Any]:
    footer_contents: list[dict[str, Any]] = []
    if primary_uri:
        footer_contents.append(
            {
                "type": "button",
                "style": "primary",
                "height": "sm",
                "color": "#10B981",
                "action": {"type": "uri", "label": primary_label[:20], "uri": primary_uri},
            }
        )
    elif primary_text:
        footer_contents.append(
            {
                "type": "button",
                "style": "primary",
                "height": "sm",
                "color": "#10B981",
                "action": {"type": "message", "label": primary_label[:20], "text": primary_text[:300]},
            }
        )
    if secondary_label and secondary_uri:
        footer_contents.append(
            {
                "type": "button",
                "style": "link",
                "height": "sm",
                "action": {"type": "uri", "label": secondary_label[:20], "uri": secondary_uri},
            }
        )
    bubble: dict[str, Any] = {
        "type": "flex",
        "altText": f"{title} {subtitle}".strip(),
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": title, "weight": "bold", "size": "lg", "wrap": True},
                    {"type": "text", "text": subtitle, "size": "sm", "color": "#6B7280", "wrap": True},
                ],
                "paddingBottom": "8px",
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [{"type": "text", "text": line, "size": "sm", "wrap": True} for line in lines[:4]],
            },
        },
    }
    if footer_contents:
        bubble["contents"]["footer"] = {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": footer_contents,
        }
    return bubble


def build_liff_tab_url(tab: str) -> str | None:
    if not settings.liff_channel_id:
        return None
    safe_tab = (tab or "today").strip() or "today"
    return f"https://liff.line.me/{settings.liff_channel_id}?tab={safe_tab}"


async def reply_line_message(
    reply_token: str,
    text: str | None = None,
    *,
    quick_reply: list[object] | None = None,
    flex_message: dict[str, Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> None:
    if not settings.line_channel_access_token:
        return
    payload_messages = _normalize_messages(text=text, quick_reply=quick_reply, flex_message=flex_message, messages=messages)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={"Authorization": f"Bearer {settings.line_channel_access_token}"},
            json={"replyToken": reply_token, "messages": payload_messages},
        )
        response.raise_for_status()


async def push_line_message(
    line_user_id: str,
    text: str | None = None,
    *,
    flex_message: dict[str, Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> None:
    if not settings.line_channel_access_token:
        return
    payload_messages = _normalize_messages(text=text, quick_reply=None, flex_message=flex_message, messages=messages)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.line.me/v2/bot/message/push",
            headers={"Authorization": f"Bearer {settings.line_channel_access_token}"},
            json={"to": line_user_id, "messages": payload_messages},
        )
        response.raise_for_status()


def _normalize_messages(
    *,
    text: str | None,
    quick_reply: list[object] | None,
    flex_message: dict[str, Any] | None,
    messages: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    payload_messages: list[dict[str, Any]] = []
    if messages:
        payload_messages.extend(messages)
    else:
        if flex_message:
            payload_messages.append(flex_message)
        if text:
            payload_messages.append(build_text_message(text, quick_reply=quick_reply))
    if not payload_messages:
        raise ValueError("LINE message payload is empty")
    return payload_messages[:5]


def _build_quick_reply_items(quick_reply: list[object]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in quick_reply[:13]:
        if isinstance(item, dict):
            items.append(item)
            continue
        label = str(item)
        items.append(
            {
                "type": "action",
                "action": {
                    "type": "message",
                    "label": label[:20],
                    "text": label[:300],
                },
            }
        )
    return items
