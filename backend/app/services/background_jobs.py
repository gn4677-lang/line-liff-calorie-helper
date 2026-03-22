from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update

from ..config import settings
from ..database import SessionLocal as DefaultSessionLocal
from ..database import get_session_factory
from ..models import InboundEvent, MealLog, SearchJob, User, utcnow
from ..providers.factory import get_ai_provider
from .daily_nudge import process_proactive_pushes_once
from .google_places import search_nearby_places, search_text_places
from .line import build_action_flex_message, build_liff_tab_url, push_line_message
from .observability import finish_task_run, provider_descriptor, record_error_event, route_layers_for_task, start_task_run
from .proactive import build_external_food_job_result, create_notification, upsert_place_cache
from .video_intake import build_video_refinement_result


MAX_JOB_RETRIES = 3
MAX_INBOUND_EVENT_RETRIES = 4
SessionLocal = DefaultSessionLocal
_worker_thread: threading.Thread | None = None
_stop_event = threading.Event()

JOB_TASK_FAMILY = {
    "nearby_places": "nearby_recommendation",
    "menu_precision": "suggested_update_review",
    "brand_lookup": "suggested_update_review",
    "external_food_check": "nutrition_or_food_qa",
    "video_extract": "meal_log_now",
    "video_transcript": "meal_log_now",
    "video_precision": "meal_log_now",
    "video_brand_lookup": "meal_log_now",
}


def start_background_worker() -> None:
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(target=run_worker_forever, name="app-worker", daemon=True)
    _worker_thread.start()


def stop_background_worker() -> None:
    _stop_event.set()


def run_worker_forever() -> None:
    while not _stop_event.is_set():
        try:
            process_inbound_events_once()
            process_search_jobs_once()
            with _session_factory()() as db:
                process_proactive_pushes_once(db)
                process_alert_evaluation_once(db)
        except Exception:
            pass
        _stop_event.wait(settings.background_poll_interval_seconds)


def process_inbound_events_once(limit: int | None = None) -> None:
    batch_size = limit or settings.background_job_batch_size
    with _session_factory()() as db:
        for event in _claim_inbound_events(db, batch_size):
            _process_one_inbound_event(db, event)


def process_search_jobs_once(limit: int | None = None) -> None:
    batch_size = limit or settings.background_job_batch_size
    with _session_factory()() as db:
        for job in _claim_search_jobs(db, batch_size):
            _process_one_job(db, job)


def process_alert_evaluation_once(db: Session) -> None:
    """Evaluate alert rules and create alert events for triggered rules."""
    try:
        from .observability_console import evaluate_alert_rules
        evaluate_alert_rules(db)
    except Exception:
        # Don't let alert evaluation failures stop the worker
        pass


def _claim_inbound_events(db, limit: int) -> list[InboundEvent]:
    now = utcnow()
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
    lease_until = now + timedelta(seconds=settings.background_job_lease_seconds)
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
            .values(
                status="running",
                claimed_at=now,
                lease_expires_at=lease_until,
                claim_token=claim_token,
            )
        )
        db.commit()
        if result.rowcount:
            event = db.get(InboundEvent, event_id)
            if event is not None:
                claimed.append(event)
        if len(claimed) >= limit:
            break
    return claimed


def _claim_search_jobs(db, limit: int) -> list[SearchJob]:
    now = utcnow()
    candidate_ids = list(
        db.scalars(
            select(SearchJob.id)
            .where(
                or_(
                    SearchJob.status == "pending",
                    and_(SearchJob.status == "running", SearchJob.lease_expires_at.is_not(None), SearchJob.lease_expires_at < now),
                )
            )
            .order_by(SearchJob.created_at)
            .limit(max(limit * 4, limit))
        )
    )
    claimed: list[SearchJob] = []
    lease_until = now + timedelta(seconds=settings.background_job_lease_seconds)
    for job_id in candidate_ids:
        claim_token = str(uuid.uuid4())
        result = db.execute(
            update(SearchJob)
            .where(SearchJob.id == job_id)
            .where(
                or_(
                    SearchJob.status == "pending",
                    and_(SearchJob.status == "running", SearchJob.lease_expires_at.is_not(None), SearchJob.lease_expires_at < now),
                )
            )
            .values(
                status="running",
                claimed_at=now,
                lease_expires_at=lease_until,
                claim_token=claim_token,
                started_at=now,
            )
        )
        db.commit()
        if result.rowcount:
            job = db.get(SearchJob, job_id)
            if job is not None:
                claimed.append(job)
        if len(claimed) >= limit:
            break
    return claimed


def _process_one_inbound_event(db, event: InboundEvent) -> None:
    trace_id = event.trace_id or event.id
    message = (event.payload or {}).get("message") or {}
    message_type = message.get("type") if isinstance(message, dict) else None
    provider = get_ai_provider()
    provider_name, model_name = provider_descriptor(provider, task_family="meal_log_now", source_mode=str(message_type or "text"))
    route_layer_1, route_layer_2 = route_layers_for_task("line_webhook_event")
    task_run_id = start_task_run(
        db,
        trace_id=trace_id,
        task_family="line_webhook_event",
        route_layer_1=route_layer_1,
        route_layer_2=route_layer_2,
        provider_name=provider_name or "message_worker",
        model_name=model_name or "line_message_worker",
    )
    try:
        from ..api import routes as route_module

        asyncio.run(route_module.process_line_event_payload(db, event.payload or {}, trace_id=trace_id, reply_token=event.reply_token))
        event.status = "completed"
        event.processed_at = utcnow()
        event.lease_expires_at = None
        event.claim_token = None
        event.last_error = ""
        db.add(event)
        db.commit()
        finish_task_run(
            db,
            task_run_id,
            status="success",
            result_summary={
                "event_id": event.id,
                "message_type": message_type or "",
                "execution_phase": "webhook_worker",
                "ingress_mode": "ack_fast",
                "queue_source": event.source,
                "external_event_id": event.external_event_id,
                "route_policy": "queued_worker_orchestration",
                "route_target": "line_message_orchestration",
            },
        )
    except Exception as exc:
        event.attempt_count += 1
        exhausted = event.attempt_count >= MAX_INBOUND_EVENT_RETRIES
        event.status = "failed" if exhausted else "pending"
        event.last_error = str(exc)
        event.lease_expires_at = None
        event.claim_token = None
        event.processed_at = utcnow() if exhausted else None
        db.add(event)
        db.commit()
        record_error_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            component="inbound_event_worker",
            operation="line_webhook_event",
            severity="error",
            error_code="event_retry_exhausted" if exhausted else "event_retry_pending",
            exception_type=type(exc).__name__,
            message=str(exc),
            retry_count=event.attempt_count,
            fallback_used=not exhausted,
            user_visible_impact="degraded" if not exhausted else "silent_background_failure",
            request_metadata={"event_id": event.id, "external_event_id": event.external_event_id},
        )
        finish_task_run(
            db,
            task_run_id,
            status="failed" if exhausted else "fallback",
            error_type=type(exc).__name__,
            fallback_reason="retry_exhausted" if exhausted else "retry_pending",
            result_summary={
                "event_id": event.id,
                "attempt_count": event.attempt_count,
                "status": event.status,
                "message_type": message_type or "",
                "execution_phase": "webhook_worker",
                "ingress_mode": "ack_fast",
                "queue_source": event.source,
                "external_event_id": event.external_event_id,
                "route_policy": "queued_worker_orchestration",
                "route_target": "line_message_orchestration",
            },
        )


def _process_one_job(db, job: SearchJob) -> None:
    trace_id = str((job.request_payload or {}).get("trace_id") or job.id)
    task_family = JOB_TASK_FAMILY.get(job.job_type, "fallback_ambiguous")
    route_layer_1, route_layer_2 = route_layers_for_task(task_family)
    task_run_id = start_task_run(
        db,
        trace_id=trace_id,
        user_id=job.user_id,
        task_family=task_family,
        route_layer_1=route_layer_1,
        route_layer_2=route_layer_2,
        provider_name="background_worker",
        model_name=job.job_type,
    )
    try:
        if job.job_type == "nearby_places":
            result_payload, suggested_update = _run_nearby_places_job(job.request_payload or {})
        elif job.job_type in {"video_extract", "video_transcript", "video_precision", "video_brand_lookup"}:
            result_payload, suggested_update = _run_video_job(job.request_payload or {})
        elif job.job_type in {"menu_precision", "brand_lookup", "external_food_check"}:
            result_payload, suggested_update = _run_external_food_job(db, job.request_payload or {})
        else:
            result_payload, suggested_update = ({"message": "Unsupported job type"}, {})

        job.result_payload = result_payload
        job.suggested_update = suggested_update
        job.status = "completed"
        job.finished_at = utcnow()
        job.lease_expires_at = None
        job.claim_token = None

        if (job.request_payload or {}).get("notify_on_complete") and (result_payload or suggested_update):
            _maybe_create_job_notification(db, job)

        db.add(job)
        db.commit()
        finish_task_run(
            db,
            task_run_id,
            status="success",
            result_summary={
                "job_type": job.job_type,
                "status": job.status,
                "suggested_update": bool(job.suggested_update),
                "result_payload_keys": list((job.result_payload or {}).keys())[:12],
                "execution_phase": "background_job_worker",
                "ingress_mode": "async_job",
                "route_policy": "background_job_worker",
                "route_target": job.job_type,
            },
        )
    except Exception as exc:
        job.job_retry_count += 1
        exhausted = job.job_retry_count >= MAX_JOB_RETRIES
        job.last_error = str(exc)
        job.status = "failed" if exhausted else "pending"
        job.lease_expires_at = None
        job.claim_token = None
        job.finished_at = utcnow() if exhausted else None
        db.add(job)
        db.commit()
        record_error_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=job.user_id,
            component="background_worker",
            operation=job.job_type,
            severity="error",
            error_code="job_retry_exhausted" if exhausted else "job_retry_pending",
            exception_type=type(exc).__name__,
            message=str(exc),
            retry_count=job.job_retry_count,
            fallback_used=not exhausted,
            user_visible_impact="silent_background_failure" if exhausted else "degraded",
            request_metadata={"job_id": job.id},
        )
        finish_task_run(
            db,
            task_run_id,
            status="failed" if exhausted else "fallback",
            error_type=type(exc).__name__,
            fallback_reason="retry_exhausted" if exhausted else "retry_pending",
            result_summary={
                "job_id": job.id,
                "retry_count": job.job_retry_count,
                "job_status": job.status,
                "execution_phase": "background_job_worker",
                "ingress_mode": "async_job",
                "route_policy": "background_job_worker",
                "route_target": job.job_type,
            },
        )


def _run_nearby_places_job(request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    lat = request_payload.get("lat")
    lng = request_payload.get("lng")
    query = request_payload.get("query")
    meal_type = request_payload.get("meal_type")

    if lat is not None and lng is not None:
        places = search_nearby_places(lat=float(lat), lng=float(lng), meal_type=meal_type)
    elif query:
        places = search_text_places(query=query)
    else:
        places = []

    with _session_factory()() as db:
        upsert_place_cache(db, places)

    result = {"places": places[:8], "query": query, "meal_type": meal_type}
    return result, {}


def _run_external_food_job(db, request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    text = request_payload.get("text", "")
    source_hint = request_payload.get("source_hint")
    result_payload, suggested_update = build_external_food_job_result(text, source_hint=source_hint)
    target_log_id = request_payload.get("target_log_id")
    if target_log_id and suggested_update:
        log = db.get(MealLog, target_log_id)
        if log:
            suggested_update["target_log_id"] = log.id
            suggested_update.setdefault("store_name", _extract_store_name(log.description_raw))
            suggested_update.setdefault("external_link", "")
    return result_payload, suggested_update


def _run_video_job(request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return build_video_refinement_result(request_payload)


def _maybe_create_job_notification(db, job: SearchJob) -> None:
    user = db.get(User, job.user_id)
    if not user:
        return

    title = "Async update ready"
    body = "A background check found a more detailed result."
    notification_type = "async_update"
    if job.job_type == "nearby_places":
        title = "Nearby search updated"
        body = "I found more precise nearby options."
        notification_type = "nearby_update"
    elif job.job_type in {"video_extract", "video_transcript", "video_precision", "video_brand_lookup"}:
        title = "Video analysis updated"
        body = "I finished a background pass on your meal video."
        notification_type = "video_update"

    create_notification(
        db,
        user,
        notification_type=notification_type,
        title=title,
        body=body,
        payload={"job_id": job.id, "suggested_update": job.suggested_update, "result_payload": job.result_payload},
        related_job_id=job.id,
    )
    line_text = body
    flex_message = None
    if job.job_type == "nearby_places":
        place_count = len((job.result_payload or {}).get("places", []))
        line_text = f"I found {place_count} more precise nearby options."
        flex_message = build_action_flex_message(
            title="Nearby options updated",
            subtitle=f"{place_count} nearby picks are ready",
            lines=[
                "The nearby shortlist now includes more precise place results.",
                "Open Eat to compare the refreshed shortlist and decide there.",
            ],
            primary_label="Open Eat",
            primary_uri=build_liff_tab_url("eat"),
            secondary_label="Open Today",
            secondary_uri=build_liff_tab_url("today"),
        )
    elif job.job_type in {"menu_precision", "brand_lookup", "external_food_check"}:
        line_text = "I found a more precise nutrition update for a recent meal."
        flex_message = build_action_flex_message(
            title="Nutrition update ready",
            subtitle="A recent meal has a suggested refinement",
            lines=[
                "A background pass found a more specific estimate for one of your recent meals.",
                "Open Today to review and decide whether to apply it.",
            ],
            primary_label="Open Today",
            primary_uri=build_liff_tab_url("today"),
        )
    elif job.job_type in {"video_extract", "video_transcript", "video_precision", "video_brand_lookup"}:
        line_text = "Video analysis finished with a refined estimate."
        flex_message = build_action_flex_message(
            title="Video update ready",
            subtitle="The meal video background pass has completed",
            lines=[
                "A background refinement extracted more evidence from the meal video.",
                "Open Today to review and optionally apply the updated estimate.",
            ],
            primary_label="Open Today",
            primary_uri=build_liff_tab_url("today"),
        )
    try:
        asyncio.run(push_line_message(user.line_user_id, line_text, flex_message=flex_message))
    except Exception:
        pass
    job.notification_sent_at = datetime.now()


def _extract_store_name(description: str) -> str:
    return description.split()[0][:80] if description.strip() else ""


def _session_factory():
    return SessionLocal if SessionLocal is not DefaultSessionLocal else get_session_factory()
