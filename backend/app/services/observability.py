from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from ..config import canary_line_user_id_list, canary_user_id_list
from ..models import (
    ConversationTrace,
    ErrorEvent,
    FeedbackEvent,
    KnowledgeEvent,
    OutcomeEvent,
    ReviewQueueItem,
    TaskRun,
    UncertaintyEvent,
    UnknownCaseEvent,
)


MAX_TEXT_LENGTH = 2000
SENSITIVE_KEY_PATTERN = re.compile(r"(token|secret|password|authorization|api[_-]?key|cookie)", re.IGNORECASE)
SAFE_OBSERVABILITY_KEYS = {
    # Token counts
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    # Budget info
    "token_budget_per_hour",
    "cost_budget_usd_per_day",
    "request_budget_per_hour",
    # Rate limit info
    "rate_limit_remaining_tokens",
    "rate_limit_remaining_requests",
    "rate_limit_reset_tokens_s",
    "rate_limit_reset_requests_s",
    # Cost tracking
    "estimated_cost_usd",
    "estimated_cost",
    # Request tracking
    "request_count",
    # Provider info
    "provider_name",
    "model_name",
    "model_hint",
}
NEGATIVE_FEEDBACK_RULES = [
    {
        "feedback_type": "explicit_negative",
        "feedback_label": "off_topic",
        "severity": "high",
        "patterns": ["答非所問", "不是在問這個", "不是這個", "off topic", "not what i asked"],
    },
    {
        "feedback_type": "explicit_negative",
        "feedback_label": "wrong_answer",
        "severity": "high",
        "patterns": ["你搞錯了", "這不對", "熱量不對", "wrong", "incorrect"],
    },
    {
        "feedback_type": "explicit_negative",
        "feedback_label": "too_many_questions",
        "severity": "medium",
        "patterns": ["問題太多", "不要再問", "別再問了", "too many questions"],
    },
    {
        "feedback_type": "explicit_negative",
        "feedback_label": "wrong_route",
        "severity": "high",
        "patterns": ["不是要改這個", "不是要記這個", "不是要推薦", "wrong route"],
    },
]


def ensure_trace_id(existing: str | None = None) -> str:
    return existing or str(uuid.uuid4())


def get_request_trace_id(request: Request | None) -> str:
    if request is None:
        return ensure_trace_id()
    trace_id = getattr(request.state, "trace_id", None)
    if trace_id:
        return trace_id
    trace_id = ensure_trace_id(request.headers.get("x-trace-id"))
    request.state.trace_id = trace_id
    return trace_id


def create_conversation_trace(
    db: Session,
    *,
    trace_id: str,
    user_id: int | None = None,
    line_user_id: str | None = None,
    surface: str,
    task_family: str,
    task_confidence: float | None = None,
    source_mode: str | None = None,
    input_text: str = "",
    input_metadata: dict[str, Any] | None = None,
    thread_id: str | None = None,
    message_id: str | None = None,
    reply_to_trace_id: str | None = None,
    is_system_initiated: bool = False,
    is_canary: bool = False,
    traffic_class: str = "standard",
) -> str:
    trace_row_id = trace_id
    row = ConversationTrace(
        id=trace_row_id,
        user_id=user_id,
        line_user_id=line_user_id,
        surface=surface,
        thread_id=thread_id,
        message_id=message_id,
        reply_to_trace_id=reply_to_trace_id,
        is_system_initiated=is_system_initiated,
        is_canary=is_canary,
        traffic_class=traffic_class or "standard",
        task_family=task_family,
        task_confidence=task_confidence,
        source_mode=source_mode,
        input_text=_sanitize_text(input_text),
        input_metadata=_sanitize_payload(input_metadata or {}),
    )
    _persist_row(db, row)
    return trace_row_id


def start_task_run(
    db: Session,
    *,
    trace_id: str,
    task_family: str,
    user_id: int | None = None,
    route_layer_1: str | None = None,
    route_layer_2: str | None = None,
    provider_name: str | None = None,
    model_name: str | None = None,
    prompt_version: str | None = None,
    knowledge_packet_version: str | None = None,
    is_canary: bool | None = None,
    traffic_class: str | None = None,
    result_summary: dict[str, Any] | None = None,
) -> str:
    task_run_id = str(uuid.uuid4())
    inherited_is_canary = bool(is_canary)
    inherited_traffic_class = traffic_class or "standard"
    if is_canary is None or traffic_class is None:
        trace = db.get(ConversationTrace, trace_id)
        if trace is not None:
            if is_canary is None:
                inherited_is_canary = bool(trace.is_canary)
            if traffic_class is None:
                inherited_traffic_class = trace.traffic_class or "standard"
    row = TaskRun(
        id=task_run_id,
        trace_id=trace_id,
        user_id=user_id,
        is_canary=inherited_is_canary,
        traffic_class=inherited_traffic_class,
        task_family=task_family,
        route_layer_1=route_layer_1,
        route_layer_2=route_layer_2,
        provider_name=provider_name,
        model_name=model_name,
        prompt_version=prompt_version,
        knowledge_packet_version=knowledge_packet_version,
        started_at=datetime.now(timezone.utc),
        status="success",
        result_summary=_sanitize_payload(result_summary or {}),
    )
    _persist_row(db, row)
    return task_run_id


def finish_task_run(
    db: Session,
    task_run_id: str | None,
    *,
    status: str,
    error_type: str | None = None,
    fallback_reason: str | None = None,
    result_summary: dict[str, Any] | None = None,
) -> None:
    if not task_run_id:
        return
    with _bound_session(db) as log_db:
        row = log_db.get(TaskRun, task_run_id)
        if not row:
            return
        completed_at = _coerce_utc(datetime.now(timezone.utc))
        started_at = _coerce_utc(row.started_at)
        row.completed_at = completed_at
        if started_at and completed_at:
            row.latency_ms = max(int((completed_at - started_at).total_seconds() * 1000), 0)
        row.status = status
        row.error_type = error_type
        row.fallback_reason = _sanitize_text(fallback_reason or "") if fallback_reason else None
        merged_summary = dict(row.result_summary or {})
        merged_summary.update(_sanitize_payload(result_summary or {}))
        row.result_summary = merged_summary
        log_db.add(row)
        log_db.commit()


def record_uncertainty_event(
    db: Session,
    *,
    trace_id: str,
    task_family: str,
    user_id: int | None = None,
    task_run_id: str | None = None,
    estimation_confidence: float | None = None,
    confirmation_calibration: float | None = None,
    primary_uncertainties: list[str] | None = None,
    missing_slots: list[str] | None = None,
    ambiguity_flags: list[str] | None = None,
    answer_mode: str | None = None,
    clarification_budget: int | None = None,
    clarification_used: int | None = None,
    stop_reason: str | None = None,
    used_generic_portion_estimate: bool = False,
    used_comparison_mode: bool = False,
) -> str:
    event_id = str(uuid.uuid4())
    row = UncertaintyEvent(
        id=event_id,
        trace_id=trace_id,
        task_run_id=task_run_id,
        user_id=user_id,
        task_family=task_family,
        estimation_confidence=estimation_confidence,
        confirmation_calibration=confirmation_calibration,
        primary_uncertainties=primary_uncertainties or [],
        missing_slots=missing_slots or [],
        ambiguity_flags=ambiguity_flags or [],
        answer_mode=answer_mode,
        clarification_budget=clarification_budget,
        clarification_used=clarification_used,
        stop_reason=stop_reason,
        used_generic_portion_estimate=used_generic_portion_estimate,
        used_comparison_mode=used_comparison_mode,
    )
    _persist_row(db, row)
    return event_id


def record_knowledge_event(
    db: Session,
    *,
    trace_id: str,
    question_or_query: str,
    task_run_id: str | None = None,
    user_id: int | None = None,
    knowledge_mode: str,
    matched_items: list[dict[str, Any]] | None = None,
    matched_docs: list[str] | None = None,
    used_search: bool = False,
    search_sources: list[dict[str, Any]] | None = None,
    grounding_type: str | None = None,
    knowledge_gap_type: str | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    row = KnowledgeEvent(
        id=event_id,
        trace_id=trace_id,
        task_run_id=task_run_id,
        user_id=user_id,
        question_or_query=_sanitize_text(question_or_query),
        knowledge_mode=knowledge_mode,
        matched_items=_sanitize_payload(matched_items or []),
        matched_docs=[_sanitize_text(item) for item in (matched_docs or [])],
        used_search=used_search,
        search_sources=_sanitize_payload(search_sources or []),
        grounding_type=grounding_type,
        knowledge_gap_type=knowledge_gap_type,
    )
    _persist_row(db, row)
    return event_id


def record_error_event(
    db: Session,
    *,
    trace_id: str,
    component: str,
    operation: str,
    user_id: int | None = None,
    task_run_id: str | None = None,
    severity: str = "error",
    error_code: str | None = None,
    exception_type: str | None = None,
    message: str = "",
    retry_count: int = 0,
    fallback_used: bool = False,
    user_visible_impact: str = "degraded",
    request_metadata: dict[str, Any] | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    row = ErrorEvent(
        id=event_id,
        trace_id=trace_id,
        task_run_id=task_run_id,
        user_id=user_id,
        component=component,
        operation=operation,
        severity=severity,
        error_code=error_code,
        exception_type=exception_type,
        message=_sanitize_text(message),
        retry_count=retry_count,
        fallback_used=fallback_used,
        user_visible_impact=user_visible_impact,
        request_metadata=_sanitize_payload(request_metadata or {}),
    )
    _persist_row(db, row)
    if severity in {"error", "critical"} or error_code in {"job_retry_exhausted", "failed_request"}:
        _enqueue_review_queue_item(
            db,
            queue_type="operational_error",
            priority=0 if severity == "critical" or error_code == "job_retry_exhausted" else 1,
            task_family="operational",
            trace_id=trace_id,
            source_table="error_events",
            source_id=event_id,
            title=f"{component}:{operation}",
            summary=message or error_code or exception_type or "Operational error",
            normalized_label=error_code or exception_type,
            payload={
                "severity": severity,
                "retry_count": retry_count,
                "fallback_used": fallback_used,
                "user_visible_impact": user_visible_impact,
                "request_metadata": request_metadata or {},
            },
        )
    return event_id


def record_feedback_event(
    db: Session,
    *,
    trace_id: str,
    feedback_type: str,
    feedback_label: str,
    user_id: int | None = None,
    target_trace_id: str | None = None,
    free_text: str = "",
    severity: str = "medium",
) -> str:
    event_id = str(uuid.uuid4())
    row = FeedbackEvent(
        id=event_id,
        user_id=user_id,
        trace_id=trace_id,
        target_trace_id=target_trace_id,
        feedback_type=feedback_type,
        feedback_label=feedback_label,
        free_text=_sanitize_text(free_text),
        severity=severity,
    )
    _persist_row(db, row)
    if feedback_type == "explicit_negative" or feedback_label in {"wrong_route", "off_topic", "wrong_answer", "dismissed_async_update"}:
        _enqueue_review_queue_item(
            db,
            queue_type="feedback",
            priority=0 if severity == "high" else 1,
            task_family="user_feedback",
            trace_id=trace_id,
            source_table="feedback_events",
            source_id=event_id,
            title=f"feedback:{feedback_label}",
            summary=free_text or feedback_label,
            normalized_label=feedback_label,
            payload={"feedback_type": feedback_type, "severity": severity, "target_trace_id": target_trace_id},
        )
    return event_id


def record_unknown_case_event(
    db: Session,
    *,
    trace_id: str,
    task_family: str,
    unknown_type: str,
    raw_query: str,
    user_id: int | None = None,
    task_run_id: str | None = None,
    source_hint: str = "",
    ocr_hits: list[dict[str, Any]] | None = None,
    transcript: str = "",
    current_answer: str = "",
    suggested_research_area: str = "",
) -> str:
    event_id = str(uuid.uuid4())
    row = UnknownCaseEvent(
        id=event_id,
        trace_id=trace_id,
        task_run_id=task_run_id,
        user_id=user_id,
        task_family=task_family,
        unknown_type=unknown_type,
        raw_query=_sanitize_text(raw_query),
        source_hint=_sanitize_text(source_hint),
        ocr_hits=_sanitize_payload(ocr_hits or []),
        transcript=_sanitize_text(transcript),
        current_answer=_sanitize_text(current_answer),
        suggested_research_area=_sanitize_text(suggested_research_area),
        review_status="new",
    )
    _persist_row(db, row)
    _enqueue_review_queue_item(
        db,
        queue_type="unknown_case",
        priority=1,
        task_family=task_family,
        trace_id=trace_id,
        source_table="unknown_case_events",
        source_id=event_id,
        title=f"{unknown_type}:{task_family}",
        summary=raw_query or current_answer or unknown_type,
        normalized_label=unknown_type,
        payload={
            "source_hint": source_hint,
            "suggested_research_area": suggested_research_area,
            "ocr_hits": ocr_hits or [],
            "transcript": transcript,
        },
    )
    return event_id


def record_outcome_event(
    db: Session,
    *,
    trace_id: str,
    task_family: str,
    outcome_type: str,
    user_id: int | None = None,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    row = OutcomeEvent(
        id=event_id,
        trace_id=trace_id,
        user_id=user_id,
        task_family=task_family,
        outcome_type=outcome_type,
        target_id=target_id,
        payload=_sanitize_payload(payload or {}),
    )
    _persist_row(db, row)
    return event_id


def detect_explicit_feedback(text: str) -> dict[str, str] | None:
    normalized = text.strip().lower()
    for rule in NEGATIVE_FEEDBACK_RULES:
        if any(pattern in normalized for pattern in rule["patterns"]):
            return {
                "feedback_type": rule["feedback_type"],
                "feedback_label": rule["feedback_label"],
                "severity": rule["severity"],
            }
    return None


def resolve_traffic_class(
    *,
    user_id: int | str | None = None,
    line_user_id: str | None = None,
    input_metadata: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    metadata = input_metadata or {}
    if metadata.get("is_canary") is True:
        return True, str(metadata.get("traffic_class") or "self_use_canary")

    canary_line_ids = set(canary_line_user_id_list())
    canary_user_ids = set(canary_user_id_list())
    is_canary = False
    if line_user_id and line_user_id in canary_line_ids:
        is_canary = True
    if user_id is not None and str(user_id) in canary_user_ids:
        is_canary = True
    return is_canary, "self_use_canary" if is_canary else "standard"


def provider_descriptor(provider: Any, *, task_family: str, source_mode: str | None = None) -> tuple[str | None, str | None]:
    provider_name = type(provider).__name__ if provider is not None else None
    model_name = None
    if provider_name == "BuilderSpaceProvider":
        try:
            from ..config import settings

            if task_family == "meal_log_now" and source_mode in {"image", "video"}:
                model_name = settings.builderspace_vision_model
            else:
                model_name = settings.builderspace_chat_model
        except Exception:
            model_name = "builderspace"
    elif provider_name == "HeuristicProvider":
        model_name = "heuristic"
    return provider_name, model_name


def route_layers_for_task(task_family: str) -> tuple[str, str]:
    if task_family == "line_webhook_ingress":
        return "ingress", task_family
    if task_family == "line_webhook_event":
        return "worker", task_family
    if task_family in {"meal_log_now", "meal_log_correction", "clarification", "confirmation"}:
        return "logging", task_family
    if task_family in {"remaining_or_recommendation", "nearby_recommendation", "weekly_drift_probe", "future_event_probe", "planning", "compensation"}:
        return "query", task_family
    if task_family in {"preference_or_memory_correction", "meta_help"}:
        return "settings_or_help", task_family
    if task_family == "nutrition_or_food_qa":
        return "query", task_family
    return "ambiguous", task_family


def _bound_session(db: Session) -> Session:
    return Session(bind=db.get_bind(), future=True)


def _persist_row(db: Session, row: Any) -> None:
    with _bound_session(db) as log_db:
        log_db.add(row)
        log_db.commit()


def _enqueue_review_queue_item(
    db: Session,
    *,
    queue_type: str,
    priority: int,
    task_family: str | None,
    trace_id: str | None,
    source_table: str,
    source_id: str,
    title: str,
    summary: str,
    normalized_label: str | None,
    payload: dict[str, Any],
) -> None:
    with _bound_session(db) as log_db:
        existing = (
            log_db.query(ReviewQueueItem)
            .filter_by(source_table=source_table, source_id=source_id)
            .one_or_none()
        )
        if existing:
            return
        row = ReviewQueueItem(
            queue_type=queue_type,
            priority=priority,
            task_family=task_family,
            trace_id=trace_id,
            source_table=source_table,
            source_id=source_id,
            title=_sanitize_text(title)[:160],
            summary=_sanitize_text(summary),
            normalized_label=_sanitize_text(normalized_label) if normalized_label else None,
            payload=_sanitize_payload(payload),
        )
        log_db.add(row)
        log_db.commit()


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sanitize_text(value: str | None) -> str:
    if not value:
        return ""
    compact = " ".join(str(value).split())
    return compact[:MAX_TEXT_LENGTH]


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key)
            if normalized_key in SAFE_OBSERVABILITY_KEYS:
                sanitized[normalized_key] = _sanitize_payload(item)
            elif SENSITIVE_KEY_PATTERN.search(normalized_key):
                sanitized[str(key)] = "<redacted>"
            else:
                sanitized[normalized_key] = _sanitize_payload(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value[:50]]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value[:50]]
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _sanitize_text(str(value))
