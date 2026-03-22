from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..schemas import (
    AdminLoginRequest,
    AdminMeResponse,
    AdminSessionResponse,
    AlertEventResponse,
    AlertRuleRequest,
    AlertRuleResponse,
    AlertStatusUpdateRequest,
    ObservabilityDashboardResponse,
    ObservabilityMetricResponse,
    ReviewQueueItemResponse,
    ReviewQueueUpdateRequest,
    StandardResponse,
    TraceDetailResponse,
    TraceListItemResponse,
)
from ..services.admin_auth import create_admin_session, require_admin_session, revoke_admin_session, validate_admin_passcode
from ..services.knowledge import refresh_knowledge_layer
from ..services.observability_console import (
    build_eval_export,
    build_observability_dashboard,
    collect_default_metrics,
    ensure_default_alert_rules,
    evaluate_alert_rules,
    get_trace_detail,
    list_alert_events,
    list_alert_rules,
    list_review_queue,
    list_trace_summaries,
    update_alert_event_status,
    update_review_queue_item,
    upsert_alert_rule,
)


router = APIRouter()


@router.post(f"{settings.api_prefix}/admin/login", response_model=StandardResponse)
def admin_login(request: AdminLoginRequest, db: Session = Depends(get_db)) -> StandardResponse:
    if not validate_admin_passcode(request.passcode):
        raise HTTPException(status_code=401, detail="Invalid admin passcode")
    token, session = create_admin_session(db, label=request.label or "observability-admin")
    return StandardResponse(
        coach_message="Admin session created.",
        payload={"session": AdminSessionResponse(token=token, label=session.label, status=session.status, expires_at=session.expires_at).model_dump()},
    )


@router.get(f"{settings.api_prefix}/admin/me", response_model=StandardResponse)
def admin_me(session=Depends(require_admin_session)) -> StandardResponse:
    me = AdminMeResponse(
        label=session.label,
        status=session.status,
        expires_at=session.expires_at,
        last_seen_at=session.last_seen_at,
    )
    return StandardResponse(coach_message="Admin session is valid.", payload={"session": me.model_dump()})


@router.post(f"{settings.api_prefix}/admin/logout", response_model=StandardResponse)
def admin_logout(
    x_admin_session: str | None = Header(default=None, alias="X-Admin-Session"),
    session=Depends(require_admin_session),
    db: Session = Depends(get_db),
) -> StandardResponse:
    token = x_admin_session
    if token is None:
        raise HTTPException(status_code=400, detail="Missing admin session token for logout")
    revoked = revoke_admin_session(db, token)
    if revoked is None:
        raise HTTPException(status_code=404, detail="Admin session not found")
    return StandardResponse(coach_message="Admin session closed.", payload={"status": revoked.status})


@router.get(f"{settings.api_prefix}/observability/dashboard", response_model=StandardResponse)
def observability_dashboard(
    window_hours: int = Query(default=168, ge=1, le=24 * 30),
    trend_days: int = Query(default=7, ge=3, le=30),
    db: Session = Depends(get_db),
    _admin_session=Depends(require_admin_session),
) -> StandardResponse:
    dashboard = ObservabilityDashboardResponse(
        **build_observability_dashboard(db, window_hours=window_hours, trend_days=trend_days, user_id=None)
    ).model_dump()
    return StandardResponse(
        coach_message="Observability dashboard loaded.",
        payload={"dashboard": dashboard},
    )


@router.get(f"{settings.api_prefix}/observability/metrics", response_model=StandardResponse)
def observability_metrics(
    window_hours: int = Query(default=168, ge=1, le=24 * 30),
    db: Session = Depends(get_db),
    _admin_session=Depends(require_admin_session),
) -> StandardResponse:
    metrics = [ObservabilityMetricResponse(**row).model_dump() for row in collect_default_metrics(db, window_hours=window_hours)]
    return StandardResponse(
        coach_message="Observability metrics loaded.",
        payload={"metrics": metrics, "window_hours": window_hours},
    )


@router.get(f"{settings.api_prefix}/observability/eval-export", response_model=StandardResponse)
def observability_eval_export(
    window_hours: int = Query(default=168, ge=1, le=24 * 30),
    limit: int = Query(default=200, ge=10, le=1000),
    db: Session = Depends(get_db),
    _admin_session=Depends(require_admin_session),
) -> StandardResponse:
    export = build_eval_export(db, window_hours=window_hours, limit=limit)
    return StandardResponse(
        coach_message="Eval export loaded.",
        payload={"eval_export": export},
    )


@router.post(f"{settings.api_prefix}/observability/knowledge/refresh", response_model=StandardResponse)
def observability_knowledge_refresh(db: Session = Depends(get_db), _admin_session=Depends(require_admin_session)) -> StandardResponse:
    status = refresh_knowledge_layer()
    return StandardResponse(
        coach_message="Knowledge layer refreshed.",
        payload={"knowledge": status},
    )


@router.get(f"{settings.api_prefix}/observability/alert-rules", response_model=StandardResponse)
def observability_alert_rules(db: Session = Depends(get_db), _admin_session=Depends(require_admin_session)) -> StandardResponse:
    rules = [AlertRuleResponse.model_validate(rule, from_attributes=True).model_dump() for rule in ensure_default_alert_rules(db)]
    return StandardResponse(coach_message="Alert rules loaded.", payload={"alert_rules": rules})


@router.post(f"{settings.api_prefix}/observability/alert-rules", response_model=StandardResponse)
def observability_alert_rules_upsert(
    request: AlertRuleRequest,
    db: Session = Depends(get_db),
    _admin_session=Depends(require_admin_session),
) -> StandardResponse:
    rule = upsert_alert_rule(
        db,
        name=request.name,
        metric_key=request.metric_key,
        comparator=request.comparator,
        threshold=request.threshold,
        window_hours=request.window_hours,
        task_family=request.task_family,
        severity=request.severity,
        min_sample_size=request.min_sample_size,
        cooldown_minutes=request.cooldown_minutes,
        status=request.status,
        dimensions=request.dimensions,
        notes=request.notes,
    )
    return StandardResponse(
        coach_message="Alert rule saved.",
        payload={"alert_rule": AlertRuleResponse.model_validate(rule, from_attributes=True).model_dump()},
    )


@router.post(f"{settings.api_prefix}/observability/alerts/evaluate", response_model=StandardResponse)
def observability_alerts_evaluate(db: Session = Depends(get_db), _admin_session=Depends(require_admin_session)) -> StandardResponse:
    alerts = [AlertEventResponse.model_validate(item, from_attributes=True).model_dump() for item in evaluate_alert_rules(db)]
    return StandardResponse(
        coach_message="Alert evaluation complete.",
        payload={"alerts": alerts, "triggered_count": len(alerts)},
    )


@router.get(f"{settings.api_prefix}/observability/alerts", response_model=StandardResponse)
def observability_alerts(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin_session=Depends(require_admin_session),
) -> StandardResponse:
    alerts = [AlertEventResponse.model_validate(item, from_attributes=True).model_dump() for item in list_alert_events(db, status=status, limit=limit)]
    return StandardResponse(coach_message="Alert events loaded.", payload={"alerts": alerts})


@router.post(f"{settings.api_prefix}/observability/alerts/{{alert_id}}/status", response_model=StandardResponse)
def observability_alert_update_status(
    alert_id: str,
    request: AlertStatusUpdateRequest,
    db: Session = Depends(get_db),
    _admin_session=Depends(require_admin_session),
) -> StandardResponse:
    alert = update_alert_event_status(db, alert_id, status=request.status)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return StandardResponse(
        coach_message="Alert status updated.",
        payload={"alert": AlertEventResponse.model_validate(alert, from_attributes=True).model_dump()},
    )


@router.get(f"{settings.api_prefix}/observability/review-queue", response_model=StandardResponse)
def observability_review_queue(
    status: str | None = Query(default=None),
    queue_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin_session=Depends(require_admin_session),
) -> StandardResponse:
    items = [
        ReviewQueueItemResponse.model_validate(item, from_attributes=True).model_dump()
        for item in list_review_queue(db, status=status, queue_type=queue_type, limit=limit)
    ]
    return StandardResponse(coach_message="Review queue loaded.", payload={"review_queue": items})


@router.post(f"{settings.api_prefix}/observability/review-queue/{{item_id}}/status", response_model=StandardResponse)
def observability_review_queue_update(
    item_id: int,
    request: ReviewQueueUpdateRequest,
    db: Session = Depends(get_db),
    _admin_session=Depends(require_admin_session),
) -> StandardResponse:
    item = update_review_queue_item(db, item_id, status=request.status, notes=request.notes, assigned_to=request.assigned_to)
    if item is None:
        raise HTTPException(status_code=404, detail="Review queue item not found")
    return StandardResponse(
        coach_message="Review queue item updated.",
        payload={"review_item": ReviewQueueItemResponse.model_validate(item, from_attributes=True).model_dump()},
    )


@router.get(f"{settings.api_prefix}/observability/traces", response_model=StandardResponse)
def observability_traces(
    task_family: str | None = Query(default=None),
    surface: str | None = Query(default=None),
    source_mode: str | None = Query(default=None),
    status: str | None = Query(default=None),
    provider_name: str | None = Query(default=None),
    model_name: str | None = Query(default=None),
    execution_phase: str | None = Query(default=None),
    ingress_mode: str | None = Query(default=None),
    route_policy: str | None = Query(default=None),
    llm_cache: str | None = Query(default=None),
    is_canary: bool | None = Query(default=None),
    traffic_class: str | None = Query(default=None),
    has_error: bool | None = Query(default=None),
    has_feedback: bool | None = Query(default=None),
    has_unknown_case: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin_session=Depends(require_admin_session),
) -> StandardResponse:
    results = list_trace_summaries(
        db,
        task_family=task_family,
        surface=surface,
        source_mode=source_mode,
        status=status,
        provider_name=provider_name,
        model_name=model_name,
        execution_phase=execution_phase,
        ingress_mode=ingress_mode,
        route_policy=route_policy,
        llm_cache=llm_cache,
        is_canary=is_canary,
        traffic_class=traffic_class,
        has_error=has_error,
        has_feedback=has_feedback,
        has_unknown_case=has_unknown_case,
        limit=limit,
        offset=offset,
    )
    items = [TraceListItemResponse(**row).model_dump() for row in results["items"]]
    return StandardResponse(
        coach_message="Trace list loaded.",
        payload={
            "items": items,
            "total": results["total"],
            "limit": results["limit"],
            "offset": results["offset"],
        },
    )


@router.get(f"{settings.api_prefix}/observability/traces/{{trace_id}}", response_model=StandardResponse)
def observability_trace_detail(
    trace_id: str,
    db: Session = Depends(get_db),
    _admin_session=Depends(require_admin_session),
) -> StandardResponse:
    detail = get_trace_detail(db, trace_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    payload = TraceDetailResponse(
        trace=detail["trace"],
        task_runs=detail["task_runs"],
        uncertainty_events=detail["uncertainty_events"],
        knowledge_events=detail["knowledge_events"],
        error_events=detail["error_events"],
        feedback_events=detail["feedback_events"],
        unknown_case_events=detail["unknown_case_events"],
        outcome_events=detail["outcome_events"],
        related_review_items=[ReviewQueueItemResponse.model_validate(item, from_attributes=True) for item in detail["related_review_items"]],
        related_alerts=[AlertEventResponse.model_validate(item, from_attributes=True) for item in detail["related_alerts"]],
    ).model_dump()
    return StandardResponse(coach_message="Trace detail loaded.", payload={"trace_detail": payload})
