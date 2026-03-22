from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, update

from backend.app.api import routes as legacy_routes
from backend.app.models import InboundEvent, User, utcnow
from backend.app.services.auth import get_or_create_user
from backend.app.services.line import (
    build_action_flex_message,
    build_liff_tab_url,
    fetch_line_content,
    send_line_response,
)

from .cohort import decide_agentic_cohort
from .config import get_settings
from .contracts import (
    AgentInput,
    AgentInputSource,
    AttachmentRef,
    InputModality,
    LocationRef,
    PostbackPayload,
    SourceMetadata,
)
from .database import SessionLocal
from .runtime import agent_loop, state_assembler, store


settings = get_settings()
MAX_INBOUND_RETRIES = 4
_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None
_processed_scan_keys: set[str] = set()


@dataclass(slots=True)
class ScheduledScanWindow:
    label: str
    hour: int
    minute: int


class AgenticWorker:
    windows = (
        ScheduledScanWindow("breakfast_window", 7, 30),
        ScheduledScanWindow("lunch_window", 11, 30),
        ScheduledScanWindow("dinner_window", 17, 30),
        ScheduledScanWindow("night_window", 20, 30),
    )

    def due_windows(self, now: datetime) -> list[ScheduledScanWindow]:
        return [window for window in self.windows if window.hour == now.hour and window.minute == now.minute]


def start_worker() -> None:
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(target=run_worker_forever, name="agentic-worker", daemon=True)
    _worker_thread.start()


def stop_worker() -> None:
    _stop_event.set()


def run_worker_forever() -> None:
    while not _stop_event.is_set():
        try:
            process_inbound_events_once()
        except Exception:
            pass
        try:
            process_scheduled_scans_once()
        except Exception:
            pass
        _stop_event.wait(1.0)


def process_inbound_events_once(limit: int | None = None) -> None:
    batch_size = max(1, limit or 8)
    with SessionLocal() as db:
        for event in _claim_inbound_events(db, batch_size):
            _process_one_inbound_event(db, event)


def process_scheduled_scans_once(*, now: datetime | None = None, limit_users: int | None = None) -> int:
    local_now = now or datetime.now(ZoneInfo(settings.timezone))
    worker = AgenticWorker()
    due = worker.due_windows(local_now)
    if not due:
        return 0
    processed = 0
    for window in due:
        key = f"{window.label}:{local_now.strftime('%Y%m%d%H%M')}"
        if key in _processed_scan_keys:
            continue
        processed += _process_due_window(window, local_now, limit_users=limit_users)
        _processed_scan_keys.add(key)
    _prune_scan_keys(local_now)
    return processed


def _claim_inbound_events(db, limit: int) -> list[InboundEvent]:
    now = utcnow()
    lease_until = now + timedelta(seconds=60)
    candidate_ids = list(
        db.scalars(
            select(InboundEvent.id)
            .where(
                or_(
                    InboundEvent.status == "pending",
                    and_(InboundEvent.status == "running", InboundEvent.lease_expires_at.is_not(None), InboundEvent.lease_expires_at < now),
                )
            )
            .order_by(InboundEvent.created_at)
            .limit(max(limit * 4, limit))
        )
    )
    claimed: list[InboundEvent] = []
    for event_id in candidate_ids:
        claim_token = str(uuid.uuid4())
        result = db.execute(
            update(InboundEvent)
            .where(InboundEvent.id == event_id)
            .where(
                or_(
                    InboundEvent.status == "pending",
                    and_(InboundEvent.status == "running", InboundEvent.lease_expires_at.is_not(None), InboundEvent.lease_expires_at < now),
                )
            )
            .values(status="running", claimed_at=now, lease_expires_at=lease_until, claim_token=claim_token)
        )
        db.commit()
        if result.rowcount:
            event = db.get(InboundEvent, event_id)
            if event is not None:
                claimed.append(event)
        if len(claimed) >= limit:
            break
    return claimed


def _process_due_window(window: ScheduledScanWindow, now: datetime, *, limit_users: int | None = None) -> int:
    processed = 0
    with SessionLocal() as db:
        query = select(User).where(User.line_user_id.is_not(None)).order_by(User.id)
        if limit_users is not None:
            query = query.limit(max(1, limit_users))
        users = db.execute(query).scalars().all()
        for user in users:
            decision = decide_agentic_cohort(user_id=user.id, line_user_id=user.line_user_id)
            if not decision.enabled:
                continue
            result = agent_loop.process_proactive(
                db,
                user,
                scheduled_window=window.label,
                cohort=decision.cohort,
                core_version=decision.core_version,
            )
            if result is None:
                continue
            trace_id = store.persist_turn(db, result, cohort=decision.cohort, core_version=decision.core_version)
            if (
                user.line_user_id
                and result.delivery
                and result.delivery.should_send
                and result.delivery.delivery_action.value != "suppress"
            ):
                _deliver_agentic_result(user, None, result, trace_id=trace_id)
            processed += 1
    return processed


def _process_one_inbound_event(db, event: InboundEvent) -> None:
    try:
        user = get_or_create_user(db, line_user_id=event.line_user_id, display_name="LINE User")
        decision = decide_agentic_cohort(user_id=user.id, line_user_id=user.line_user_id)
        if not decision.enabled:
            asyncio.run(
                legacy_routes.process_line_event_payload(
                    db,
                    event.payload or {},
                    trace_id=event.trace_id or event.id,
                    reply_token=event.reply_token,
                )
            )
            _complete_event(db, event)
            return

        agent_input = _agent_input_from_event(event.payload or {}, user=user, trace_id=event.trace_id or event.id)
        result = agent_loop.process(db, user, agent_input, cohort=decision.cohort, core_version=decision.core_version)
        trace_id = store.persist_turn(db, result, cohort=decision.cohort, core_version=decision.core_version)
        if result.delivery and result.delivery.should_send and result.delivery.delivery_action.value != "suppress":
            _deliver_agentic_result(user, event.reply_token, result, trace_id=trace_id)
        elif result.turn.response.message_text:
            _deliver_agentic_result(user, event.reply_token, result, trace_id=trace_id, ignore_delivery_policy=True)
        _complete_event(db, event)
    except Exception as exc:
        _fail_event(db, event, exc)


def _complete_event(db, event: InboundEvent) -> None:
    event.status = "completed"
    event.processed_at = utcnow()
    event.lease_expires_at = None
    event.claim_token = None
    event.last_error = ""
    db.add(event)
    db.commit()


def _fail_event(db, event: InboundEvent, exc: Exception) -> None:
    event.attempt_count += 1
    exhausted = event.attempt_count >= MAX_INBOUND_RETRIES
    event.status = "failed" if exhausted else "pending"
    event.last_error = str(exc)
    event.processed_at = utcnow() if exhausted else None
    event.lease_expires_at = None
    event.claim_token = None
    db.add(event)
    db.commit()


def _deliver_agentic_result(
    user: User,
    reply_token: str | None,
    result,
    *,
    trace_id: str,
    ignore_delivery_policy: bool = False,
) -> None:
    response = result.turn.response
    decision = result.delivery
    text = response.message_text
    if response.followup_question:
        text = f"{text}\n\n{response.followup_question}"
    flex_message = None
    deep_link = response.deep_link or build_liff_tab_url((decision.decision_home.value if decision else "today"))
    if response.hero_card:
        flex_message = build_action_flex_message(
            title=response.hero_card.title,
            subtitle=response.hero_card.body,
            lines=[response.message_text],
            primary_label=response.hero_card.cta_label or "Open",
            primary_uri=deep_link,
        )
    elif decision and not ignore_delivery_policy and decision.delivery_action.value == "line_teaser_to_liff":
        flex_message = build_action_flex_message(
            title="Open your decision home",
            subtitle=decision.why_now,
            lines=[response.message_text],
            primary_label="Open LIFF",
            primary_uri=deep_link,
            secondary_label="Today",
            secondary_uri=build_liff_tab_url("today"),
        )
    quick_reply = response.quick_replies[:4]
    asyncio.run(
        send_line_response(
            line_user_id=user.line_user_id,
            reply_token=reply_token,
            text=text,
            quick_reply=quick_reply,
            flex_message=flex_message,
        )
    )


def _agent_input_from_event(event: dict[str, Any], *, user: User, trace_id: str) -> AgentInput:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    line_user_id = str(source.get("userId") or user.line_user_id or "")
    metadata = SourceMetadata(
        user_id=str(user.id),
        line_user_id=line_user_id or None,
        trace_id=trace_id,
        auth_mode="line_webhook",
    )
    event_type = str(event.get("type") or "message")
    if event_type == "postback":
        payload = _parse_postback_payload(str((event.get("postback") or {}).get("data") or ""))
        return AgentInput(
            source=AgentInputSource.line_postback,
            modalities=[InputModality.postback],
            postback_payload=payload,
            source_metadata=metadata,
        )
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    message_type = str(message.get("type") or "text")
    modalities: list[InputModality] = []
    attachments: list[AttachmentRef] = []
    text = None
    location = None
    if message_type == "text":
        modalities = [InputModality.text]
        text = str(message.get("text") or "")
    elif message_type == "location":
        modalities = [InputModality.location]
        location = LocationRef(
            lat=float(message.get("latitude") or 0.0),
            lng=float(message.get("longitude") or 0.0),
            label=str(message.get("title") or message.get("address") or "").strip() or None,
        )
    elif message_type in {"image", "audio", "video"}:
        modalities = [InputModality(message_type)]
        attachment = _fetch_attachment_sync(str(message.get("id") or ""), line_user_id=line_user_id, modality=message_type)
        if attachment is not None:
            attachments.append(attachment)
    else:
        modalities = [InputModality.system]
        text = json.dumps(event, ensure_ascii=False)
    return AgentInput(
        source=AgentInputSource.line_message,
        modalities=modalities,
        text=text,
        attachments=attachments,
        location=location,
        source_metadata=metadata,
    )


def _fetch_attachment_sync(message_id: str, *, line_user_id: str, modality: str) -> AttachmentRef | None:
    if not message_id:
        return None
    try:
        _, payload = asyncio.run(fetch_line_content(message_id, line_user_id=line_user_id))
    except Exception:
        return AttachmentRef(modality=modality, media_id=message_id, metadata={"fetch_failed": True})
    return AttachmentRef(
        modality=modality,
        media_id=message_id,
        mime_type=str(payload.get("mime_type") or ""),
        storage_provider=str(payload.get("storage_provider") or ""),
        storage_path=str(payload.get("storage_path") or ""),
        local_path=str(payload.get("local_path") or ""),
        url=str(payload.get("url") or "") or None,
        metadata={key: value for key, value in payload.items() if key not in {"mime_type", "storage_provider", "storage_path", "local_path", "url"}},
    )


def _parse_postback_payload(raw: str) -> PostbackPayload:
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return PostbackPayload(
                    action=str(data.get("action") or "noop"),
                    entity_ref=str(data.get("entity_ref") or "") or None,
                    option_key=str(data.get("option_key") or "") or None,
                    decision_context_ref=str(data.get("decision_context_ref") or "") or None,
                    payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
                )
        except json.JSONDecodeError:
            pass
    return PostbackPayload(action=raw or "noop")


def _prune_scan_keys(now: datetime) -> None:
    cutoff = (now - timedelta(days=2)).strftime("%Y%m%d%H%M")
    stale = {key for key in _processed_scan_keys if key.rsplit(":", 1)[-1] < cutoff}
    _processed_scan_keys.difference_update(stale)
