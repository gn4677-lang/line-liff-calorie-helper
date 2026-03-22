from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InboundEvent


def line_event_external_id(event: dict[str, Any]) -> str:
    message = event.get("message") or {}
    message_id = str(message.get("id") or "").strip()
    if message_id:
        return message_id
    encoded = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def enqueue_line_event(
    db: Session,
    *,
    event: dict[str, Any],
    line_user_id: str,
    reply_token: str | None,
    trace_id: str | None,
) -> tuple[InboundEvent, bool]:
    external_event_id = line_event_external_id(event)
    existing = db.scalar(
        select(InboundEvent).where(InboundEvent.source == "line_webhook", InboundEvent.external_event_id == external_event_id)
    )
    if existing is not None:
        return existing, False

    row = InboundEvent(
        id=str(uuid.uuid4()),
        source="line_webhook",
        external_event_id=external_event_id,
        line_user_id=line_user_id,
        reply_token=reply_token,
        trace_id=trace_id,
        payload=event,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, True
