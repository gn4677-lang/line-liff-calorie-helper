from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from .knowledge import knowledge_runtime_status
from ..models import (
    AlertEvent,
    AlertRule,
    ActivityAdjustment,
    BodyGoal,
    ConversationTrace,
    ErrorEvent,
    FeedbackEvent,
    InboundEvent,
    KnowledgeEvent,
    MealEvent,
    MemoryHypothesis,
    MemorySignal,
    Notification,
    ObservabilityMetricSnapshot,
    OutcomeEvent,
    RecommendationProfile,
    RecommendationSession,
    ReportingBias,
    ReviewQueueItem,
    SearchJob,
    TaskRun,
    UncertaintyEvent,
    UnknownCaseEvent,
    User,
    utcnow,
)


DEFAULT_ALERT_RULES = [
    {
        "name": "meal-log-fallback-rate-high",
        "metric_key": "task_fallback_rate",
        "comparator": "gt",
        "threshold": 0.25,
        "window_hours": 24,
        "task_family": "meal_log_now",
        "severity": "warning",
        "min_sample_size": 5,
        "cooldown_minutes": 360,
        "notes": "Meal logging is falling back too often.",
    },
    {
        "name": "nutrition-unknown-rate-high",
        "metric_key": "unknown_case_rate",
        "comparator": "gt",
        "threshold": 0.20,
        "window_hours": 168,
        "task_family": "nutrition_or_food_qa",
        "severity": "warning",
        "min_sample_size": 3,
        "cooldown_minutes": 720,
        "notes": "Nutrition QA is missing too many answers locally.",
    },
    {
        "name": "suggested-update-dismiss-rate-high",
        "metric_key": "suggested_update_dismiss_rate",
        "comparator": "gt",
        "threshold": 0.60,
        "window_hours": 168,
        "task_family": "suggested_update_review",
        "severity": "warning",
        "min_sample_size": 5,
        "cooldown_minutes": 720,
        "notes": "Users are dismissing too many async refinements.",
    },
    {
        "name": "generic-portion-fallback-high",
        "metric_key": "generic_portion_fallback_rate",
        "comparator": "gt",
        "threshold": 0.25,
        "window_hours": 168,
        "task_family": "meal_log_now",
        "severity": "warning",
        "min_sample_size": 5,
        "cooldown_minutes": 720,
        "notes": "Portion estimation is falling back to generic too often.",
    },
    {
        "name": "retry-exhausted-detected",
        "metric_key": "retry_exhausted_count",
        "comparator": "gt",
        "threshold": 0.0,
        "window_hours": 24,
        "task_family": None,
        "severity": "critical",
        "min_sample_size": 1,
        "cooldown_minutes": 60,
        "notes": "Background job retries were exhausted.",
    },
]

DEFAULT_METRIC_REQUESTS = [
    {"metric_key": "task_success_rate", "task_family": "meal_log_now"},
    {"metric_key": "task_fallback_rate", "task_family": "meal_log_now"},
    {"metric_key": "unknown_case_rate", "task_family": "nutrition_or_food_qa"},
    {"metric_key": "generic_portion_fallback_rate", "task_family": "meal_log_now"},
    {"metric_key": "suggested_update_apply_rate", "task_family": "suggested_update_review"},
    {"metric_key": "suggested_update_dismiss_rate", "task_family": "suggested_update_review"},
    {"metric_key": "dissatisfaction_rate", "task_family": None},
    {"metric_key": "degraded_error_rate", "task_family": None},
    {"metric_key": "retry_exhausted_count", "task_family": None},
]


def ensure_default_alert_rules(db: Session) -> list[AlertRule]:
    rules: list[AlertRule] = []
    for spec in DEFAULT_ALERT_RULES:
        row = db.query(AlertRule).filter_by(name=spec["name"]).one_or_none()
        if not row:
            row = AlertRule(**spec)
            db.add(row)
            db.flush()
        rules.append(row)
    db.commit()
    return list_alert_rules(db)


def list_alert_rules(db: Session) -> list[AlertRule]:
    return db.query(AlertRule).order_by(AlertRule.severity.desc(), AlertRule.name.asc()).all()


def upsert_alert_rule(
    db: Session,
    *,
    name: str,
    metric_key: str,
    comparator: str,
    threshold: float,
    window_hours: int,
    task_family: str | None,
    severity: str,
    min_sample_size: int,
    cooldown_minutes: int,
    status: str = "active",
    dimensions: dict[str, Any] | None = None,
    notes: str = "",
) -> AlertRule:
    row = db.query(AlertRule).filter_by(name=name).one_or_none()
    if row is None:
        row = AlertRule(name=name)
        db.add(row)
    row.metric_key = metric_key
    row.comparator = comparator
    row.threshold = threshold
    row.window_hours = window_hours
    row.task_family = task_family
    row.severity = severity
    row.min_sample_size = min_sample_size
    row.cooldown_minutes = cooldown_minutes
    row.status = status
    row.dimensions = dimensions or {}
    row.notes = notes
    db.commit()
    db.refresh(row)
    return row


def list_alert_events(db: Session, *, status: str | None = None, limit: int = 100) -> list[AlertEvent]:
    query = db.query(AlertEvent)
    if status:
        query = query.filter(AlertEvent.status == status)
    return query.order_by(AlertEvent.last_seen_at.desc()).limit(limit).all()


def update_alert_event_status(db: Session, alert_id: str, *, status: str) -> AlertEvent | None:
    row = db.get(AlertEvent, alert_id)
    if not row:
        return None
    row.status = status
    row.last_seen_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_review_queue(
    db: Session,
    *,
    status: str | None = None,
    queue_type: str | None = None,
    limit: int = 100,
) -> list[ReviewQueueItem]:
    query = db.query(ReviewQueueItem)
    if status:
        query = query.filter(ReviewQueueItem.status == status)
    if queue_type:
        query = query.filter(ReviewQueueItem.queue_type == queue_type)
    return query.order_by(ReviewQueueItem.priority.asc(), ReviewQueueItem.created_at.desc()).limit(limit).all()


def update_review_queue_item(
    db: Session,
    item_id: int,
    *,
    status: str,
    notes: str | None = None,
    assigned_to: str | None = None,
) -> ReviewQueueItem | None:
    row = db.get(ReviewQueueItem, item_id)
    if not row:
        return None
    row.status = status
    if notes is not None:
        row.notes = notes
    if assigned_to is not None:
        row.assigned_to = assigned_to
    if status in {"resolved", "ignored"}:
        row.reviewed_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def build_observability_dashboard(
    db: Session,
    *,
    window_hours: int = 168,
    trend_days: int = 7,
    user_id: int | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=window_hours)
    summary_cards = _build_summary_cards(db, since=since, window_hours=window_hours)
    task_health = _build_task_health(db, window_hours=window_hours)
    quality_trends = _build_quality_trends(db, trend_days=trend_days)
    usage_panels = _build_usage_panels(db, since=since)
    product_panels = _build_product_panels(db, since=since)
    memory_panels = _build_memory_panels(db, user_id=user_id)
    operational_panels = _build_operational_panels(db, since=since)
    webhook_queue_panels = _build_webhook_queue_panels(db)
    notification_panels = _build_notification_panels(db, since=since)
    eval_panels = _build_eval_panels(db, since=since)
    attention_panels = _build_attention_panels(db)
    return {
        "refreshed_at": now,
        "window_hours": window_hours,
        "trend_days": trend_days,
        "summary_cards": summary_cards,
        "task_health": task_health,
        "quality_trends": quality_trends,
        "usage_panels": usage_panels,
        "product_panels": product_panels,
        "memory_panels": memory_panels,
        "operational_panels": operational_panels,
        "webhook_queue_panels": webhook_queue_panels,
        "notification_panels": notification_panels,
        "eval_panels": eval_panels,
        "attention_panels": attention_panels,
    }


def build_eval_export(
    db: Session,
    *,
    window_hours: int = 168,
    limit: int = 200,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    since = generated_at - timedelta(hours=window_hours)
    recent_runs = (
        db.query(TaskRun)
        .filter(TaskRun.started_at >= since)
        .order_by(TaskRun.started_at.desc())
        .limit(limit)
        .all()
    )
    webhook_runs = [
        row for row in recent_runs
        if row.task_family in {"line_webhook_ingress", "line_webhook_event"}
    ]
    planning_runs = [
        row for row in recent_runs
        if row.task_family in {"planning", "compensation"}
    ]
    canary_runs = [row for row in recent_runs if bool(row.is_canary)]
    return {
        "generated_at": generated_at,
        "window_hours": window_hours,
        "usage_panels": _build_usage_panels(db, since=since),
        "eval_panels": _build_eval_panels(db, since=since),
        "recent_webhook_runs": [_task_run_row(row) for row in webhook_runs],
        "recent_planning_runs": [_task_run_row(row) for row in planning_runs],
        "recent_canary_runs": [_task_run_row(row) for row in canary_runs[:limit]],
        "canary_transcript_review": _build_canary_transcript_review(db, canary_runs=canary_runs, limit=min(limit, 50)),
    }


def list_trace_summaries(
    db: Session,
    *,
    task_family: str | None = None,
    surface: str | None = None,
    source_mode: str | None = None,
    status: str | None = None,
    provider_name: str | None = None,
    model_name: str | None = None,
    execution_phase: str | None = None,
    ingress_mode: str | None = None,
    route_policy: str | None = None,
    llm_cache: str | None = None,
    is_canary: bool | None = None,
    traffic_class: str | None = None,
    has_error: bool | None = None,
    has_feedback: bool | None = None,
    has_unknown_case: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    query = db.query(ConversationTrace)
    if task_family:
        query = query.filter(ConversationTrace.task_family == task_family)
    if surface:
        query = query.filter(ConversationTrace.surface == surface)
    if source_mode:
        query = query.filter(ConversationTrace.source_mode == source_mode)
    if is_canary is not None:
        query = query.filter(ConversationTrace.is_canary == is_canary)
    if traffic_class:
        query = query.filter(ConversationTrace.traffic_class == traffic_class)

    trace_id_filters: list[Any] = []
    if status or provider_name or model_name or route_policy or llm_cache or execution_phase or ingress_mode:
        task_query = db.query(TaskRun.trace_id).distinct()
        if status:
            task_query = task_query.filter(TaskRun.status == status)
        if provider_name:
            task_query = task_query.filter(TaskRun.provider_name == provider_name)
        if model_name:
            task_query = task_query.filter(TaskRun.model_name == model_name)
        candidate_runs = task_query.all()
        trace_ids = {row[0] for row in candidate_runs}
        if route_policy or llm_cache:
            filtered_trace_ids: set[str] = set()
            runs = db.query(TaskRun).filter(TaskRun.trace_id.in_(trace_ids)).all() if trace_ids else []
            for run in runs:
                if route_policy and _task_run_summary_value(run, "route_policy") != route_policy:
                    continue
                if llm_cache and _task_run_summary_value(run, "llm_cache") != llm_cache:
                    continue
                if execution_phase and _task_run_summary_value(run, "execution_phase") != execution_phase:
                    continue
                if ingress_mode and _task_run_summary_value(run, "ingress_mode") != ingress_mode:
                    continue
                filtered_trace_ids.add(run.trace_id)
            trace_id_filters.append(filtered_trace_ids)
        else:
            if execution_phase or ingress_mode:
                filtered_trace_ids: set[str] = set()
                runs = db.query(TaskRun).filter(TaskRun.trace_id.in_(trace_ids)).all() if trace_ids else []
                for run in runs:
                    if execution_phase and _task_run_summary_value(run, "execution_phase") != execution_phase:
                        continue
                    if ingress_mode and _task_run_summary_value(run, "ingress_mode") != ingress_mode:
                        continue
                    filtered_trace_ids.add(run.trace_id)
                trace_id_filters.append(filtered_trace_ids)
            else:
                trace_id_filters.append(trace_ids)
    if has_error is not None:
        error_ids = set(row[0] for row in db.query(ErrorEvent.trace_id).distinct().all())
        trace_id_filters.append(error_ids if has_error else None)
        if not has_error:
            query = query.filter(~ConversationTrace.id.in_(error_ids))
    if has_feedback is not None:
        feedback_ids = set(row[0] for row in db.query(FeedbackEvent.trace_id).distinct().all())
        trace_id_filters.append(feedback_ids if has_feedback else None)
        if not has_feedback:
            query = query.filter(~ConversationTrace.id.in_(feedback_ids))
    if has_unknown_case is not None:
        unknown_ids = set(row[0] for row in db.query(UnknownCaseEvent.trace_id).distinct().all())
        trace_id_filters.append(unknown_ids if has_unknown_case else None)
        if not has_unknown_case:
            query = query.filter(~ConversationTrace.id.in_(unknown_ids))

    required_sets = [trace_ids for trace_ids in trace_id_filters if trace_ids is not None]
    if required_sets:
        intersection = set.intersection(*required_sets) if len(required_sets) > 1 else required_sets[0]
        if not intersection:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        query = query.filter(ConversationTrace.id.in_(intersection))

    total = query.count()
    traces = query.order_by(ConversationTrace.created_at.desc()).offset(offset).limit(limit).all()
    trace_ids = [row.id for row in traces]
    if not trace_ids:
        return {"items": [], "total": total, "limit": limit, "offset": offset}

    task_runs = (
        db.query(TaskRun)
        .filter(TaskRun.trace_id.in_(trace_ids))
        .order_by(TaskRun.trace_id.asc(), TaskRun.started_at.desc())
        .all()
    )
    latest_task_run_by_trace: dict[str, TaskRun] = {}
    for run in task_runs:
        latest_task_run_by_trace.setdefault(run.trace_id, run)

    error_trace_ids = set(row[0] for row in db.query(ErrorEvent.trace_id).filter(ErrorEvent.trace_id.in_(trace_ids)).distinct().all())
    feedback_trace_ids = set(row[0] for row in db.query(FeedbackEvent.trace_id).filter(FeedbackEvent.trace_id.in_(trace_ids)).distinct().all())
    unknown_trace_ids = set(
        row[0] for row in db.query(UnknownCaseEvent.trace_id).filter(UnknownCaseEvent.trace_id.in_(trace_ids)).distinct().all()
    )
    outcome_rows = (
        db.query(OutcomeEvent)
        .filter(OutcomeEvent.trace_id.in_(trace_ids))
        .order_by(OutcomeEvent.trace_id.asc(), OutcomeEvent.created_at.desc())
        .all()
    )
    latest_outcome_by_trace: dict[str, OutcomeEvent] = {}
    for row in outcome_rows:
        latest_outcome_by_trace.setdefault(row.trace_id, row)

    items: list[dict[str, Any]] = []
    for trace in traces:
        latest_run = latest_task_run_by_trace.get(trace.id)
        outcome = latest_outcome_by_trace.get(trace.id)
        outcome_summary = outcome.outcome_type if outcome else (latest_run.status if latest_run else "no_outcome")
        items.append(
            {
                "trace_id": trace.id,
                "created_at": trace.created_at,
                "task_family": trace.task_family,
                "surface": trace.surface,
                "source_mode": trace.source_mode,
                "input_preview": _truncate(trace.input_text or "", 120),
                "route_status": latest_run.status if latest_run else "unknown",
                "provider_name": latest_run.provider_name if latest_run else None,
                "model_name": latest_run.model_name if latest_run else None,
                "execution_phase": _task_run_summary_value(latest_run, "execution_phase") if latest_run else None,
                "ingress_mode": _task_run_summary_value(latest_run, "ingress_mode") if latest_run else None,
                "route_policy": _task_run_summary_value(latest_run, "route_policy") if latest_run else None,
                "route_target": _task_run_summary_value(latest_run, "route_target") if latest_run else None,
                "llm_cache": _task_run_summary_value(latest_run, "llm_cache") if latest_run else None,
                "latency_ms": latest_run.latency_ms if latest_run else None,
                "is_canary": bool(trace.is_canary),
                "traffic_class": trace.traffic_class or "standard",
                "has_error": trace.id in error_trace_ids,
                "has_feedback": trace.id in feedback_trace_ids,
                "has_unknown_case": trace.id in unknown_trace_ids,
                "outcome_summary": outcome_summary,
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_trace_detail(db: Session, trace_id: str) -> dict[str, Any] | None:
    trace = db.get(ConversationTrace, trace_id)
    if trace is None:
        return None

    task_runs = db.query(TaskRun).filter(TaskRun.trace_id == trace_id).order_by(TaskRun.started_at.asc()).all()
    task_run_ids = [row.id for row in task_runs]
    uncertainty_events = (
        db.query(UncertaintyEvent).filter(UncertaintyEvent.trace_id == trace_id).order_by(UncertaintyEvent.created_at.asc()).all()
    )
    knowledge_events = db.query(KnowledgeEvent).filter(KnowledgeEvent.trace_id == trace_id).order_by(KnowledgeEvent.created_at.asc()).all()
    error_events = db.query(ErrorEvent).filter(ErrorEvent.trace_id == trace_id).order_by(ErrorEvent.created_at.asc()).all()
    feedback_events = db.query(FeedbackEvent).filter(FeedbackEvent.trace_id == trace_id).order_by(FeedbackEvent.created_at.asc()).all()
    unknown_case_events = (
        db.query(UnknownCaseEvent).filter(UnknownCaseEvent.trace_id == trace_id).order_by(UnknownCaseEvent.created_at.asc()).all()
    )
    outcome_events = db.query(OutcomeEvent).filter(OutcomeEvent.trace_id == trace_id).order_by(OutcomeEvent.created_at.asc()).all()

    source_ids = {str(row.id) for row in error_events}
    source_ids.update(str(row.id) for row in unknown_case_events)
    source_ids.update(str(row.id) for row in outcome_events)
    source_ids.update(str(row.id) for row in feedback_events)
    related_review_items = (
        db.query(ReviewQueueItem)
        .filter(
            or_(
                ReviewQueueItem.trace_id == trace_id,
                and_(ReviewQueueItem.source_table.in_(("error_events", "unknown_case_events", "outcome_events", "feedback_events")), ReviewQueueItem.source_id.in_(source_ids)),
            )
        )
        .order_by(ReviewQueueItem.priority.asc(), ReviewQueueItem.created_at.desc())
        .all()
    )
    related_alerts = (
        db.query(AlertEvent)
        .filter(AlertEvent.task_family == trace.task_family)
        .order_by(AlertEvent.last_seen_at.desc())
        .limit(12)
        .all()
    )
    return {
        "trace": _trace_row(trace),
        "task_runs": [_task_run_row(row) for row in task_runs],
        "uncertainty_events": [_uncertainty_row(row) for row in uncertainty_events],
        "knowledge_events": [_knowledge_row(row) for row in knowledge_events],
        "error_events": [_error_row(row) for row in error_events],
        "feedback_events": [_feedback_row(row) for row in feedback_events],
        "unknown_case_events": [_unknown_case_row(row) for row in unknown_case_events],
        "outcome_events": [_outcome_row(row) for row in outcome_events],
        "related_review_items": related_review_items,
        "related_alerts": related_alerts,
        "task_run_ids": task_run_ids,
    }


def collect_default_metrics(db: Session, *, window_hours: int = 168) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for spec in DEFAULT_METRIC_REQUESTS:
        metrics.append(compute_metric(db, spec["metric_key"], window_hours=window_hours, task_family=spec["task_family"]))
    return metrics


def compute_metric(
    db: Session,
    metric_key: str,
    *,
    window_hours: int,
    task_family: str | None = None,
) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    if metric_key == "task_success_rate":
        return _rate_metric(
            metric_key,
            task_family,
            window_hours,
            numerator=_task_run_count(db, since, task_family=task_family, statuses={"success"}),
            denominator=_task_run_count(db, since, task_family=task_family),
        )
    if metric_key == "task_fallback_rate":
        return _rate_metric(
            metric_key,
            task_family,
            window_hours,
            numerator=_task_run_count(db, since, task_family=task_family, statuses={"fallback", "partial"}),
            denominator=_task_run_count(db, since, task_family=task_family),
        )
    if metric_key == "unknown_case_rate":
        return _rate_metric(
            metric_key,
            task_family,
            window_hours,
            numerator=_unknown_case_count(db, since, task_family=task_family),
            denominator=_task_run_count(db, since, task_family=task_family),
        )
    if metric_key == "generic_portion_fallback_rate":
        return _rate_metric(
            metric_key,
            task_family,
            window_hours,
            numerator=_generic_portion_count(db, since, task_family=task_family),
            denominator=_uncertainty_count(db, since, task_family=task_family),
        )
    if metric_key == "suggested_update_apply_rate":
        total = _feedback_count(db, since, feedback_labels={"accepted_async_update", "dismissed_async_update"})
        numerator = _feedback_count(db, since, feedback_labels={"accepted_async_update"})
        return _rate_metric(metric_key, task_family, window_hours, numerator=numerator, denominator=total)
    if metric_key == "suggested_update_dismiss_rate":
        total = _feedback_count(db, since, feedback_labels={"accepted_async_update", "dismissed_async_update"})
        numerator = _feedback_count(db, since, feedback_labels={"dismissed_async_update"})
        return _rate_metric(metric_key, task_family, window_hours, numerator=numerator, denominator=total)
    if metric_key == "dissatisfaction_rate":
        denominator = _conversation_count(db, since, task_family=task_family)
        numerator = _feedback_count(db, since, explicit_negative_only=True, task_family=task_family)
        return _rate_metric(metric_key, task_family, window_hours, numerator=numerator, denominator=denominator)
    if metric_key == "degraded_error_rate":
        numerator = _degraded_error_count(db, since, task_family=task_family)
        denominator = _task_run_count(db, since, task_family=task_family)
        return _rate_metric(metric_key, task_family, window_hours, numerator=numerator, denominator=denominator)
    if metric_key == "retry_exhausted_count":
        numerator = _retry_exhausted_count(db, since, task_family=task_family)
        return {
            "metric_key": metric_key,
            "task_family": task_family,
            "window_hours": window_hours,
            "value": float(numerator),
            "numerator": float(numerator),
            "denominator": 0.0,
            "sample_size": int(numerator),
            "dimensions": {},
        }
    raise ValueError(f"Unsupported metric key: {metric_key}")


def evaluate_alert_rules(db: Session) -> list[AlertEvent]:
    rules = ensure_default_alert_rules(db)
    now = datetime.now(timezone.utc)
    triggered: list[AlertEvent] = []

    for rule in rules:
        if rule.status != "active":
            continue
        metric = compute_metric(db, rule.metric_key, window_hours=rule.window_hours, task_family=rule.task_family)
        _capture_metric_snapshot(db, metric)
        if metric["sample_size"] < rule.min_sample_size:
            continue
        if not _compare(metric["value"], rule.comparator, rule.threshold):
            continue

        open_alert = (
            db.query(AlertEvent)
            .filter(AlertEvent.rule_id == rule.id, AlertEvent.status == "open")
            .order_by(AlertEvent.last_seen_at.desc())
            .first()
        )
        cooldown_until = (rule.last_triggered_at or datetime.fromtimestamp(0, tz=timezone.utc)) + timedelta(minutes=rule.cooldown_minutes)
        if open_alert and now < cooldown_until:
            open_alert.last_seen_at = now
            open_alert.occurrence_count += 1
            open_alert.metric_value = metric["value"]
            open_alert.sample_size = metric["sample_size"]
            open_alert.payload = {**(open_alert.payload or {}), "metric": metric}
            db.add(open_alert)
            db.commit()
            triggered.append(open_alert)
            continue

        alert = AlertEvent(
            id=str(uuid.uuid4()),
            rule_id=rule.id,
            metric_key=rule.metric_key,
            task_family=rule.task_family,
            severity=rule.severity,
            status="open",
            title=_build_alert_title(rule),
            summary=_build_alert_summary(rule, metric),
            metric_value=metric["value"],
            threshold=rule.threshold,
            sample_size=metric["sample_size"],
            payload={"metric": metric, "dimensions": rule.dimensions or {}},
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=1,
        )
        db.add(alert)
        rule.last_triggered_at = now
        db.add(rule)
        db.commit()
        db.refresh(alert)
        _enqueue_alert_review_item(db, alert)
        triggered.append(alert)

    return triggered


def _task_run_count(db: Session, since: datetime, *, task_family: str | None = None, statuses: set[str] | None = None) -> int:
    query = db.query(TaskRun).filter(TaskRun.started_at >= since)
    if task_family:
        query = query.filter(TaskRun.task_family == task_family)
    if statuses:
        query = query.filter(TaskRun.status.in_(statuses))
    return query.count()


def _unknown_case_count(db: Session, since: datetime, *, task_family: str | None = None) -> int:
    query = db.query(UnknownCaseEvent).filter(UnknownCaseEvent.created_at >= since)
    if task_family:
        query = query.filter(UnknownCaseEvent.task_family == task_family)
    return query.count()


def _uncertainty_count(db: Session, since: datetime, *, task_family: str | None = None) -> int:
    query = db.query(UncertaintyEvent).filter(UncertaintyEvent.created_at >= since)
    if task_family:
        query = query.filter(UncertaintyEvent.task_family == task_family)
    return query.count()


def _generic_portion_count(db: Session, since: datetime, *, task_family: str | None = None) -> int:
    query = db.query(UncertaintyEvent).filter(
        UncertaintyEvent.created_at >= since,
        UncertaintyEvent.used_generic_portion_estimate.is_(True),
    )
    if task_family:
        query = query.filter(UncertaintyEvent.task_family == task_family)
    return query.count()


def _conversation_count(db: Session, since: datetime, *, task_family: str | None = None) -> int:
    query = db.query(ConversationTrace).filter(ConversationTrace.created_at >= since)
    if task_family:
        query = query.filter(ConversationTrace.task_family == task_family)
    return query.count()


def _feedback_count(
    db: Session,
    since: datetime,
    *,
    explicit_negative_only: bool = False,
    feedback_labels: set[str] | None = None,
    task_family: str | None = None,
) -> int:
    query = db.query(FeedbackEvent).filter(FeedbackEvent.created_at >= since)
    if explicit_negative_only:
        query = query.filter(FeedbackEvent.feedback_type == "explicit_negative")
    if feedback_labels:
        query = query.filter(FeedbackEvent.feedback_label.in_(feedback_labels))
    if task_family:
        trace_ids = [
            row[0]
            for row in db.query(ConversationTrace.id)
            .filter(ConversationTrace.created_at >= since, ConversationTrace.task_family == task_family)
            .all()
        ]
        if not trace_ids:
            return 0
        query = query.filter(
            or_(
                FeedbackEvent.trace_id.in_(trace_ids),
                FeedbackEvent.target_trace_id.in_(trace_ids),
            )
        )
    return query.count()


def _degraded_error_count(db: Session, since: datetime, *, task_family: str | None = None) -> int:
    query = db.query(ErrorEvent).filter(
        ErrorEvent.created_at >= since,
        ErrorEvent.user_visible_impact.in_({"degraded", "failed_request", "silent_background_failure"}),
    )
    if task_family:
        task_ids = [
            row[0]
            for row in db.query(TaskRun.id)
            .filter(TaskRun.started_at >= since, TaskRun.task_family == task_family)
            .all()
        ]
        if not task_ids:
            return 0
        query = query.filter(ErrorEvent.task_run_id.in_(task_ids))
    return query.count()


def _retry_exhausted_count(db: Session, since: datetime, *, task_family: str | None = None) -> int:
    query = db.query(ErrorEvent).filter(ErrorEvent.created_at >= since, ErrorEvent.error_code == "job_retry_exhausted")
    if task_family:
        task_ids = [
            row[0]
            for row in db.query(TaskRun.id)
            .filter(TaskRun.started_at >= since, TaskRun.task_family == task_family)
            .all()
        ]
        if not task_ids:
            return 0
        query = query.filter(ErrorEvent.task_run_id.in_(task_ids))
    return query.count()


def _rate_metric(metric_key: str, task_family: str | None, window_hours: int, *, numerator: int, denominator: int) -> dict[str, Any]:
    sample_size = denominator
    value = round(numerator / denominator, 4) if denominator else 0.0
    return {
        "metric_key": metric_key,
        "task_family": task_family,
        "window_hours": window_hours,
        "value": value,
        "numerator": float(numerator),
        "denominator": float(denominator),
        "sample_size": sample_size,
        "dimensions": {},
    }


def _compare(value: float, comparator: str, threshold: float) -> bool:
    if comparator == "gt":
        return value > threshold
    if comparator == "gte":
        return value >= threshold
    if comparator == "lt":
        return value < threshold
    if comparator == "lte":
        return value <= threshold
    raise ValueError(f"Unsupported comparator: {comparator}")


def _capture_metric_snapshot(db: Session, metric: dict[str, Any]) -> ObservabilityMetricSnapshot:
    row = ObservabilityMetricSnapshot(
        id=str(uuid.uuid4()),
        metric_key=metric["metric_key"],
        task_family=metric.get("task_family"),
        window_hours=int(metric["window_hours"]),
        value=float(metric["value"]),
        numerator=float(metric.get("numerator", 0.0)),
        denominator=float(metric.get("denominator", 0.0)),
        sample_size=int(metric.get("sample_size", 0)),
        dimensions=metric.get("dimensions", {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _build_alert_title(rule: AlertRule) -> str:
    task_part = f" ({rule.task_family})" if rule.task_family else ""
    return f"{rule.metric_key}{task_part}"


def _build_alert_summary(rule: AlertRule, metric: dict[str, Any]) -> str:
    return (
        f"Metric {rule.metric_key} for {rule.task_family or 'global'} is {metric['value']}, "
        f"threshold {rule.comparator} {rule.threshold}, sample {metric['sample_size']}."
    )


def _enqueue_alert_review_item(db: Session, alert: AlertEvent) -> None:
    existing = db.query(ReviewQueueItem).filter_by(source_table="alert_events", source_id=alert.id).one_or_none()
    if existing:
        return
    row = ReviewQueueItem(
        queue_type="alert",
        priority=0 if alert.severity == "critical" else 1,
        task_family=alert.task_family,
        trace_id=None,
        source_table="alert_events",
        source_id=alert.id,
        title=alert.title,
        summary=alert.summary,
        normalized_label=alert.metric_key,
        payload=alert.payload or {},
    )
    db.add(row)
    db.commit()


def _build_summary_cards(db: Session, *, since: datetime, window_hours: int) -> list[dict[str, Any]]:
    open_alerts = db.query(AlertEvent).filter(AlertEvent.status == "open").count()
    critical_alerts = db.query(AlertEvent).filter(AlertEvent.status == "open", AlertEvent.severity == "critical").count()
    new_review_items = db.query(ReviewQueueItem).filter(ReviewQueueItem.status == "new").count()
    retry_exhausted = _retry_exhausted_count(db, since)
    recommendation_sessions = db.query(RecommendationSession).filter(RecommendationSession.created_at >= since).all()
    recommendation_session_count = len(recommendation_sessions)
    accepted_top_pick = sum(1 for row in recommendation_sessions if row.accepted_event_type == "accepted_top_pick")
    top_pick_accept_rate = (accepted_top_pick / recommendation_session_count) if recommendation_session_count else 0.0
    body_goal_count = db.query(BodyGoal).count()
    target_weight_count = db.query(BodyGoal).filter(BodyGoal.target_weight_kg.is_not(None)).count()
    body_goal_coverage = (target_weight_count / body_goal_count) if body_goal_count else 0.0
    activity_adjustment_count = db.query(ActivityAdjustment).filter(ActivityAdjustment.created_at >= since).count()
    unknown_rate = compute_metric(
        db,
        "unknown_case_rate",
        window_hours=window_hours,
        task_family="nutrition_or_food_qa",
    )
    dissatisfaction_rate = compute_metric(db, "dissatisfaction_rate", window_hours=window_hours, task_family=None)
    return [
        {
            "key": "open_alerts",
            "title": "Open Alerts",
            "value": open_alerts,
            "status": "critical" if critical_alerts else ("warning" if open_alerts else "healthy"),
            "subtitle": f"{critical_alerts} critical",
        },
        {
            "key": "review_queue_new",
            "title": "New Review Items",
            "value": new_review_items,
            "status": "warning" if new_review_items else "healthy",
            "subtitle": "Needs triage",
        },
        {
            "key": "nutrition_unknown_rate",
            "title": "Nutrition Unknown Rate",
            "value": round(unknown_rate["value"], 4),
            "status": "warning" if unknown_rate["value"] > 0.2 else "healthy",
            "subtitle": f"{unknown_rate['sample_size']} samples / {window_hours}h",
        },
        {
            "key": "dissatisfaction_rate",
            "title": "Dissatisfaction Rate",
            "value": round(dissatisfaction_rate["value"], 4),
            "status": "warning" if dissatisfaction_rate["value"] > 0.1 else "healthy",
            "subtitle": f"{dissatisfaction_rate['sample_size']} traces / {window_hours}h",
        },
        {
            "key": "eat_feed_sessions",
            "title": "Eat Feed Sessions",
            "value": recommendation_session_count,
            "status": "healthy" if recommendation_session_count else "neutral",
            "subtitle": f"Last {window_hours}h",
        },
        {
            "key": "top_pick_accept_rate",
            "title": "Top Pick Accept Rate",
            "value": round(top_pick_accept_rate, 4),
            "status": "warning" if recommendation_session_count >= 5 and top_pick_accept_rate < 0.25 else ("healthy" if recommendation_session_count else "neutral"),
            "subtitle": f"{accepted_top_pick} accepted / {recommendation_session_count} shown",
        },
        {
            "key": "body_goal_coverage",
            "title": "Body Goal Coverage",
            "value": round(body_goal_coverage, 4),
            "status": "warning" if body_goal_count and body_goal_coverage < 0.5 else ("healthy" if body_goal_count else "neutral"),
            "subtitle": f"{target_weight_count} with target / {body_goal_count} total",
        },
        {
            "key": "activity_adjustments",
            "title": "Activity Adjustments",
            "value": activity_adjustment_count,
            "status": "healthy" if activity_adjustment_count else "neutral",
            "subtitle": f"Manual + chat-adjusted events / {window_hours}h",
        },
        {
            "key": "retry_exhausted",
            "title": "Retry Exhausted",
            "value": retry_exhausted,
            "status": "critical" if retry_exhausted else "healthy",
            "subtitle": f"Last {window_hours}h",
        },
    ]


def _build_task_health(db: Session, *, window_hours: int) -> list[dict[str, Any]]:
    task_families = [
        row[0]
        for row in db.query(TaskRun.task_family)
        .filter(TaskRun.task_family.is_not(None))
        .distinct()
        .order_by(TaskRun.task_family.asc())
        .all()
        if row[0]
    ]
    health_rows: list[dict[str, Any]] = []
    for task_family in task_families:
        success = compute_metric(db, "task_success_rate", window_hours=window_hours, task_family=task_family)
        fallback = compute_metric(db, "task_fallback_rate", window_hours=window_hours, task_family=task_family)
        unknown = compute_metric(db, "unknown_case_rate", window_hours=window_hours, task_family=task_family)
        dissatisfaction = compute_metric(db, "dissatisfaction_rate", window_hours=window_hours, task_family=task_family)
        sample_size = int(max(success["sample_size"], fallback["sample_size"], unknown["sample_size"], dissatisfaction["sample_size"]))
        health_rows.append(
            {
                "task_family": task_family,
                "sample_size": sample_size,
                "success_rate": round(success["value"], 4),
                "fallback_rate": round(fallback["value"], 4),
                "unknown_case_rate": round(unknown["value"], 4),
                "dissatisfaction_rate": round(dissatisfaction["value"], 4),
            }
        )
    return sorted(health_rows, key=lambda item: (item["dissatisfaction_rate"], item["fallback_rate"], item["unknown_case_rate"]), reverse=True)


def _build_quality_trends(db: Session, *, trend_days: int) -> dict[str, list[dict[str, Any]]]:
    return {
        "unknown_cases": _daily_count_series(db, UnknownCaseEvent.created_at, UnknownCaseEvent, trend_days=trend_days),
        "explicit_negative_feedback": _daily_filtered_count_series(
            db,
            FeedbackEvent.created_at,
            FeedbackEvent,
            trend_days=trend_days,
            filters=(FeedbackEvent.feedback_type == "explicit_negative",),
        ),
        "degraded_errors": _daily_filtered_count_series(
            db,
            ErrorEvent.created_at,
            ErrorEvent,
            trend_days=trend_days,
            filters=(ErrorEvent.user_visible_impact.in_({"degraded", "failed_request", "silent_background_failure"}),),
        ),
        "review_queue_new": _daily_filtered_count_series(
            db,
            ReviewQueueItem.created_at,
            ReviewQueueItem,
            trend_days=trend_days,
            filters=(ReviewQueueItem.status == "new",),
        ),
    }


def _build_operational_panels(db: Session, *, since: datetime) -> dict[str, Any]:
    component_rows = (
        db.query(
            ErrorEvent.component,
            func.count(ErrorEvent.id),
            func.sum(case((ErrorEvent.severity == "critical", 1), else_=0)),
            func.sum(case((ErrorEvent.user_visible_impact.in_(("degraded", "failed_request", "silent_background_failure")), 1), else_=0)),
            func.max(ErrorEvent.created_at),
        )
        .filter(ErrorEvent.created_at >= since)
        .group_by(ErrorEvent.component)
        .order_by(func.count(ErrorEvent.id).desc(), ErrorEvent.component.asc())
        .all()
    )
    error_by_component = [
        {
            "component": component or "unknown",
            "total_count": int(total or 0),
            "critical_count": int(critical or 0),
            "degraded_count": int(degraded or 0),
            "last_seen_at": last_seen,
        }
        for component, total, critical, degraded, last_seen in component_rows
    ]
    error_code_rows = (
        db.query(ErrorEvent.error_code, func.count(ErrorEvent.id))
        .filter(ErrorEvent.created_at >= since)
        .group_by(ErrorEvent.error_code)
        .order_by(func.count(ErrorEvent.id).desc(), ErrorEvent.error_code.asc())
        .limit(10)
        .all()
    )
    return {
        "error_by_component": error_by_component,
        "top_error_codes": [{"label": code or "unknown", "count": int(count or 0)} for code, count in error_code_rows],
    }


def _build_webhook_queue_panels(db: Session) -> dict[str, Any]:
    """Build webhook queue depth and worker lag monitoring panels."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    # Inbound events stats
    inbound_pending = db.query(InboundEvent).filter(InboundEvent.status == "pending").count()
    inbound_running = db.query(InboundEvent).filter(InboundEvent.status == "running").count()
    # Stuck events: running but lease expired (compare as UTC)
    stuck_cutoff = now - timedelta(minutes=5)
    inbound_stuck = (
        db.query(InboundEvent)
        .filter(
            InboundEvent.status == "running",
            InboundEvent.lease_expires_at < stuck_cutoff,
        )
        .count()
    )
    # Average queue age for pending events
    oldest_pending = db.query(InboundEvent.created_at).filter(InboundEvent.status == "pending").order_by(InboundEvent.created_at.asc()).first()
    avg_queue_age_seconds = 0.0
    if oldest_pending and oldest_pending[0]:
        pending_created = oldest_pending[0]
        # Handle naive datetime by assuming UTC
        if pending_created.tzinfo is None:
            pending_created = pending_created.replace(tzinfo=timezone.utc)
        avg_queue_age_seconds = (now - pending_created).total_seconds()
    # Worker lag: time since oldest pending event
    worker_lag_seconds = avg_queue_age_seconds

    # Search jobs stats
    search_pending = db.query(SearchJob).filter(SearchJob.status == "pending").count()
    search_running = db.query(SearchJob).filter(SearchJob.status == "running").count()
    search_stuck = (
        db.query(SearchJob)
        .filter(
            SearchJob.status == "running",
            SearchJob.lease_expires_at < stuck_cutoff,
        )
        .count()
    )

    return {
        "inbound_events": {
            "pending": inbound_pending,
            "running": inbound_running,
            "stuck": inbound_stuck,
            "avg_queue_age_seconds": round(avg_queue_age_seconds, 1),
            "worker_lag_seconds": round(worker_lag_seconds, 1),
        },
        "search_jobs": {
            "pending": search_pending,
            "running": search_running,
            "stuck": search_stuck,
        },
        "health_status": (
            "critical" if inbound_stuck > 0 or search_stuck > 0
            else "warning" if inbound_pending > 50 or search_pending > 50
            else "healthy"
        ),
    }


def _build_notification_panels(db: Session, *, since: datetime) -> dict[str, Any]:
    """Build notification delivery tracking panels."""
    notifications = (
        db.query(Notification)
        .filter(Notification.created_at >= since)
        .all()
    )
    total_count = len(notifications)
    by_type: dict[str, dict[str, int]] = {}
    by_status: dict[str, int] = {}
    for notif in notifications:
        notif_type = notif.type or "unknown"
        notif_status = notif.status or "unknown"
        by_type.setdefault(notif_type, {"total": 0, "unread": 0, "read": 0})
        by_type[notif_type]["total"] += 1
        if notif_status == "unread":
            by_type[notif_type]["unread"] += 1
        elif notif_status == "read":
            by_type[notif_type]["read"] += 1
        by_status[notif_status] = by_status.get(notif_status, 0) + 1

    # Calculate push delivery metrics (unread notifications that are not 'read' yet might indicate delivery issues)
    # For now, track by status distribution
    return {
        "total_notifications": total_count,
        "by_type": [
            {"type": notif_type, "total": stats["total"], "unread": stats["unread"], "read": stats["read"]}
            for notif_type, stats in sorted(by_type.items(), key=lambda x: -x[1]["total"])
        ],
        "by_status": [{"status": status, "count": count} for status, count in sorted(by_status.items(), key=lambda x: -x[1])],
        "health_status": (
            "critical" if by_status.get("failed", 0) > 5
            else "warning" if by_status.get("failed", 0) > 0
            else "healthy"
        ),
    }


def _build_usage_panels(db: Session, *, since: datetime) -> dict[str, Any]:
    model_rows = (
        db.query(TaskRun.provider_name, TaskRun.model_name, func.count(TaskRun.id), func.avg(TaskRun.latency_ms))
        .filter(TaskRun.started_at >= since)
        .group_by(TaskRun.provider_name, TaskRun.model_name)
        .order_by(func.count(TaskRun.id).desc())
        .limit(12)
        .all()
    )
    provider_rows = (
        db.query(TaskRun.provider_name, func.count(TaskRun.id))
        .filter(TaskRun.started_at >= since)
        .group_by(TaskRun.provider_name)
        .order_by(func.count(TaskRun.id).desc())
        .all()
    )
    recent_runs = db.query(TaskRun).filter(TaskRun.started_at >= since).all()
    execution_phase_rows = _group_task_runs_by_summary(recent_runs, key="execution_phase")
    ingress_mode_rows = _group_task_runs_by_summary(recent_runs, key="ingress_mode")
    route_policy_rows = _group_task_runs_by_summary(recent_runs, key="route_policy")
    llm_cache_rows = _group_task_runs_by_summary(recent_runs, key="llm_cache")
    route_target_rows = _group_task_runs_by_summary(recent_runs, key="route_target")
    planning_copy_rows = _group_task_runs_by_summary(recent_runs, key="planning_copy_layer")
    saved_local_count = sum(row["count"] for row in route_target_rows if row["label"] == "heuristic")
    remote_llm_count = sum(row["count"] for row in route_target_rows if row["label"] == "builderspace")
    usage_rows = [_extract_llm_usage(row.result_summary or {}) for row in recent_runs]
    usage_rows = [row for row in usage_rows if row]
    prompt_tokens = sum(int(row.get("prompt_tokens") or 0) for row in usage_rows)
    completion_tokens = sum(int(row.get("completion_tokens") or 0) for row in usage_rows)
    total_tokens = sum(int(row.get("total_tokens") or 0) for row in usage_rows)
    estimated_cost_usd = round(sum(float(row.get("estimated_cost_usd") or 0.0) for row in usage_rows), 6)
    usage_requests = sum(int(row.get("request_count") or 0) for row in usage_rows)
    latest_budget_snapshot = {}
    for row in usage_rows:
        for key in (
            "request_budget_per_hour",
            "token_budget_per_hour",
            "cost_budget_usd_per_day",
            "rate_limit_remaining_requests",
            "rate_limit_remaining_tokens",
            "rate_limit_reset_requests_s",
            "rate_limit_reset_tokens_s",
        ):
            if row.get(key) is not None:
                latest_budget_snapshot[key] = row.get(key)
    token_usage_available = bool(usage_rows)
    return {
        "token_usage_available": token_usage_available,
        "note": (
            "Token and cost accounting is aggregated from task-run llm_usage metadata. "
            "Runs without provider usage metadata are excluded from the precise totals."
            if token_usage_available
            else "This panel currently shows provider/model request volume and latency. Precise token and cost totals appear once llm_usage metadata is present in task runs."
        ),
        "provider_request_counts": [
            {"label": provider or "unknown", "count": int(count or 0)}
            for provider, count in provider_rows
        ],
        "model_request_breakdown": [
            {
                "provider_name": provider or "unknown",
                "model_name": model or "unknown",
                "request_count": int(count or 0),
                "avg_latency_ms": int(avg_latency or 0),
            }
            for provider, model, count, avg_latency in model_rows
        ],
        "execution_phase_breakdown": execution_phase_rows,
        "ingress_mode_breakdown": ingress_mode_rows,
        "route_policy_breakdown": route_policy_rows,
        "llm_cache_breakdown": llm_cache_rows,
        "route_target_breakdown": route_target_rows,
        "planning_copy_breakdown": planning_copy_rows,
        "token_cost_summary": {
            "tracked_request_count": usage_requests,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens or (prompt_tokens + completion_tokens),
            "estimated_cost_usd": estimated_cost_usd,
        },
        "budget_snapshot": latest_budget_snapshot,
        "packet_coverage_summary": {
            "memory_packet_present_runs": _count_task_runs_with_summary_value(recent_runs, key="memory_packet_present", expected="True"),
            "communication_profile_present_runs": _count_task_runs_with_summary_value(recent_runs, key="communication_profile_present", expected="True"),
            "planning_copy_attempted_runs": _count_task_runs_with_summary_value(recent_runs, key="planning_copy_attempted", expected="True"),
        },
        "llm_path_summary": {
            "saved_local_requests": saved_local_count,
            "remote_llm_requests": remote_llm_count,
            "cache_hits": sum(row["count"] for row in llm_cache_rows if row["label"] == "hit"),
            "webhook_ingress_events": sum(row["count"] for row in execution_phase_rows if row["label"] == "webhook_ingress"),
            "webhook_worker_runs": sum(row["count"] for row in execution_phase_rows if row["label"] == "webhook_worker"),
        },
    }


def _extract_llm_usage(summary: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    candidates = [
        summary.get("llm_usage"),
        (summary.get("recommendation_policy") or {}).get("llm_usage") if isinstance(summary.get("recommendation_policy"), dict) else None,
        (summary.get("weekly_coaching") or {}).get("llm_usage") if isinstance(summary.get("weekly_coaching"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _build_canary_transcript_review(
    db: Session,
    *,
    canary_runs: list[TaskRun],
    limit: int,
) -> list[dict[str, Any]]:
    if not canary_runs:
        return []
    review_items: list[dict[str, Any]] = []
    seen_trace_ids: set[str] = set()
    for run in canary_runs:
        if run.trace_id in seen_trace_ids:
            continue
        seen_trace_ids.add(run.trace_id)
        trace = db.get(ConversationTrace, run.trace_id)
        if trace is None:
            continue
        feedback_rows = (
            db.query(FeedbackEvent)
            .filter(FeedbackEvent.trace_id == run.trace_id)
            .order_by(FeedbackEvent.created_at.asc())
            .all()
        )
        outcome_rows = (
            db.query(OutcomeEvent)
            .filter(OutcomeEvent.trace_id == run.trace_id)
            .order_by(OutcomeEvent.created_at.asc())
            .all()
        )
        review_items.append(
            {
                "trace_id": run.trace_id,
                "task_family": run.task_family,
                "surface": trace.surface,
                "traffic_class": trace.traffic_class,
                "created_at": trace.created_at,
                "input_text": trace.input_text,
                "provider_name": run.provider_name,
                "model_name": run.model_name,
                "status": run.status,
                "fallback_reason": run.fallback_reason,
                "result_summary": run.result_summary or {},
                "feedback_labels": [row.feedback_label for row in feedback_rows],
                "outcome_types": [row.outcome_type for row in outcome_rows],
                "review_reason": "canary_transcript_review",
            }
        )
        if len(review_items) >= limit:
            break
    return review_items


def _build_product_panels(db: Session, *, since: datetime) -> dict[str, Any]:
    sessions = (
        db.query(RecommendationSession)
        .filter(RecommendationSession.created_at >= since)
        .order_by(RecommendationSession.created_at.desc())
        .all()
    )
    session_count = len(sessions)
    accepted_top_pick = sum(1 for row in sessions if row.accepted_event_type == "accepted_top_pick")
    accepted_backup_pick = sum(1 for row in sessions if row.accepted_event_type == "accepted_backup_pick")
    accepted_nearby = sum(1 for row in sessions if row.accepted_event_type == "accepted_nearby_new")
    corrected_after_acceptance = sum(1 for row in sessions if row.accepted_event_type == "post_log_manual_correction")

    status_buckets: dict[str, int] = {}
    source_buckets: dict[str, int] = {}
    latest_sessions: list[dict[str, Any]] = []
    for row in sessions[:10]:
        shown_top_pick = row.shown_top_pick or {}
        latest_sessions.append(
            {
                "id": row.id,
                "created_at": row.created_at,
                "status": row.status,
                "top_pick_title": shown_top_pick.get("title", ""),
                "top_pick_source": shown_top_pick.get("source_type", ""),
                "accepted_event_type": row.accepted_event_type,
            }
        )
    for row in sessions:
        status_buckets[row.status or "unknown"] = status_buckets.get(row.status or "unknown", 0) + 1
        shown_source = str((row.shown_top_pick or {}).get("source_type") or "unknown")
        source_buckets[shown_source] = source_buckets.get(shown_source, 0) + 1

    profile_count = db.query(RecommendationProfile).count()
    avg_profile_sample_size = float(db.query(func.avg(RecommendationProfile.sample_size)).scalar() or 0.0)
    body_goal_count = db.query(BodyGoal).count()
    target_weight_count = db.query(BodyGoal).filter(BodyGoal.target_weight_kg.is_not(None)).count()
    activity_adjustment_count = db.query(ActivityAdjustment).filter(ActivityAdjustment.created_at >= since).count()
    proactive_notifications = (
        db.query(Notification)
        .filter(
            Notification.created_at >= since,
            Notification.type.in_(("daily_nudge", "meal_event_reminder", "dinner_pick")),
        )
        .all()
    )
    proactive_buckets = {
        "daily_nudge": sum(1 for row in proactive_notifications if row.type == "daily_nudge"),
        "meal_event_reminder": sum(1 for row in proactive_notifications if row.type == "meal_event_reminder"),
        "dinner_pick": sum(1 for row in proactive_notifications if row.type == "dinner_pick"),
    }
    meal_event_count = db.query(MealEvent).filter(MealEvent.created_at >= since).count()
    knowledge_summary = knowledge_runtime_status()

    return {
        "recommendation_summary": {
            "sessions": session_count,
            "accepted_top_pick": accepted_top_pick,
            "accepted_backup_pick": accepted_backup_pick,
            "accepted_nearby": accepted_nearby,
            "corrected_after_acceptance": corrected_after_acceptance,
            "top_pick_accept_rate": round((accepted_top_pick / session_count), 4) if session_count else 0.0,
            "backup_pick_accept_rate": round((accepted_backup_pick / session_count), 4) if session_count else 0.0,
            "nearby_accept_rate": round((accepted_nearby / session_count), 4) if session_count else 0.0,
            "correction_rate": round((corrected_after_acceptance / session_count), 4) if session_count else 0.0,
        },
        "body_goal_summary": {
            "body_goal_users": body_goal_count,
            "target_weight_users": target_weight_count,
            "target_weight_coverage": round((target_weight_count / body_goal_count), 4) if body_goal_count else 0.0,
            "activity_adjustment_events": activity_adjustment_count,
            "recommendation_profiles": profile_count,
            "avg_profile_sample_size": round(avg_profile_sample_size, 2),
        },
        "proactive_summary": {
            "daily_nudges": proactive_buckets["daily_nudge"],
            "meal_event_reminders": proactive_buckets["meal_event_reminder"],
            "dinner_picks": proactive_buckets["dinner_pick"],
            "meal_events_created": meal_event_count,
        },
        "knowledge_summary": knowledge_summary,
        "recommendation_status_breakdown": [
            {"label": label, "count": count}
            for label, count in sorted(status_buckets.items(), key=lambda item: (-item[1], item[0]))
        ],
        "recommendation_source_breakdown": [
            {"label": label, "count": count}
            for label, count in sorted(source_buckets.items(), key=lambda item: (-item[1], item[0]))
        ],
        "latest_recommendation_sessions": latest_sessions,
    }


def _group_task_runs_by_summary(task_runs: list[TaskRun], *, key: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[int]] = {}
    for row in task_runs:
        label = _task_run_summary_value(row, key) or "unknown"
        buckets.setdefault(label, [])
        if row.latency_ms is not None:
            buckets[label].append(int(row.latency_ms))
    counts: dict[str, int] = {}
    for row in task_runs:
        label = _task_run_summary_value(row, key) or "unknown"
        counts[label] = counts.get(label, 0) + 1
    items = []
    for label, count in counts.items():
        latencies = buckets.get(label, [])
        items.append(
            {
                "label": label,
                "count": int(count),
                "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
            }
        )
    items.sort(key=lambda item: (-item["count"], item["label"]))
    return items


def _group_task_runs_by_attr(task_runs: list[TaskRun], *, attr: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[int]] = {}
    counts: dict[str, int] = {}
    for row in task_runs:
        value = getattr(row, attr, None)
        label = str(value).strip() if value is not None and str(value).strip() else "unknown"
        counts[label] = counts.get(label, 0) + 1
        buckets.setdefault(label, [])
        if row.latency_ms is not None:
            buckets[label].append(int(row.latency_ms))
    items = []
    for label, count in counts.items():
        latencies = buckets.get(label, [])
        items.append(
            {
                "label": label,
                "count": int(count),
                "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
            }
        )
    items.sort(key=lambda item: (-item["count"], item["label"]))
    return items


def _count_task_runs_with_summary_value(task_runs: list[TaskRun], *, key: str, expected: str) -> int:
    return sum(1 for row in task_runs if (_task_run_summary_value(row, key) or "") == expected)


def _build_memory_panels(db: Session, *, user_id: int | None) -> dict[str, Any]:
    if user_id is None:
        primary_user = db.query(User).order_by(User.updated_at.desc(), User.created_at.desc()).first()
        user_id = primary_user.id if primary_user else None

    query_signals = db.query(MemorySignal)
    query_hypotheses = db.query(MemoryHypothesis)
    bias_query = db.query(ReportingBias)
    if user_id is not None:
        query_signals = query_signals.filter(MemorySignal.user_id == user_id)
        query_hypotheses = query_hypotheses.filter(MemoryHypothesis.user_id == user_id)
        bias_query = bias_query.filter(ReportingBias.user_id == user_id)

    total_signals = query_signals.count()
    stable_signals = query_signals.filter(MemorySignal.status.in_(("stable", "decaying"))).count()
    active_hypotheses = query_hypotheses.filter(MemoryHypothesis.status == "active").count()
    tentative_hypotheses = query_hypotheses.filter(MemoryHypothesis.status == "tentative").count()
    signal_dimension_rows = (
        query_signals.with_entities(MemorySignal.dimension, func.count(MemorySignal.id))
        .group_by(MemorySignal.dimension)
        .order_by(func.count(MemorySignal.id).desc(), MemorySignal.dimension.asc())
        .limit(10)
        .all()
    )
    top_signals = (
        query_signals.order_by(MemorySignal.evidence_score.desc(), MemorySignal.last_seen_at.desc())
        .limit(8)
        .all()
    )
    top_hypotheses = (
        query_hypotheses.order_by(MemoryHypothesis.confidence.desc(), MemoryHypothesis.last_confirmed_at.desc())
        .limit(8)
        .all()
    )
    bias = bias_query.one_or_none()
    return {
        "scope": "current_user" if user_id is not None else "global",
        "summary": {
            "total_signals": total_signals,
            "stable_signals": stable_signals,
            "active_hypotheses": active_hypotheses,
            "tentative_hypotheses": tentative_hypotheses,
        },
        "top_signal_dimensions": [
            {"label": dimension or "unknown", "count": int(count or 0)}
            for dimension, count in signal_dimension_rows
        ],
        "top_signals": [
            {
                "pattern_type": row.pattern_type,
                "dimension": row.dimension,
                "canonical_label": row.canonical_label,
                "status": row.status,
                "evidence_score": round(row.evidence_score or 0.0, 3),
                "counter_evidence_score": round(row.counter_evidence_score or 0.0, 3),
            }
            for row in top_signals
        ],
        "top_hypotheses": [
            {
                "dimension": row.dimension,
                "label": row.label,
                "status": row.status,
                "confidence": round(row.confidence or 0.0, 3),
                "evidence_count": row.evidence_count,
                "counter_evidence_count": row.counter_evidence_count,
            }
            for row in top_hypotheses
        ],
        "reporting_bias": {
            "underreport_score": round(bias.underreport_score, 3) if bias else 0.0,
            "overreport_score": round(bias.overreport_score, 3) if bias else 0.0,
            "vagueness_score": round(bias.vagueness_score, 3) if bias else 0.0,
            "missing_detail_score": round(bias.missing_detail_score, 3) if bias else 0.0,
            "log_confidence_score": round(bias.log_confidence_score, 3) if bias else 0.0,
        },
    }


def _build_eval_panels(db: Session, *, since: datetime) -> dict[str, Any]:
    recent_runs = db.query(TaskRun).filter(TaskRun.started_at >= since).all()
    unknown_label_rows = (
        db.query(UnknownCaseEvent.unknown_type, func.count(UnknownCaseEvent.id))
        .filter(UnknownCaseEvent.created_at >= since)
        .group_by(UnknownCaseEvent.unknown_type)
        .order_by(func.count(UnknownCaseEvent.id).desc(), UnknownCaseEvent.unknown_type.asc())
        .limit(10)
        .all()
    )
    feedback_label_rows = (
        db.query(FeedbackEvent.feedback_label, func.count(FeedbackEvent.id))
        .filter(FeedbackEvent.created_at >= since, FeedbackEvent.feedback_label.is_not(None))
        .group_by(FeedbackEvent.feedback_label)
        .order_by(func.count(FeedbackEvent.id).desc(), FeedbackEvent.feedback_label.asc())
        .limit(10)
        .all()
    )
    error_code_rows = (
        db.query(ErrorEvent.error_code, func.count(ErrorEvent.id))
        .filter(
            ErrorEvent.created_at >= since,
            ErrorEvent.component.in_(("inbound_event_worker", "background_worker", "knowledge")),
        )
        .group_by(ErrorEvent.error_code)
        .order_by(func.count(ErrorEvent.id).desc(), ErrorEvent.error_code.asc())
        .limit(10)
        .all()
    )
    webhook_runs = [row for row in recent_runs if row.task_family in {"line_webhook_ingress", "line_webhook_event"}]
    return {
        "top_unknown_labels": [{"label": label or "unknown", "count": int(count or 0)} for label, count in unknown_label_rows],
        "top_feedback_labels": [{"label": label or "unknown", "count": int(count or 0)} for label, count in feedback_label_rows],
        "execution_phase_breakdown": _group_task_runs_by_summary(recent_runs, key="execution_phase"),
        "ingress_mode_breakdown": _group_task_runs_by_summary(recent_runs, key="ingress_mode"),
        "webhook_worker_status_breakdown": _group_task_runs_by_attr(webhook_runs, attr="status"),
        "fallback_reason_breakdown": _group_task_runs_by_attr([row for row in recent_runs if row.fallback_reason], attr="fallback_reason"),
        "deterministic_integration_error_codes": [{"label": code or "unknown", "count": int(count or 0)} for code, count in error_code_rows],
        "packet_coverage_summary": {
            "memory_packet_present_runs": _count_task_runs_with_summary_value(recent_runs, key="memory_packet_present", expected="True"),
            "communication_profile_present_runs": _count_task_runs_with_summary_value(recent_runs, key="communication_profile_present", expected="True"),
            "planning_copy_attempted_runs": _count_task_runs_with_summary_value(recent_runs, key="planning_copy_attempted", expected="True"),
            "knowledge_packet_version_runs": sum(1 for row in recent_runs if bool(row.knowledge_packet_version)),
        },
    }


def _build_attention_panels(db: Session) -> dict[str, Any]:
    open_alerts = [
        {
            "id": alert.id,
            "severity": alert.severity,
            "title": alert.title,
            "summary": alert.summary,
            "last_seen_at": alert.last_seen_at,
        }
        for alert in db.query(AlertEvent).filter(AlertEvent.status == "open").order_by(AlertEvent.severity.desc(), AlertEvent.last_seen_at.desc()).limit(8).all()
    ]
    review_queue = [
        {
            "id": item.id,
            "queue_type": item.queue_type,
            "priority": item.priority,
            "title": item.title,
            "summary": item.summary,
            "status": item.status,
            "created_at": item.created_at,
        }
        for item in db.query(ReviewQueueItem).filter(ReviewQueueItem.status.in_(("new", "triaged", "in_progress"))).order_by(ReviewQueueItem.priority.asc(), ReviewQueueItem.created_at.desc()).limit(10).all()
    ]
    critical_errors = [
        {
            "id": row.id,
            "component": row.component,
            "operation": row.operation,
            "error_code": row.error_code,
            "message": row.message,
            "created_at": row.created_at,
        }
        for row in db.query(ErrorEvent).filter(ErrorEvent.severity == "critical").order_by(ErrorEvent.created_at.desc()).limit(8).all()
    ]
    return {
        "open_alerts": open_alerts,
        "review_queue": review_queue,
        "critical_errors": critical_errors,
    }


def _daily_count_series(db: Session, created_at_column: Any, model: Any, *, trend_days: int) -> list[dict[str, Any]]:
    return _daily_filtered_count_series(db, created_at_column, model, trend_days=trend_days, filters=())


def _daily_filtered_count_series(
    db: Session,
    created_at_column: Any,
    model: Any,
    *,
    trend_days: int,
    filters: tuple[Any, ...],
) -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(days=trend_days - 1)
    query = db.query(func.date(created_at_column), func.count("*")).filter(created_at_column >= since)
    for condition in filters:
        query = query.filter(condition)
    rows = query.group_by(func.date(created_at_column)).all()
    lookup = {str(day): int(count or 0) for day, count in rows}
    series: list[dict[str, Any]] = []
    for offset in range(trend_days):
        current_day = (since + timedelta(days=offset)).date().isoformat()
        series.append({"date": current_day, "value": float(lookup.get(current_day, 0))})
    return series


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def _trace_row(row: ConversationTrace) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "line_user_id": row.line_user_id,
        "surface": row.surface,
        "thread_id": row.thread_id,
        "message_id": row.message_id,
        "reply_to_trace_id": row.reply_to_trace_id,
        "is_system_initiated": row.is_system_initiated,
        "is_canary": row.is_canary,
        "traffic_class": row.traffic_class,
        "task_family": row.task_family,
        "task_confidence": row.task_confidence,
        "source_mode": row.source_mode,
        "input_text": row.input_text,
        "input_metadata": row.input_metadata,
        "created_at": row.created_at,
    }


def _task_run_row(row: TaskRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "trace_id": row.trace_id,
        "user_id": row.user_id,
        "is_canary": row.is_canary,
        "traffic_class": row.traffic_class,
        "task_family": row.task_family,
        "route_layer_1": row.route_layer_1,
        "route_layer_2": row.route_layer_2,
        "provider_name": row.provider_name,
        "model_name": row.model_name,
        "prompt_version": row.prompt_version,
        "knowledge_packet_version": row.knowledge_packet_version,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "latency_ms": row.latency_ms,
        "status": row.status,
        "error_type": row.error_type,
        "fallback_reason": row.fallback_reason,
        "result_summary": row.result_summary,
        "execution_phase": _task_run_summary_value(row, "execution_phase"),
        "ingress_mode": _task_run_summary_value(row, "ingress_mode"),
        "route_policy": _task_run_summary_value(row, "route_policy"),
        "route_target": _task_run_summary_value(row, "route_target"),
        "route_reason": _task_run_summary_value(row, "route_reason"),
        "llm_cache": _task_run_summary_value(row, "llm_cache"),
        "knowledge_strategy": _task_run_summary_value(row, "knowledge_strategy"),
        "memory_packet_present": _task_run_summary_value(row, "memory_packet_present"),
        "communication_profile_present": _task_run_summary_value(row, "communication_profile_present"),
        "planning_copy_attempted": _task_run_summary_value(row, "planning_copy_attempted"),
        "planning_copy_layer": _task_run_summary_value(row, "planning_copy_layer"),
    }


def _uncertainty_row(row: UncertaintyEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "trace_id": row.trace_id,
        "task_run_id": row.task_run_id,
        "task_family": row.task_family,
        "estimation_confidence": row.estimation_confidence,
        "confirmation_calibration": row.confirmation_calibration,
        "primary_uncertainties": row.primary_uncertainties,
        "missing_slots": row.missing_slots,
        "ambiguity_flags": row.ambiguity_flags,
        "answer_mode": row.answer_mode,
        "clarification_budget": row.clarification_budget,
        "clarification_used": row.clarification_used,
        "stop_reason": row.stop_reason,
        "used_generic_portion_estimate": row.used_generic_portion_estimate,
        "used_comparison_mode": row.used_comparison_mode,
        "created_at": row.created_at,
    }


def _knowledge_row(row: KnowledgeEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "trace_id": row.trace_id,
        "task_run_id": row.task_run_id,
        "question_or_query": row.question_or_query,
        "knowledge_mode": row.knowledge_mode,
        "matched_items": row.matched_items,
        "matched_docs": row.matched_docs,
        "used_search": row.used_search,
        "search_sources": row.search_sources,
        "grounding_type": row.grounding_type,
        "knowledge_gap_type": row.knowledge_gap_type,
        "created_at": row.created_at,
    }


def _error_row(row: ErrorEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "trace_id": row.trace_id,
        "task_run_id": row.task_run_id,
        "component": row.component,
        "operation": row.operation,
        "severity": row.severity,
        "error_code": row.error_code,
        "exception_type": row.exception_type,
        "message": row.message,
        "retry_count": row.retry_count,
        "fallback_used": row.fallback_used,
        "user_visible_impact": row.user_visible_impact,
        "request_metadata": row.request_metadata,
        "created_at": row.created_at,
    }


def _task_run_summary_value(row: TaskRun | None, key: str) -> str | None:
    if row is None or not isinstance(row.result_summary, dict):
        return None
    value = row.result_summary.get(key)
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return None
    text = str(value).strip()
    return text or None


def _feedback_row(row: FeedbackEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "trace_id": row.trace_id,
        "target_trace_id": row.target_trace_id,
        "feedback_type": row.feedback_type,
        "feedback_label": row.feedback_label,
        "free_text": row.free_text,
        "severity": row.severity,
        "created_at": row.created_at,
    }


def _unknown_case_row(row: UnknownCaseEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "trace_id": row.trace_id,
        "task_run_id": row.task_run_id,
        "task_family": row.task_family,
        "unknown_type": row.unknown_type,
        "raw_query": row.raw_query,
        "source_hint": row.source_hint,
        "ocr_hits": row.ocr_hits,
        "transcript": row.transcript,
        "current_answer": row.current_answer,
        "suggested_research_area": row.suggested_research_area,
        "review_status": row.review_status,
        "created_at": row.created_at,
    }


def _outcome_row(row: OutcomeEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "trace_id": row.trace_id,
        "task_family": row.task_family,
        "outcome_type": row.outcome_type,
        "target_id": row.target_id,
        "payload": row.payload,
        "created_at": row.created_at,
    }
