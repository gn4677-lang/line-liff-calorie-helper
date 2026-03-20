from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import re

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import ActivityAdjustment, Food, MealDraft, MealEvent, MealLog, PlanEvent, SearchJob, WeightLog, utcnow
from ..providers.factory import get_ai_provider
from ..schemas import (
    ActivityAdjustmentRequest,
    ActivityAdjustmentUpdateRequest,
    BodyGoalUpdateRequest,
    ClarifyRequest,
    ClientConfigResponse,
    ConfirmRequest,
    EatFeedRequest,
    FavoriteStoreRequest,
    IntakeRequest,
    LocationResolveRequest,
    MealEventRequest,
    ManualMealLogRequest,
    MeResponse,
    MealEditRequest,
    MemoryProfileResponse,
    NearbyRecommendationRequest,
    NutritionQARequest,
    OnboardingPreferencesRequest,
    OnboardingStateResponse,
    PlanEventResponse,
    PlanRequest,
    PreferenceCorrectionRequest,
    PreferenceResponse,
    PreferencesUpdateRequest,
    SavedPlaceRequest,
    StandardResponse,
    VideoIntakeRequest,
    WeightLogRequest,
)
from ..services.auth import get_or_create_user, verify_liff_id_token
from ..services.liff_session import create_liff_session, verify_liff_session
from ..services.body_metrics import (
    activity_to_response,
    body_goal_to_response,
    build_progress_series,
    create_activity_adjustment,
    delete_activity_adjustment,
    get_or_create_body_goal,
    list_activity_adjustments,
    refresh_body_goal_calibration,
    update_activity_adjustment,
    update_body_goal,
)
from ..services.energy_qa import (
    answer_calorie_question,
    build_energy_context,
    looks_like_energy_question,
    looks_like_remaining_calorie_question,
)
from ..services.eat_feed import (
    attribute_recommendation_outcome,
    build_eat_feed,
    mark_recommendation_manual_correction,
)
from ..services.intake import (
    confirm_draft,
    create_manual_log,
    create_correction_preview,
    create_or_update_draft,
    delete_log,
    draft_to_response,
    edit_log_manual,
    edit_log,
    infer_meal_type,
    log_to_response,
    update_draft_with_clarification,
)
from ..services.knowledge import KNOWLEDGE_PACKET_VERSION, build_estimation_knowledge_packet
from ..services.line import build_draft_flex_message, fetch_line_content, reply_line_message, verify_line_signature
from ..services.meal_events import create_meal_event, list_meal_events, meal_event_to_response, parse_future_meal_event_text
from ..services.memory import (
    apply_onboarding_preferences,
    apply_preference_correction,
    build_memory_profile,
    build_onboarding_state,
    detect_chat_correction,
    get_or_create_preferences,
    mark_onboarding_skipped,
    preference_to_response,
    synthesize_hypotheses,
)
from ..services.observability import (
    create_conversation_trace,
    detect_explicit_feedback,
    finish_task_run,
    get_request_trace_id,
    provider_descriptor,
    record_error_event,
    record_feedback_event,
    record_knowledge_event,
    record_outcome_event,
    record_uncertainty_event,
    record_unknown_case_event,
    route_layers_for_task,
    start_task_run,
)
from ..services.planning import build_compensation_plan, build_day_plan
from ..services.proactive import (
    apply_search_job,
    build_nearby_heuristics,
    create_search_job,
    dismiss_search_job,
    list_favorite_stores,
    list_golden_orders,
    list_notifications,
    list_saved_places,
    mark_notification_read,
    maybe_queue_menu_precision_job,
    resolve_location_context,
    save_place,
    search_job_to_response,
    upsert_favorite_store,
)
from ..services.recommendations import get_recommendations
from ..services.storage import attachment_for_persistence, store_attachment_bytes
from ..services.storage import infer_source_type_from_mime
from ..services.summary import build_day_summary
from ..services.summary import build_logbook_range
from ..services.video_intake import (
    enrich_attachment_with_video_probe,
    enrich_video_intake_request,
    first_video_attachment,
    maybe_queue_video_refinement_job,
)
from ..providers.base import EstimateResult


router = APIRouter()


def _is_auto_recordable(draft: MealDraft) -> bool:
    return (draft.draft_context or {}).get("confirmation_mode") == "auto_recordable"


def _build_draft_message(draft: MealDraft) -> tuple[str, list[object] | None]:
    metadata = draft.draft_context or {}
    kcal_range = f"{draft.kcal_low}-{draft.kcal_high} kcal"
    uncertainties = metadata.get("primary_uncertainties", [])
    uncertainty_text = f" 目前最不確定的是：{', '.join(uncertainties)}。" if uncertainties else ""
    mode = metadata.get("confirmation_mode")

    if mode == "needs_clarification":
        return draft.followup_question or "我還差一個關鍵細節，補一下我就能幫你記錄。", metadata.get("answer_options") or None
    if mode == "correction_preview":
        original = metadata.get("original_kcal")
        diff = metadata.get("difference_kcal")
        diff_text = ""
        if original is not None and diff is not None:
            direction = "+" if diff >= 0 else "-"
            diff_text = f" 變化：{original} kcal {direction} {abs(diff)} kcal。"
        return f"我重新估了一下上一筆，現在約 {draft.estimate_kcal} kcal。{diff_text}要直接套用嗎？", None
    if mode == "auto_recordable":
        return (
            f"這餐我先幫你記成約 {draft.estimate_kcal} kcal，範圍 {kcal_range}。{uncertainty_text}如果想改，直接回我一句就好。",
            None,
        )
    if metadata.get("stop_reason") == "budget_exhausted":
        return (
            f"我先停在這裡，用一般份量幫你估成 {draft.estimate_kcal} kcal，範圍 {kcal_range}。{uncertainty_text}",
            None,
        )
    return f"我目前先抓這餐約 {draft.estimate_kcal} kcal，範圍 {kcal_range}。{uncertainty_text}", None


def _latest_open_draft(db: Session, user) -> MealDraft | None:
    return db.scalar(
        select(MealDraft)
        .where(
            MealDraft.user_id == user.id,
            MealDraft.status.in_(("awaiting_clarification", "ready_to_confirm")),
        )
        .order_by(MealDraft.updated_at.desc(), MealDraft.created_at.desc())
    )


def _is_confirm_text(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {"確認", "確認這餐", "確認記錄", "記錄這餐", "套用更新", "好", "ok", "yes"}


def _is_defer_text(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {"稍後", "晚點", "先不要", "skip", "later"}


def _draft_liff_url(tab: str = "today") -> str | None:
    if not settings.liff_channel_id:
        return None
    return f"https://liff.line.me/{settings.liff_channel_id}?tab={tab}"


def _build_draft_flex_payload(draft: MealDraft) -> dict[str, object] | None:
    metadata = draft.draft_context or {}
    mode = metadata.get("confirmation_mode")
    liff_url = _draft_liff_url("today")
    if mode == "needs_clarification":
        return None

    parsed_items = [item.get("name", "") for item in (draft.parsed_items or []) if isinstance(item, dict)]
    kcal_text = f"約 {draft.estimate_kcal} kcal ({draft.kcal_low}-{draft.kcal_high})"
    lines = [line for line in [parsed_items[0] if parsed_items else draft.raw_input_text.strip(), draft.uncertainty_note or "", *metadata.get("primary_uncertainties", [])[:2]] if line]

    if mode == "correction_preview":
        return build_draft_flex_message(
            title="更新前一餐",
            subtitle=kcal_text,
            lines=lines[:3] or ["我重新算過上一筆紀錄。"],
            primary_label="套用更新",
            primary_text="套用更新",
            secondary_uri=liff_url,
        )
    if mode == "auto_recordable":
        return None
    return build_draft_flex_message(
        title="確認這餐",
        subtitle=kcal_text,
        lines=lines[:3] or ["我先幫你整理好了，確認後就會入帳。"],
        primary_label="確認記錄",
        primary_text="確認這餐",
        secondary_uri=liff_url,
    )


def _route_text_task(text: str) -> tuple[str, float]:
    normalized = text.strip().lower()
    if looks_like_remaining_calorie_question(normalized):
        return "remaining_or_recommendation", 0.88
    if looks_like_energy_question(normalized):
        return "nutrition_or_food_qa", 0.82
    if re.search(r"(breakfast|lunch|dinner|snack|早餐|午餐|晚餐|點心|便當|雞胸|吃了|剛吃)", normalized):
        return "meal_log_now", 0.86
    if re.search(r"(改一下|修正|上一筆|其實|飯只|沒喝|沒吃|更正)", normalized):
        return "meal_log_correction", 0.79
    if re.search(r"(明天|後天|週末|周末|聚餐|大餐|吃到飽|燒肉|火鍋|晚點要吃)", normalized):
        return "future_event_probe", 0.83
    if re.search(r"(這週|這周|前幾天|吃爆|超標|拉回來|weekly)", normalized):
        return "weekly_drift_probe", 0.74
    if re.search(r"(剩多少|還能吃|推薦|吃什麼|附近|哪裡吃|recommend)", normalized):
        return "remaining_or_recommendation", 0.84
    if re.search(r"(weight|體重|kg)", normalized):
        return "weight_log", 0.84
    if re.search(r"(熱量|營養|蛋白質|脂肪|碳水|ig|instagram|品牌|菜單|店家|新品)", normalized):
        return "nutrition_or_food_qa", 0.72
    if re.search(r"(不喜歡|不要再推|我不吃|我最近開始|偏好|記得我)", normalized):
        return "preference_or_memory_correction", 0.76
    if re.search(r"(help|幫助|怎麼用|功能)", normalized):
        return "meta_help", 0.70
    return "fallback_ambiguous", 0.35


def _disambiguation_options() -> list[object]:
    return ["記這餐", "改上一筆", "看推薦", "問營養", "看今天剩多少"]


def _location_route_options() -> list[object]:
    return [
        "現在附近",
        "等下要去的地方",
        "家附近",
        "公司附近",
        "我自己輸入",
        {"type": "action", "action": {"type": "location", "label": "分享位置"}},
    ]


def _maybe_queue_post_intake_job(
    db: Session,
    user,
    *,
    trace_id: str | None = None,
    source_mode: str,
    text: str,
    meal_type: str | None,
    attachments: list[dict],
    metadata: dict[str, object],
    draft: MealDraft | None = None,
    log: MealLog | None = None,
    notify_on_complete: bool = True,
):
    if source_mode == "video" or first_video_attachment(attachments) is not None:
        return maybe_queue_video_refinement_job(
            db,
            user,
            trace_id=trace_id,
            text=text,
            meal_type=meal_type,
            attachments=attachments,
            metadata=metadata,
            draft=draft,
            log=log,
            notify_on_complete=notify_on_complete,
        )
    if log is not None:
        return maybe_queue_menu_precision_job(db, user, trace_id=trace_id, text=text, log=log, notify_on_complete=notify_on_complete)
    return None


def _start_observed_task(
    db: Session,
    request: Request | None,
    *,
    user,
    surface: str,
    task_family: str,
    input_text: str = "",
    input_metadata: dict[str, object] | None = None,
    source_mode: str | None = None,
    task_confidence: float | None = None,
    provider=None,
) -> tuple[str, str]:
    trace_id = get_request_trace_id(request)
    create_conversation_trace(
        db,
        trace_id=trace_id,
        user_id=user.id,
        line_user_id=user.line_user_id,
        surface=surface,
        task_family=task_family,
        task_confidence=task_confidence,
        source_mode=source_mode,
        input_text=input_text,
        input_metadata=input_metadata or {},
    )
    route_layer_1, route_layer_2 = route_layers_for_task(task_family)
    provider_name, model_name = provider_descriptor(provider, task_family=task_family, source_mode=source_mode)
    task_run_id = start_task_run(
        db,
        trace_id=trace_id,
        user_id=user.id,
        task_family=task_family,
        route_layer_1=route_layer_1,
        route_layer_2=route_layer_2,
        provider_name=provider_name,
        model_name=model_name,
        prompt_version=getattr(provider, "prompt_version", None),
        knowledge_packet_version=KNOWLEDGE_PACKET_VERSION if task_family in {"meal_log_now", "meal_log_correction"} else None,
    )
    return trace_id, task_run_id


def _source_hint_from_metadata(metadata: dict[str, object] | None) -> str | None:
    if not metadata:
        return None
    parts: list[str] = []
    transcript = metadata.get("transcript")
    if isinstance(transcript, str) and transcript.strip():
        parts.append(transcript.strip())
    ocr_hits = metadata.get("ocr_hits")
    if isinstance(ocr_hits, list):
        parts.extend(str(item.get("text", "")).strip() for item in ocr_hits if isinstance(item, dict) and item.get("text"))
    brand_hints = metadata.get("brand_hints")
    if isinstance(brand_hints, list):
        parts.extend(str(item).strip() for item in brand_hints if str(item).strip())
    combined = "\n".join(part for part in parts if part)
    return combined or None


def _store_context_hint(db: Session | None, user, text: str) -> str | None:
    if db is None or user is None or not text.strip():
        return None
    normalized = "".join(text.strip().lower().split())
    foods = list(
        db.scalars(
            select(Food)
            .where(Food.user_id == user.id, Food.store_context.is_not(None))
            .order_by(Food.usage_count.desc(), Food.last_used_at.desc())
            .limit(24)
        )
    )
    for food in foods:
        food_name = "".join((food.name or "").lower().split())
        if not food_name or (food_name not in normalized and normalized not in food_name):
            continue
        store_context = food.store_context or {}
        top_store_name = str(store_context.get("top_store_name") or "").strip()
        if not top_store_name:
            continue
        hint_parts = [f"這個品項你最常在 {top_store_name} 記錄"]
        if store_context.get("top_avg_kcal"):
            hint_parts.append(f"那家店通常約 {store_context['top_avg_kcal']} kcal")
        if store_context.get("top_location_context"):
            hint_parts.append(f"位置情境：{store_context['top_location_context']}")
        return "；".join(hint_parts)
    return None


async def _estimate_with_knowledge(
    provider,
    *,
    db: Session | None = None,
    user=None,
    text: str,
    meal_type: str | None,
    mode: str,
    source_mode: str,
    clarification_count: int,
    attachments: list[dict],
    metadata: dict[str, object] | None = None,
):
    metadata = metadata or {}
    source_hint_parts = [_source_hint_from_metadata(metadata), _store_context_hint(db, user, text)]
    knowledge_packet = build_estimation_knowledge_packet(
        text,
        source_hint="\n".join(part for part in source_hint_parts if part) or None,
        ocr_hits=metadata.get("ocr_hits") if isinstance(metadata.get("ocr_hits"), list) else None,
        meal_type=meal_type,
        source_mode=source_mode,
    )
    estimate = await provider.estimate_meal(
        text=text,
        meal_type=meal_type,
        mode=mode,
        source_mode=source_mode,
        clarification_count=clarification_count,
        attachments=attachments,
        knowledge_packet=knowledge_packet,
    )
    estimate.knowledge_packet_version = knowledge_packet.get("version")
    estimate.matched_knowledge_packs = knowledge_packet.get("matched_packs", [])
    estimate.evidence_slots = {
        **estimate.evidence_slots,
        "knowledge_packet_version": knowledge_packet.get("version"),
        "matched_knowledge_packs": knowledge_packet.get("matched_packs", []),
        "knowledge_strategy": knowledge_packet.get("primary_strategy"),
    }
    return estimate


def _task_result_summary_from_estimate(
    estimate: EstimateResult | None,
    *,
    source_mode: str | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    summary: dict[str, object] = dict(extra or {})
    if source_mode:
        summary["source_mode"] = source_mode
    if estimate is None:
        return summary
    slots = estimate.evidence_slots or {}
    route_policy = slots.get("route_policy")
    route_target = slots.get("route_target")
    route_reason = slots.get("route_reason")
    llm_cache = slots.get("llm_cache")
    knowledge_strategy = slots.get("knowledge_strategy")
    matched_packs = estimate.matched_knowledge_packs or []
    if route_policy:
        summary["route_policy"] = route_policy
    if route_target:
        summary["route_target"] = route_target
    if route_reason:
        summary["route_reason"] = route_reason
    if llm_cache:
        summary["llm_cache"] = llm_cache
    if knowledge_strategy:
        summary["knowledge_strategy"] = knowledge_strategy
    if estimate.knowledge_packet_version:
        summary["knowledge_packet_version"] = estimate.knowledge_packet_version
    if matched_packs:
        summary["matched_knowledge_packs"] = matched_packs
    return summary


def _task_result_summary_from_draft(
    draft: MealDraft,
    *,
    source_mode: str | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    context = draft.draft_context or {}
    summary = _task_result_summary_from_estimate(
        EstimateResult(
            parsed_items=draft.parsed_items or [],
            estimate_kcal=draft.estimate_kcal,
            kcal_low=draft.kcal_low,
            kcal_high=draft.kcal_high,
            confidence=draft.confidence,
            missing_slots=draft.missing_slots or [],
            followup_question=draft.followup_question,
            uncertainty_note=draft.uncertainty_note or "",
            status=draft.status,
            evidence_slots=context.get("evidence_slots", {}) or {},
            comparison_candidates=context.get("comparison_candidates", []) or [],
            ambiguity_flags=context.get("ambiguity_flags", []) or [],
            knowledge_packet_version=context.get("knowledge_packet_version"),
            matched_knowledge_packs=context.get("matched_knowledge_packs", []) or [],
        ),
        source_mode=source_mode or draft.source_mode,
        extra=extra,
    )
    return summary


def _record_draft_uncertainty(db: Session, *, trace_id: str, task_run_id: str, user, task_family: str, draft: MealDraft) -> None:
    metadata = draft.draft_context or {}
    record_uncertainty_event(
        db,
        trace_id=trace_id,
        task_run_id=task_run_id,
        user_id=user.id,
        task_family=task_family,
        estimation_confidence=metadata.get("estimation_confidence", draft.confidence),
        confirmation_calibration=metadata.get("confirmation_calibration", 1.0),
        primary_uncertainties=metadata.get("primary_uncertainties", []),
        missing_slots=draft.missing_slots,
        ambiguity_flags=metadata.get("ambiguity_flags", []),
        answer_mode=metadata.get("answer_mode"),
        clarification_budget=metadata.get("clarification_budget"),
        clarification_used=metadata.get("clarification_used"),
        stop_reason=metadata.get("stop_reason"),
        used_generic_portion_estimate=metadata.get("stop_reason") == "budget_exhausted",
        used_comparison_mode=bool(metadata.get("comparison_mode_used")),
    )


async def current_user(
    request: Request,
    db: Session = Depends(get_db),
    x_line_user_id: str | None = Header(default=None),
    x_display_name: str | None = Header(default=None),
    x_line_id_token: str | None = Header(default=None),
    x_app_session: str | None = Header(default=None),
):
    cookie_session = request.cookies.get("app_session")
    identity = None

    if cookie_session:
        try:
            identity = verify_liff_session(cookie_session)
            request.state.auth_mode = "app_session"
            request.state.verified_identity = identity
        except HTTPException:
            identity = None

    if identity is not None:
        line_user_id = identity.line_user_id
        display_name = identity.display_name
    elif x_app_session:
        identity = verify_liff_session(x_app_session)
        line_user_id = identity.line_user_id
        display_name = identity.display_name
        request.state.auth_mode = "app_session"
        request.state.verified_identity = identity
    elif x_line_id_token:
        identity = await verify_liff_id_token(x_line_id_token)
        line_user_id = identity.line_user_id
        display_name = identity.display_name
        request.state.auth_mode = "liff_id_token"
        request.state.verified_identity = identity
    elif x_line_user_id:
        line_user_id = x_line_user_id
        display_name = x_display_name or "Demo User"
        request.state.auth_mode = "header_demo"
    elif settings.environment != "production":
        line_user_id = settings.default_user_id
        display_name = x_display_name or "Demo User"
        request.state.auth_mode = "dev_default"
    else:
        raise HTTPException(status_code=401, detail="LINE authentication is required")

    if settings.allowlist_line_user_id and line_user_id != settings.allowlist_line_user_id:
        raise HTTPException(status_code=403, detail="User is not allowlisted")

    return get_or_create_user(db, line_user_id=line_user_id, display_name=display_name)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(f"{settings.api_prefix}/client-config", response_model=ClientConfigResponse)
def client_config() -> ClientConfigResponse:
    return ClientConfigResponse(
        liff_id=settings.liff_channel_id,
        auth_required=settings.environment == "production" and bool(settings.liff_channel_id),
    )


@router.get(f"{settings.api_prefix}/me", response_model=MeResponse)
def me(request: Request, response: Response, user=Depends(current_user)) -> MeResponse:
    auth_mode = getattr(request.state, "auth_mode", "unknown")
    app_session_token = None
    app_session_expires_at = None
    if auth_mode == "liff_id_token":
        identity = getattr(request.state, "verified_identity", None)
        if identity is not None:
            app_session_token, app_session_expires_at = create_liff_session(identity)
            response.set_cookie(
                key="app_session",
                value=app_session_token,
                max_age=max(settings.liff_session_ttl_hours, 1) * 3600,
                httponly=True,
                samesite="lax",
                secure=settings.environment == "production",
                path="/",
            )
    return MeResponse(
        line_user_id=user.line_user_id,
        display_name=user.display_name,
        daily_calorie_target=user.daily_calorie_target,
        provider=settings.ai_provider,
        now=datetime.now(timezone.utc),
        app_session_token=app_session_token,
        app_session_expires_at=app_session_expires_at,
        auth_mode=auth_mode,
    )


@router.get(f"{settings.api_prefix}/onboarding-state", response_model=OnboardingStateResponse)
def onboarding_state(db: Session = Depends(get_db), user=Depends(current_user)) -> OnboardingStateResponse:
    return build_onboarding_state(user, get_or_create_preferences(db, user))


@router.post(f"{settings.api_prefix}/onboarding/skip", response_model=OnboardingStateResponse)
def onboarding_skip(db: Session = Depends(get_db), user=Depends(current_user)) -> OnboardingStateResponse:
    mark_onboarding_skipped(db, user)
    return build_onboarding_state(user, get_or_create_preferences(db, user))


@router.post(f"{settings.api_prefix}/preferences/onboarding", response_model=StandardResponse)
def onboarding_preferences(
    request: OnboardingPreferencesRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    preference = apply_onboarding_preferences(db, user, request)
    return StandardResponse(
        coach_message="Onboarding preferences saved.",
        payload={
            "preferences": preference_to_response(preference).model_dump(),
            "onboarding_state": build_onboarding_state(user, preference).model_dump(),
        },
    )


@router.get(f"{settings.api_prefix}/preferences", response_model=PreferenceResponse)
def get_preferences(db: Session = Depends(get_db), user=Depends(current_user)) -> PreferenceResponse:
    return preference_to_response(get_or_create_preferences(db, user))


@router.post(f"{settings.api_prefix}/preferences/correction", response_model=StandardResponse)
def correct_preferences(
    request: PreferenceCorrectionRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    preference = apply_preference_correction(db, user, request)
    return StandardResponse(
        coach_message="Preference correction saved.",
        payload={"preferences": preference_to_response(preference).model_dump()},
    )


@router.post(f"{settings.api_prefix}/preferences", response_model=StandardResponse)
def update_preferences(
    request: PreferencesUpdateRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    preference = get_or_create_preferences(db, user)
    for field, value in request.model_dump(exclude_none=True).items():
        setattr(preference, field, value)
    db.add(preference)
    db.commit()
    db.refresh(preference)
    synthesize_hypotheses(db, user, force_user_stated=True)
    return StandardResponse(
        coach_message="Preferences updated.",
        payload={"preferences": preference_to_response(preference).model_dump()},
    )


@router.get(f"{settings.api_prefix}/memory/profile", response_model=MemoryProfileResponse)
def memory_profile(db: Session = Depends(get_db), user=Depends(current_user)) -> MemoryProfileResponse:
    return build_memory_profile(db, user)


@router.post(f"{settings.api_prefix}/location/resolve", response_model=StandardResponse)
def location_resolve(
    request: LocationResolveRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    location = resolve_location_context(db, user, request.model_dump())
    return StandardResponse(
        coach_message="Location context is ready.",
        payload={"location": location, "saved_places": [item.model_dump() for item in list_saved_places(db, user)]},
    )


@router.get(f"{settings.api_prefix}/saved-places", response_model=StandardResponse)
def get_saved_places(db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    return StandardResponse(
        coach_message="Saved places loaded.",
        payload={"saved_places": [item.model_dump() for item in list_saved_places(db, user)]},
    )


@router.post(f"{settings.api_prefix}/saved-places", response_model=StandardResponse)
def create_saved_place_route(
    request: SavedPlaceRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    save_place(db, user, request)
    return StandardResponse(
        coach_message="Saved place updated.",
        payload={"saved_places": [item.model_dump() for item in list_saved_places(db, user)]},
    )


@router.get(f"{settings.api_prefix}/favorite-stores", response_model=StandardResponse)
def get_favorite_stores(db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    return StandardResponse(
        coach_message="Favorite stores loaded.",
        payload={
            "favorite_stores": [item.model_dump() for item in list_favorite_stores(db, user)],
            "golden_orders": [item.model_dump() for item in list_golden_orders(db, user)],
        },
    )


@router.post(f"{settings.api_prefix}/favorite-stores", response_model=StandardResponse)
def create_favorite_store_route(
    request: FavoriteStoreRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    store, golden = upsert_favorite_store(db, user, request)
    return StandardResponse(
        coach_message="Favorite store updated.",
        payload={
            "favorite_store": {"id": store.id, "name": store.name},
            "golden_order_id": golden.id if golden else None,
        },
    )


@router.post(f"{settings.api_prefix}/recommendations/nearby", response_model=StandardResponse)
def nearby_recommendations(
    http_request: Request,
    request: NearbyRecommendationRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    location_context = resolve_location_context(db, user, request.model_dump())
    summary = build_day_summary(db, user, date.today())
    remaining_kcal = request.remaining_kcal if request.remaining_kcal is not None else summary.remaining_kcal
    nearby = build_nearby_heuristics(
        db,
        user,
        location_context=location_context,
        meal_type=request.meal_type,
        remaining_kcal=remaining_kcal,
    )
    job = create_search_job(
        db,
        user,
        job_type="nearby_places",
        request_payload={
            **location_context,
            "meal_type": request.meal_type,
            "remaining_kcal": remaining_kcal,
            "notify_on_complete": request.notify_on_complete,
            "trace_id": get_request_trace_id(http_request),
        },
    )
    nearby = nearby.model_copy(update={"search_job_id": job.id})
    return StandardResponse(
        coach_message="Here is a fast nearby shortlist while I look for more precise options.",
        payload={"nearby": nearby.model_dump()},
    )


@router.get(f"{settings.api_prefix}/search-jobs/{{job_id}}", response_model=StandardResponse)
def get_search_job(job_id: str, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    job = db.get(SearchJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Search job not found")
    return StandardResponse(coach_message="Search job loaded.", payload={"search_job": search_job_to_response(job).model_dump()})


@router.post(f"{settings.api_prefix}/search-jobs/{{job_id}}/apply", response_model=StandardResponse)
def apply_search_job_route(http_request: Request, job_id: str, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    job = db.get(SearchJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Search job not found")
    trace_id, task_run_id = _start_observed_task(
        db,
        http_request,
        user=user,
        surface="today",
        task_family="suggested_update_review",
        input_text="apply suggested update",
        input_metadata={"job_id": job_id, "job_type": job.job_type},
    )
    updated = apply_search_job(db, user, job)
    record_feedback_event(
        db,
        trace_id=trace_id,
        user_id=user.id,
        feedback_type="apply_suggested_update",
        feedback_label="accepted_async_update",
        severity="low",
    )
    record_outcome_event(
        db,
        trace_id=trace_id,
        user_id=user.id,
        task_family="suggested_update_review",
        outcome_type="suggested_update_applied",
        target_id=job_id,
        payload={"job_type": job.job_type},
    )
    finish_task_run(db, task_run_id, status="success", result_summary={"job_id": job_id, "job_type": job.job_type, "status": updated.status})
    return StandardResponse(coach_message="Suggested update applied.", payload={"search_job": updated.model_dump()})


@router.post(f"{settings.api_prefix}/search-jobs/{{job_id}}/dismiss", response_model=StandardResponse)
def dismiss_search_job_route(http_request: Request, job_id: str, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    job = db.get(SearchJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Search job not found")
    trace_id, task_run_id = _start_observed_task(
        db,
        http_request,
        user=user,
        surface="today",
        task_family="suggested_update_review",
        input_text="dismiss suggested update",
        input_metadata={"job_id": job_id, "job_type": job.job_type},
    )
    updated = dismiss_search_job(db, user, job)
    record_feedback_event(
        db,
        trace_id=trace_id,
        user_id=user.id,
        feedback_type="dismiss_suggested_update",
        feedback_label="dismissed_async_update",
        severity="medium",
    )
    record_outcome_event(
        db,
        trace_id=trace_id,
        user_id=user.id,
        task_family="suggested_update_review",
        outcome_type="suggested_update_dismissed",
        target_id=job_id,
        payload={"job_type": job.job_type},
    )
    finish_task_run(db, task_run_id, status="success", result_summary={"job_id": job_id, "job_type": job.job_type, "status": updated.status})
    return StandardResponse(coach_message="Suggested update dismissed.", payload={"search_job": updated.model_dump()})


@router.get(f"{settings.api_prefix}/notifications", response_model=StandardResponse)
def get_notifications(db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    return StandardResponse(
        coach_message="Notifications loaded.",
        payload={"notifications": [item.model_dump() for item in list_notifications(db, user)]},
    )


@router.post(f"{settings.api_prefix}/notifications/{{notification_id}}/read", response_model=StandardResponse)
def read_notification(notification_id: str, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    try:
        notification = mark_notification_read(db, user, notification_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StandardResponse(coach_message="Notification marked as read.", payload={"notification": notification.model_dump()})


@router.get(f"{settings.api_prefix}/plan-events", response_model=StandardResponse)
def get_plan_events(db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    cutoff = date.today()
    future_limit = cutoff + timedelta(days=14)
    events = (
        db.execute(
            select(PlanEvent)
            .where(PlanEvent.user_id == user.id)
            .where(PlanEvent.date >= cutoff)
            .where(PlanEvent.date <= future_limit)
            .order_by(PlanEvent.date)
        )
        .scalars()
        .all()
    )
    items = [
        PlanEventResponse(
            id=e.id,
            date=e.date,
            event_type=e.event_type,
            title=getattr(e, "title", ""),
            expected_extra_kcal=e.expected_extra_kcal,
            planning_status=getattr(e, "planning_status", "unplanned"),
            notes_summary=e.notes[:100] if e.notes else "",
        )
        for e in events
    ]
    return StandardResponse(
        coach_message="Upcoming events loaded.",
        payload={"plan_events": [item.model_dump() for item in items]},
    )


@router.get(f"{settings.api_prefix}/meal-events", response_model=StandardResponse)
def get_meal_events(db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    items = list_meal_events(db, user)
    return StandardResponse(
        coach_message="未來餐次事件已載入。",
        payload={"meal_events": [item.model_dump() for item in items]},
    )


@router.post(f"{settings.api_prefix}/meal-events", response_model=StandardResponse)
def post_meal_event(
    request: MealEventRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    row = create_meal_event(db, user, request)
    return StandardResponse(
        coach_message="Meal event saved.",
        payload={"meal_event": meal_event_to_response(row).model_dump()},
    )


@router.get(f"{settings.api_prefix}/body-goal", response_model=StandardResponse)
def get_body_goal(db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    goal = refresh_body_goal_calibration(db, user)
    return StandardResponse(
        coach_message="Body goal loaded.",
        payload={"body_goal": body_goal_to_response(db, user, goal, target_date=date.today()).model_dump()},
    )


@router.patch(f"{settings.api_prefix}/body-goal", response_model=StandardResponse)
def patch_body_goal(
    request: BodyGoalUpdateRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    goal = update_body_goal(db, user, request)
    return StandardResponse(
        coach_message="Body goal updated.",
        payload={"body_goal": body_goal_to_response(db, user, goal, target_date=date.today()).model_dump()},
    )


@router.get(f"{settings.api_prefix}/logbook-range", response_model=StandardResponse)
def get_logbook_range(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    if end < start:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")
    items = build_logbook_range(db, user, start_date=start, end_date=end)
    return StandardResponse(
        coach_message="Logbook range loaded.",
        payload={"days": items},
    )


@router.get(f"{settings.api_prefix}/progress-series", response_model=StandardResponse)
def get_progress_series(
    range: str = Query("30d"),
    resolution: str = Query("day"),
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    goal = refresh_body_goal_calibration(db, user)
    _ = goal
    series = build_progress_series(db, user, range_key=range, resolution=resolution)
    return StandardResponse(
        coach_message="Progress series loaded.",
        payload={"series": series.model_dump()},
    )


@router.get(f"{settings.api_prefix}/journal-add-suggestions", response_model=StandardResponse)
def get_journal_add_suggestions(
    meal_type: str = Query(...),
    target_date: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    from ..schemas import JournalAddSuggestionsResponse
    logs = list(
        db.scalars(
            select(MealLog)
            .where(MealLog.user_id == user.id, MealLog.meal_type == meal_type)
            .order_by(MealLog.created_at.desc())
            .limit(20)
        )
    )
    
    recent_items = []
    seen = set()
    for log in logs:
        text = (log.description_raw or "").strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            recent_items.append({
                "description_raw": text,
                "kcal_estimate": log.kcal_estimate,
                "meal_type": log.meal_type,
            })
        if len(recent_items) >= 5:
            break
            
    res = JournalAddSuggestionsResponse(recent_items=recent_items)
    return StandardResponse(coach_message="Suggestions loaded.", payload=res.model_dump())


@router.get(f"{settings.api_prefix}/activity-adjustments", response_model=StandardResponse)
def get_activity_adjustments(
    target_date: date | None = Query(default=None, alias="date"),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    items = list_activity_adjustments(db, user, target_date=target_date, start_date=start, end_date=end)
    return StandardResponse(
        coach_message="Activity adjustments loaded.",
        payload={"activity_adjustments": [item.model_dump() for item in items]},
    )


@router.post(f"{settings.api_prefix}/activity-adjustments", response_model=StandardResponse)
def post_activity_adjustment(
    request: ActivityAdjustmentRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    row = create_activity_adjustment(db, user, request)
    summary = build_day_summary(db, user, row.date)
    return StandardResponse(
        coach_message="Activity adjustment added.",
        summary=summary,
        payload={"activity_adjustment": activity_to_response(row).model_dump()},
    )


@router.patch(f"{settings.api_prefix}/activity-adjustments/{{adjustment_id}}", response_model=StandardResponse)
def patch_activity_adjustment(
    adjustment_id: int,
    request: ActivityAdjustmentUpdateRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    try:
        row = update_activity_adjustment(db, user, adjustment_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    summary = build_day_summary(db, user, row.date)
    return StandardResponse(
        coach_message="Activity adjustment updated.",
        summary=summary,
        payload={"activity_adjustment": activity_to_response(row).model_dump()},
    )


@router.delete(f"{settings.api_prefix}/activity-adjustments/{{adjustment_id}}", response_model=StandardResponse)
def remove_activity_adjustment(
    adjustment_id: int,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    row = db.get(ActivityAdjustment, adjustment_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Activity adjustment not found")
    target_date = row.date
    delete_activity_adjustment(db, user, adjustment_id)
    summary = build_day_summary(db, user, target_date)
    return StandardResponse(
        coach_message="Activity adjustment deleted.",
        summary=summary,
    )


@router.post(f"{settings.api_prefix}/eat-feed", response_model=StandardResponse)
def eat_feed(
    request: EatFeedRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    summary = build_day_summary(db, user, date.today())
    feed = build_eat_feed(db, user, request, remaining_kcal=summary.remaining_kcal)
    return StandardResponse(
        coach_message="Eat feed ready.",
        payload={"eat_feed": feed.model_dump()},
    )


@router.post(f"{settings.api_prefix}/intake", response_model=StandardResponse)
async def intake(
    http_request: Request,
    request: IntakeRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    request = enrich_video_intake_request(request, source_label="api_intake")
    provider = get_ai_provider()
    trace_id, task_run_id = _start_observed_task(
        db,
        http_request,
        user=user,
        surface="today",
        task_family="meal_log_now",
        input_text=request.text,
        input_metadata={"meal_type": request.meal_type, "event_context": request.event_context, "metadata": request.metadata},
        source_mode=request.source_mode,
        provider=provider,
    )
    try:
        estimate = await _estimate_with_knowledge(
            provider,
            db=db,
            user=user,
            text=request.text,
            meal_type=request.meal_type,
            mode=request.mode,
            source_mode=request.source_mode,
            clarification_count=0,
            attachments=request.attachments,
            metadata=request.metadata,
        )
        draft = create_or_update_draft(db, user, request, estimate)
        payload: dict[str, object] = {}
        _record_draft_uncertainty(db, trace_id=trace_id, task_run_id=task_run_id, user=user, task_family="meal_log_now", draft=draft)

        if _is_auto_recordable(draft):
            log = confirm_draft(db, user, draft)
            summary = build_day_summary(db, user, draft.date)
            job = _maybe_queue_post_intake_job(
                db,
                user,
                trace_id=trace_id,
                source_mode=log.source_mode,
                text=log.description_raw,
                meal_type=log.meal_type,
                attachments=draft.attachments,
                metadata=draft.draft_context or {},
                log=log,
            )
            if job:
                payload["search_job_id"] = job.id
                payload["pending_async_update"] = True
            recommendation_outcome = attribute_recommendation_outcome(db, user, log)
            if recommendation_outcome:
                payload["recommendation_outcome"] = recommendation_outcome
            record_outcome_event(
                db,
                trace_id=trace_id,
                user_id=user.id,
                task_family="meal_log_now",
                outcome_type="meal_auto_recorded",
                target_id=str(log.id),
                payload={"kcal": log.kcal_estimate},
            )
            finish_task_run(
                db,
                task_run_id,
                status="success",
                result_summary=_task_result_summary_from_draft(
                    draft,
                    extra={
                        "confirmation_mode": (draft.draft_context or {}).get("confirmation_mode"),
                        "log_id": log.id,
                        "missing_slots": draft.missing_slots,
                    },
                ),
            )
            return StandardResponse(
                coach_message=_build_draft_message(draft)[0],
                draft=draft_to_response(draft),
                log=log_to_response(log),
                summary=summary,
                payload=payload,
            )

        message, quick_reply = _build_draft_message(draft)
        if request.source_mode == "video":
            job = _maybe_queue_post_intake_job(
                db,
                user,
                trace_id=trace_id,
                source_mode=request.source_mode,
                text=request.text,
                meal_type=request.meal_type,
                attachments=request.attachments,
                metadata=request.metadata,
                draft=draft,
                notify_on_complete=False,
            )
            if job:
                payload["search_job_id"] = job.id
                payload["pending_async_update"] = True
        if quick_reply:
            payload["quick_reply"] = quick_reply
        finish_task_run(
            db,
            task_run_id,
            status="partial" if draft.missing_slots else "success",
            fallback_reason=(draft.draft_context or {}).get("stop_reason"),
            result_summary=_task_result_summary_from_draft(
                draft,
                extra={
                    "confirmation_mode": (draft.draft_context or {}).get("confirmation_mode"),
                    "missing_slots": draft.missing_slots,
                },
            ),
        )
        return StandardResponse(coach_message=message, draft=draft_to_response(draft), payload=payload)
    except Exception as exc:
        record_error_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            component="intake_route",
            operation="create_intake",
            severity="error",
            exception_type=type(exc).__name__,
            message=str(exc),
            fallback_used=False,
            user_visible_impact="failed_request",
            request_metadata={"source_mode": request.source_mode},
        )
        finish_task_run(db, task_run_id, status="failed", error_type=type(exc).__name__, result_summary={"source_mode": request.source_mode})
        raise


@router.post(f"{settings.api_prefix}/intake/video", response_model=StandardResponse)
async def intake_video(
    http_request: Request,
    request: VideoIntakeRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    intake_request = enrich_video_intake_request(
        IntakeRequest(
            text=request.text,
            meal_type=request.meal_type,
            source_mode="video",
            mode=request.mode,
            attachments=[request.attachment],
            event_at=request.event_at,
            event_context=request.event_context,
            location_context=request.location_context,
            metadata=request.metadata,
        ),
        source_label="api_video_upload",
    )
    provider = get_ai_provider()
    trace_id, task_run_id = _start_observed_task(
        db,
        http_request,
        user=user,
        surface="today",
        task_family="meal_log_now",
        input_text=intake_request.text,
        input_metadata={"video": True, "metadata": intake_request.metadata},
        source_mode="video",
        provider=provider,
    )
    try:
        estimate = await _estimate_with_knowledge(
            provider,
            db=db,
            user=user,
            text=intake_request.text,
            meal_type=intake_request.meal_type,
            mode=intake_request.mode,
            source_mode=intake_request.source_mode,
            clarification_count=0,
            attachments=intake_request.attachments,
            metadata=intake_request.metadata,
        )
        draft = create_or_update_draft(db, user, intake_request, estimate)
        payload: dict[str, object] = {}
        _record_draft_uncertainty(db, trace_id=trace_id, task_run_id=task_run_id, user=user, task_family="meal_log_now", draft=draft)

        if _is_auto_recordable(draft):
            log = confirm_draft(db, user, draft)
            summary = build_day_summary(db, user, draft.date)
            job = _maybe_queue_post_intake_job(
                db,
                user,
                trace_id=trace_id,
                source_mode="video",
                text=log.description_raw,
                meal_type=log.meal_type,
                attachments=draft.attachments,
                metadata=draft.draft_context or {},
                log=log,
                notify_on_complete=request.notify_on_refinement,
            )
            if job:
                payload["search_job_id"] = job.id
                payload["pending_async_update"] = True
            recommendation_outcome = attribute_recommendation_outcome(db, user, log)
            if recommendation_outcome:
                payload["recommendation_outcome"] = recommendation_outcome
            record_outcome_event(
                db,
                trace_id=trace_id,
                user_id=user.id,
                task_family="meal_log_now",
                outcome_type="meal_auto_recorded",
                target_id=str(log.id),
                payload={"kcal": log.kcal_estimate, "source_mode": "video"},
            )
            finish_task_run(
                db,
                task_run_id,
                status="success",
                result_summary=_task_result_summary_from_draft(
                    draft,
                    source_mode="video",
                    extra={
                        "confirmation_mode": (draft.draft_context or {}).get("confirmation_mode"),
                        "log_id": log.id,
                    },
                ),
            )
            return StandardResponse(
                coach_message=_build_draft_message(draft)[0],
                draft=draft_to_response(draft),
                log=log_to_response(log),
                summary=summary,
                payload=payload,
            )

        message, quick_reply = _build_draft_message(draft)
        job = _maybe_queue_post_intake_job(
            db,
            user,
            trace_id=trace_id,
            source_mode="video",
            text=intake_request.text,
            meal_type=intake_request.meal_type,
            attachments=intake_request.attachments,
            metadata=intake_request.metadata,
            draft=draft,
            notify_on_complete=request.notify_on_refinement,
        )
        if job:
            payload["search_job_id"] = job.id
            payload["pending_async_update"] = True
        if quick_reply:
            payload["quick_reply"] = quick_reply
        finish_task_run(
            db,
            task_run_id,
            status="partial" if draft.missing_slots else "success",
            fallback_reason=(draft.draft_context or {}).get("stop_reason"),
            result_summary=_task_result_summary_from_draft(
                draft,
                source_mode="video",
                extra={
                    "confirmation_mode": (draft.draft_context or {}).get("confirmation_mode"),
                    "missing_slots": draft.missing_slots,
                },
            ),
        )
        return StandardResponse(
            coach_message=message,
            draft=draft_to_response(draft),
            payload=payload,
        )
    except Exception as exc:
        record_error_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            component="intake_route",
            operation="create_video_intake",
            severity="error",
            exception_type=type(exc).__name__,
            message=str(exc),
            fallback_used=False,
            user_visible_impact="failed_request",
            request_metadata={"source_mode": "video"},
        )
        finish_task_run(db, task_run_id, status="failed", error_type=type(exc).__name__, result_summary={"source_mode": "video"})
        raise


@router.post(f"{settings.api_prefix}/intake/{{draft_id}}/clarify", response_model=StandardResponse)
async def clarify_intake(
    http_request: Request,
    draft_id: str,
    request: ClarifyRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    draft = db.get(MealDraft, draft_id)
    if not draft or draft.user_id != user.id:
        raise HTTPException(status_code=404, detail="Draft not found")

    provider = get_ai_provider()
    trace_id, task_run_id = _start_observed_task(
        db,
        http_request,
        user=user,
        surface="chat",
        task_family="clarification",
        input_text=request.answer,
        input_metadata={"draft_id": draft_id, "meal_type": draft.meal_type},
        source_mode=draft.source_mode,
        provider=provider,
    )
    try:
        estimate = await _estimate_with_knowledge(
            provider,
            db=db,
            user=user,
            text=f"{draft.raw_input_text}\n{request.answer}",
            meal_type=draft.meal_type,
            mode=draft.mode,
            source_mode=draft.source_mode,
            clarification_count=draft.clarification_count + 1,
            attachments=draft.attachments,
            metadata=draft.draft_context,
        )
        draft = update_draft_with_clarification(db, draft, request.answer, estimate)
        payload: dict[str, object] = {}
        _record_draft_uncertainty(db, trace_id=trace_id, task_run_id=task_run_id, user=user, task_family="clarification", draft=draft)

        if _is_auto_recordable(draft):
            log = confirm_draft(db, user, draft)
            summary = build_day_summary(db, user, draft.date)
            job = _maybe_queue_post_intake_job(
                db,
                user,
                trace_id=trace_id,
                source_mode=log.source_mode,
                text=log.description_raw,
                meal_type=log.meal_type,
                attachments=draft.attachments,
                metadata=draft.draft_context or {},
                log=log,
            )
            if job:
                payload["search_job_id"] = job.id
                payload["pending_async_update"] = True
            recommendation_outcome = attribute_recommendation_outcome(db, user, log)
            if recommendation_outcome:
                payload["recommendation_outcome"] = recommendation_outcome
            record_outcome_event(
                db,
                trace_id=trace_id,
                user_id=user.id,
                task_family="clarification",
                outcome_type="meal_auto_recorded",
                target_id=str(log.id),
                payload={"kcal": log.kcal_estimate},
            )
            finish_task_run(
                db,
                task_run_id,
                status="success",
                result_summary=_task_result_summary_from_draft(
                    draft,
                    extra={
                        "confirmation_mode": (draft.draft_context or {}).get("confirmation_mode"),
                        "log_id": log.id,
                    },
                ),
            )
            return StandardResponse(
                coach_message=_build_draft_message(draft)[0],
                draft=draft_to_response(draft),
                log=log_to_response(log),
                summary=summary,
                payload=payload,
            )

        message, quick_reply = _build_draft_message(draft)
        if quick_reply:
            payload["quick_reply"] = quick_reply
        finish_task_run(
            db,
            task_run_id,
            status="partial" if draft.missing_slots else "success",
            fallback_reason=(draft.draft_context or {}).get("stop_reason"),
            result_summary=_task_result_summary_from_draft(
                draft,
                extra={
                    "confirmation_mode": (draft.draft_context or {}).get("confirmation_mode"),
                    "missing_slots": draft.missing_slots,
                },
            ),
        )
        return StandardResponse(coach_message=message, draft=draft_to_response(draft), payload=payload)
    except Exception as exc:
        record_error_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            component="intake_route",
            operation="clarify_intake",
            severity="error",
            exception_type=type(exc).__name__,
            message=str(exc),
            fallback_used=False,
            user_visible_impact="failed_request",
            request_metadata={"draft_id": draft_id},
        )
        finish_task_run(db, task_run_id, status="failed", error_type=type(exc).__name__, result_summary={"draft_id": draft_id})
        raise


@router.post(f"{settings.api_prefix}/intake/{{draft_id}}/confirm", response_model=StandardResponse)
def confirm_intake(
    http_request: Request,
    draft_id: str,
    request: ConfirmRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    draft = db.get(MealDraft, draft_id)
    if not draft or draft.user_id != user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status == "awaiting_clarification" and not request.force_confirm:
        raise HTTPException(status_code=409, detail="Draft still needs clarification")

    trace_id, task_run_id = _start_observed_task(
        db,
        http_request,
        user=user,
        surface="today",
        task_family="confirmation",
        input_text=draft.raw_input_text,
        input_metadata={"draft_id": draft_id, "force_confirm": request.force_confirm},
        source_mode=draft.source_mode,
    )
    try:
        log = confirm_draft(db, user, draft)
        summary = build_day_summary(db, user, draft.date)
        payload: dict[str, object] = {}
        job = _maybe_queue_post_intake_job(
            db,
            user,
            trace_id=trace_id,
            source_mode=log.source_mode,
            text=log.description_raw,
            meal_type=log.meal_type,
            attachments=draft.attachments,
            metadata=draft.draft_context or {},
            log=log,
        )
        if job:
            payload["search_job_id"] = job.id
            payload["pending_async_update"] = True
        recommendation_outcome = attribute_recommendation_outcome(db, user, log)
        if recommendation_outcome:
            payload["recommendation_outcome"] = recommendation_outcome
        outcome_type = "meal_corrected" if (draft.draft_context or {}).get("correction_target_log_id") else "meal_confirmed"
        record_outcome_event(
            db,
            trace_id=trace_id,
            user_id=user.id,
            task_family="confirmation",
            outcome_type=outcome_type,
            target_id=str(log.id),
            payload={"kcal": log.kcal_estimate},
        )
        finish_task_run(
            db,
            task_run_id,
            status="success",
            result_summary=_task_result_summary_from_draft(
                draft,
                extra={
                    "outcome_type": outcome_type,
                    "log_id": log.id,
                    "confirmation_mode": (draft.draft_context or {}).get("confirmation_mode"),
                },
            ),
        )
        return StandardResponse(
            coach_message="Meal confirmed.",
            draft=draft_to_response(draft),
            log=log_to_response(log),
            summary=summary,
            payload=payload,
        )
    except Exception as exc:
        record_error_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            component="intake_route",
            operation="confirm_intake",
            severity="error",
            exception_type=type(exc).__name__,
            message=str(exc),
            fallback_used=False,
            user_visible_impact="failed_request",
            request_metadata={"draft_id": draft_id, "force_confirm": request.force_confirm},
        )
        finish_task_run(db, task_run_id, status="failed", error_type=type(exc).__name__, result_summary={"draft_id": draft_id})
        raise


@router.post(f"{settings.api_prefix}/meal-logs/manual", response_model=StandardResponse)
def post_manual_meal_log(
    request: ManualMealLogRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    target_date = request.date or (request.event_at.date() if request.event_at else date.today())
    log = create_manual_log(
        db,
        user,
        target_date=target_date,
        meal_type=request.meal_type,
        description_raw=request.description_raw,
        kcal_estimate=request.kcal_estimate,
        event_at=request.event_at,
    )
    recommendation_outcome = attribute_recommendation_outcome(db, user, log)
    summary = build_day_summary(db, user, log.date)
    return StandardResponse(
        coach_message="Manual meal logged.",
        log=log_to_response(log),
        summary=summary,
        payload={"recommendation_outcome": recommendation_outcome or {}},
    )


@router.patch(f"{settings.api_prefix}/meal-logs/{{log_id}}", response_model=StandardResponse)
def patch_meal_log(
    log_id: int,
    request: MealEditRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    log = db.get(MealLog, log_id)
    if not log or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Meal log not found")
    before_kcal = log.kcal_estimate
    updated = edit_log_manual(
        db,
        user,
        log,
        description_raw=request.description_raw,
        kcal_estimate=request.kcal_estimate,
        meal_type=request.meal_type,
        event_at=request.event_at,
    )
    recommendation_correction = mark_recommendation_manual_correction(db, user, updated, before_kcal=before_kcal)
    return StandardResponse(
        coach_message="Meal log updated.",
        log=log_to_response(updated),
        summary=build_day_summary(db, user, updated.date),
        payload={"recommendation_correction": recommendation_correction or {}},
    )


@router.delete(f"{settings.api_prefix}/meal-logs/{{log_id}}", response_model=StandardResponse)
def remove_meal_log(
    log_id: int,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    log = db.get(MealLog, log_id)
    if not log or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Meal log not found")
    target_date = log.date
    delete_log(db, log)
    return StandardResponse(
        coach_message="Meal log deleted.",
        summary=build_day_summary(db, user, target_date),
    )


@router.get(f"{settings.api_prefix}/day-summary", response_model=StandardResponse)
def day_summary(
    date_value: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    return StandardResponse(coach_message="Day summary loaded.", summary=build_day_summary(db, user, date_value or date.today()))


@router.post(f"{settings.api_prefix}/weights", response_model=StandardResponse)
def log_weight(
    request: WeightLogRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    target_date = request.date or date.today()
    entry = db.scalar(select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.date == target_date))
    if entry:
        entry.weight = request.weight
    else:
        entry = WeightLog(user_id=user.id, date=target_date, weight=request.weight)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    refresh_body_goal_calibration(db, user)
    return StandardResponse(coach_message="Weight logged.", summary=build_day_summary(db, user, target_date))


@router.get(f"{settings.api_prefix}/recommendations", response_model=StandardResponse)
def recommendations(
    meal_type: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    summary = build_day_summary(db, user, date.today())
    data = get_recommendations(db, user, meal_type, summary.remaining_kcal)
    data.saved_place_options = [item.model_dump() for item in list_saved_places(db, user)]
    return StandardResponse(coach_message="Recommendations ready.", recommendations=data)


@router.post(f"{settings.api_prefix}/plans/day", response_model=StandardResponse)
def plan_day(
    request: PlanRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    preference = get_or_create_preferences(db, user)
    overlay = build_day_summary(db, user, date.today()).recovery_overlay if request.apply_overlay else None
    plan = build_day_plan(user.daily_calorie_target, preference=preference, overlay=overlay)
    return StandardResponse(coach_message=plan.coach_message, plan=plan)


@router.post(f"{settings.api_prefix}/plans/compensation", response_model=StandardResponse)
def plan_compensation(
    request: PlanRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    preference = get_or_create_preferences(db, user)
    compensation = build_compensation_plan(
        request.expected_extra_kcal,
        compensation_style=preference.compensation_style,
        base_target=user.daily_calorie_target,
    )

    if request.apply_overlay and compensation.options:
        from ..models import PlanEvent

        preferred = next(
            (
                item
                for item in compensation.options
                if item["label"].startswith("Spread")
                or item["label"].startswith("Let")
                or item["label"].startswith("分")
            ),
            compensation.options[1 if len(compensation.options) > 1 else 0],
        )
        overlay = preferred.get("overlay")
        if overlay:
            event = PlanEvent(
                user_id=user.id,
                date=date.today(),
                event_type="recovery_overlay",
                expected_extra_kcal=request.expected_extra_kcal,
                notes=json.dumps(overlay),
            )
            db.add(event)
            db.commit()

    return StandardResponse(coach_message=compensation.coach_message, compensation=compensation)


@router.post(f"{settings.api_prefix}/qa/nutrition", response_model=StandardResponse)
def nutrition_qa(
    http_request: Request,
    request: NutritionQARequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> StandardResponse:
    trace_id, task_run_id = _start_observed_task(
        db,
        http_request,
        user=user,
        surface="recommendation",
        task_family="nutrition_or_food_qa",
        input_text=request.question,
        input_metadata={"allow_search": request.allow_search, "source_hint": request.source_hint},
    )
    try:
        result = answer_calorie_question(
            request.question,
            allow_search=request.allow_search,
            source_hint=request.source_hint,
            context=build_energy_context(db, user),
        )
        packet = result.packet or {}
        matched_items = [
            {"name": name}
            for name in packet.get("matched_items", [])
            if name
        ]
        match_mode = packet.get("match_mode")
        if result.used_search:
            knowledge_mode = "web_search_fallback"
        elif match_mode in {"structured", "activity_estimate", "remaining_budget", "tdee_context"}:
            knowledge_mode = "local_structured"
        elif match_mode == "direct":
            knowledge_mode = "local_direct_doc"
        elif match_mode == "bm25":
            knowledge_mode = "local_bm25"
        else:
            knowledge_mode = "local_unknown"
        record_knowledge_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            question_or_query=request.question,
            knowledge_mode=knowledge_mode,
            matched_items=matched_items,
            matched_docs=packet.get("matched_docs", []),
            used_search=result.used_search,
            search_sources=result.sources,
            grounding_type=None,
            knowledge_gap_type="answer_not_found" if not result.sources and not result.used_search else None,
        )
        if not result.sources and not result.used_search:
            record_unknown_case_event(
                db,
                trace_id=trace_id,
                task_run_id=task_run_id,
                user_id=user.id,
                task_family="nutrition_or_food_qa",
                unknown_type="unknown_nutrition_fact",
                raw_query=request.question,
                source_hint=request.source_hint or "",
                current_answer=result.answer,
                suggested_research_area="nutrition_or_brand_card",
            )
        finish_task_run(
            db,
            task_run_id,
            status="fallback" if result.used_search else ("partial" if not result.sources else "success"),
            fallback_reason="web_search_fallback" if result.used_search else ("answer_not_found" if not result.sources else None),
            result_summary={
                "used_search": result.used_search,
                "source_count": len(result.sources),
                "match_mode": match_mode,
                "route_policy": (
                    "web_search_fallback"
                    if result.used_search
                    else {
                        "activity_estimate": "local_activity_estimate",
                        "remaining_budget": "local_remaining_budget",
                        "tdee_context": "local_tdee_context",
                        "structured": "local_structured",
                        "direct": "local_direct_doc",
                        "bm25": "local_bm25",
                        "search": "web_search_fallback",
                        "none": "answer_not_found",
                    }.get(match_mode, "local_unknown")
                ),
                "route_target": "search" if result.used_search else "local_knowledge",
                "llm_cache": "not_applicable",
                "matched_packs": packet.get("matched_packs", []),
            },
        )
        return StandardResponse(
            coach_message=result.answer,
            payload={"sources": result.sources, "used_search": result.used_search, "packet": result.packet or {}},
        )
    except Exception as exc:
        record_error_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            component="knowledge_qa",
            operation="nutrition_qa",
            severity="error",
            exception_type=type(exc).__name__,
            message=str(exc),
            fallback_used=False,
            user_visible_impact="failed_request",
            request_metadata={"allow_search": request.allow_search},
        )
        finish_task_run(db, task_run_id, status="failed", error_type=type(exc).__name__, result_summary={"source_hint": request.source_hint or ""})
        raise


@router.post(f"{settings.api_prefix}/foods/{{food_id}}/favorite", response_model=StandardResponse)
def favorite_food(food_id: int, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    food = db.get(Food, food_id)
    if not food or food.user_id != user.id:
        raise HTTPException(status_code=404, detail="Food not found")
    food.is_favorite = not food.is_favorite
    db.add(food)
    db.commit()
    db.refresh(food)
    return StandardResponse(coach_message="Food favorite state updated.", payload={"food_id": food.id, "is_favorite": food.is_favorite})


@router.post(f"{settings.api_prefix}/attachments", response_model=StandardResponse)
async def upload_attachment(
    file: UploadFile = File(...),
    user=Depends(current_user),
) -> StandardResponse:
    content = await file.read()
    source_type = infer_source_type_from_mime(file.content_type)
    attachment = store_attachment_bytes(
        content=content,
        mime_type=file.content_type,
        source_type=source_type,
        source_id=file.filename or "upload",
        user_scope=user.line_user_id,
    )
    if source_type == "video":
        attachment = enrich_attachment_with_video_probe(
            attachment,
            content=content,
            mime_type=file.content_type,
        )
    return StandardResponse(
        coach_message="Attachment uploaded.",
        payload={"attachment": attachment_for_persistence(attachment), "signed_url": attachment.get("signed_url", "")},
    )


@router.post("/webhooks/line")
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    body = await request.body()
    if not verify_line_signature(body, x_line_signature):
        raise HTTPException(status_code=401, detail="Invalid LINE signature")

    payload = await request.json()
    provider = get_ai_provider()

    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue

        source = event.get("source") or {}
        line_user_id = source.get("userId")
        if not line_user_id:
            continue
        user = get_or_create_user(db, line_user_id=line_user_id, display_name="LINE User")
        reply_token = event.get("replyToken")
        message = event.get("message") or {}
        message_type = message.get("type")

        if message_type == "text":
            text = (message.get("text") or "").strip()
            event_trace_id = f"{get_request_trace_id(request)}-{message.get('id') or event.get('timestamp')}"
            explicit_feedback = detect_explicit_feedback(text)
            if explicit_feedback:
                create_conversation_trace(
                    db,
                    trace_id=event_trace_id,
                    user_id=user.id,
                    line_user_id=user.line_user_id,
                    surface="chat",
                    task_family="fallback_ambiguous",
                    source_mode="text",
                    input_text=text,
                    input_metadata={"line_message_id": message.get("id"), "event_type": event.get("type")},
                    thread_id=source.get("groupId") or source.get("roomId"),
                    message_id=message.get("id"),
                )
                record_feedback_event(
                    db,
                    trace_id=event_trace_id,
                    user_id=user.id,
                    feedback_type=explicit_feedback["feedback_type"],
                    feedback_label=explicit_feedback["feedback_label"],
                    free_text=text,
                    severity=explicit_feedback["severity"],
                )
            correction = detect_chat_correction(text)
            if correction:
                apply_preference_correction(db, user, correction)
                await reply_line_message(reply_token, "收到，我已經把這個偏好更新進記憶。")
                continue

            open_draft = _latest_open_draft(db, user)
            if open_draft and _is_defer_text(text):
                await reply_line_message(reply_token, "好，我先保留這筆。你之後直接回我一句就能繼續。")
                continue
            if open_draft and _is_confirm_text(text):
                log = confirm_draft(db, user, open_draft)
                attribute_recommendation_outcome(db, user, log)
                maybe_queue_menu_precision_job(db, user, trace_id=event_trace_id, text=log.description_raw, log=log)
                await reply_line_message(reply_token, f"已記錄：{log.description_raw}，約 {log.kcal_estimate} kcal。")
                continue
            if open_draft and open_draft.status == "awaiting_clarification":
                estimate = await _estimate_with_knowledge(
                    provider,
                    db=db,
                    user=user,
                    text=f"{open_draft.raw_input_text}\n{text}",
                    meal_type=open_draft.meal_type,
                    mode=open_draft.mode,
                    source_mode=open_draft.source_mode,
                    clarification_count=open_draft.clarification_count + 1,
                    attachments=open_draft.attachments,
                    metadata=open_draft.draft_context.get("source_metadata", {}) if open_draft.draft_context else {},
                )
                updated_draft = update_draft_with_clarification(db, open_draft, text, estimate)
                if _is_auto_recordable(updated_draft):
                    log = confirm_draft(db, user, updated_draft)
                    attribute_recommendation_outcome(db, user, log)
                    maybe_queue_menu_precision_job(db, user, trace_id=event_trace_id, text=log.description_raw, log=log)
                    await reply_line_message(reply_token, f"已記錄：{log.description_raw}，約 {log.kcal_estimate} kcal。")
                    continue
                reply_text, quick_reply = _build_draft_message(updated_draft)
                flex_message = _build_draft_flex_payload(updated_draft)
                await reply_line_message(reply_token, reply_text, quick_reply=quick_reply, flex_message=flex_message)
                continue

            task, task_confidence = _route_text_task(text)
            if task_confidence < 0.45 or task == "fallback_ambiguous":
                await reply_line_message(reply_token, "你想要我幫你做哪一種？", quick_reply=_disambiguation_options())
                continue

            if task == "remaining_or_recommendation":
                if any(token in text.lower() for token in ["附近", "哪裡", "where", "nearby"]):
                    await reply_line_message(reply_token, "你要我看現在附近，還是接下來要去的地方？", quick_reply=_location_route_options())
                    continue
                energy_context = build_energy_context(db, user)
                wants_recommendations = not looks_like_remaining_calorie_question(text) or any(
                    token in text.lower() for token in ["推薦", "吃什麼", "suggest", "recommend"]
                )
                if wants_recommendations:
                    summary = energy_context.summary
                    recs = get_recommendations(db, user, None, summary.remaining_kcal)
                    lines = [f"Today you have about {summary.remaining_kcal} kcal left."]
                    for item in recs.items[:3]:
                        lines.append(f"- {item.name} ({item.kcal_low}-{item.kcal_high} kcal)")
                    await reply_line_message(reply_token, "\n".join(lines))
                else:
                    result = answer_calorie_question(text, allow_search=False, context=energy_context)
                    await reply_line_message(reply_token, result.answer)
                continue

            if task == "future_event_probe":
                parsed_event = parse_future_meal_event_text(text)
                if not parsed_event:
                    await reply_line_message(reply_token, "你可以直接說像是「週五晚餐聚餐」或「明天中午吃到飽」，我會先幫你記成未來大餐事件。")
                    continue
                meal_event = create_meal_event(
                    db,
                    user,
                    MealEventRequest(
                        event_date=parsed_event.event_date,
                        meal_type=parsed_event.meal_type,
                        title=parsed_event.title,
                        expected_kcal=parsed_event.expected_kcal,
                        notes=parsed_event.notes,
                        source="chat",
                    ),
                )
                meal_label = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "點心"}.get(meal_event.meal_type, meal_event.meal_type)
                await reply_line_message(
                    reply_token,
                    f"已先記下 {meal_event.event_date.isoformat()} 的{meal_label}事件「{meal_event.title}」，先抓約 {meal_event.expected_kcal} kcal。到前一天我會再提醒你。",
                )
                continue

            if task == "weekly_drift_probe":
                summary = build_day_summary(db, user, date.today())
                if summary.should_offer_weekly_recovery:
                    await reply_line_message(reply_token, "這週看起來有點超標，要不要我幫你排一個溫和回收方案？", quick_reply=["回到正常", "小幅回收 1 天", "分 2-3 天攤平"])
                else:
                    await reply_line_message(reply_token, "這週還在可控範圍內，先照現在的節奏就好。")
                continue

            if task == "weight_log":
                match = re.search(r"(\d{2,3}(?:\.\d)?)", text)
                if not match:
                    await reply_line_message(reply_token, "直接傳像是 72.4 這樣的體重數字給我，我就會幫你記錄。")
                    continue
                value = float(match.group(1))
                weight_row = db.scalar(select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.date == date.today()))
                if weight_row:
                    weight_row.weight = value
                else:
                    weight_row = WeightLog(user_id=user.id, date=date.today(), weight=value)
                db.add(weight_row)
                db.commit()
                refresh_body_goal_calibration(db, user)
                await reply_line_message(reply_token, f"已記錄體重 {value} kg。")
                continue

            if task == "nutrition_or_food_qa":
                result = answer_calorie_question(
                    text,
                    allow_search=True,
                    context=build_energy_context(db, user),
                )
                await reply_line_message(reply_token, result.answer)
                continue

            if task == "meal_log_correction":
                target_log = db.scalar(select(MealLog).where(MealLog.user_id == user.id).order_by(MealLog.event_at.desc(), MealLog.created_at.desc()))
                if not target_log:
                    await reply_line_message(reply_token, "我現在找不到最近一筆可修正的餐點。")
                    continue
                estimate = await _estimate_with_knowledge(
                    provider,
                    db=db,
                    user=user,
                    text=f"{target_log.description_raw}\n{text}",
                    meal_type=target_log.meal_type,
                    mode="standard",
                    source_mode=target_log.source_mode,
                    clarification_count=0,
                    attachments=[],
                    metadata={},
                )
                draft = create_correction_preview(db, user, target_log, correction_text=text, estimate=estimate)
                reply_text, quick_reply = _build_draft_message(draft)
                await reply_line_message(reply_token, reply_text, quick_reply=quick_reply, flex_message=_build_draft_flex_payload(draft))
                continue

            meal_request = IntakeRequest(
                text=text,
                meal_type=infer_meal_type(text),
                source_mode="text",
                mode="standard",
                event_at=utcnow(),
                metadata={"channel": "line"},
            )
            estimate = await _estimate_with_knowledge(
                provider,
                db=db,
                user=user,
                text=meal_request.text,
                meal_type=meal_request.meal_type,
                mode=meal_request.mode,
                source_mode=meal_request.source_mode,
                clarification_count=0,
                attachments=[],
                metadata=meal_request.metadata,
            )
            draft = create_or_update_draft(db, user, meal_request, estimate)
            if _is_auto_recordable(draft):
                log = confirm_draft(db, user, draft)
                attribute_recommendation_outcome(db, user, log)
                maybe_queue_menu_precision_job(db, user, trace_id=event_trace_id, text=log.description_raw, log=log)
            reply_text, quick_reply = _build_draft_message(draft)
            await reply_line_message(reply_token, reply_text, quick_reply=quick_reply, flex_message=_build_draft_flex_payload(draft))
            continue

        if message_type == "location":
            event_trace_id = f"{get_request_trace_id(request)}-{message.get('id') or event.get('timestamp')}"
            location_context = resolve_location_context(
                db,
                user,
                {
                    "mode": "geolocation",
                    "lat": message.get("latitude"),
                    "lng": message.get("longitude"),
                    "label": message.get("title") or "Current area",
                    "query": message.get("address") or message.get("title") or "Current area",
                },
            )
            summary = build_day_summary(db, user, date.today())
            nearby = build_nearby_heuristics(db, user, location_context=location_context, meal_type=None, remaining_kcal=summary.remaining_kcal)
            job = create_search_job(
                db,
                user,
                job_type="nearby_places",
                request_payload={**location_context, "remaining_kcal": summary.remaining_kcal, "notify_on_complete": True, "trace_id": event_trace_id},
            )
            lines = [f"Fast shortlist for {nearby.location_context_used}:"]
            for item in nearby.heuristic_items[:3]:
                lines.append(f"- {item.name} ({item.kcal_low}-{item.kcal_high} kcal)")
            lines.append(f"我正在背景幫你補查更精準的選項，任務編號 {job.id[:8]}。")
            await reply_line_message(reply_token, "\n".join(lines))
            continue

        if message_type in {"image", "audio", "video"}:
            event_trace_id = f"{get_request_trace_id(request)}-{message.get('id') or event.get('timestamp')}"
            content, attachment = await fetch_line_content(message.get("id"), line_user_id=line_user_id)
            text = ""
            source_mode = "image" if message_type == "image" else "audio" if message_type == "audio" else "video"
            if message_type == "audio":
                text = await provider.transcribe_audio(content=content, mime_type=attachment.get("mime_type"))
            intake_request = IntakeRequest(
                text=text,
                meal_type="meal",
                source_mode=source_mode,
                mode="standard",
                attachments=[attachment_for_persistence(attachment)],
                event_at=utcnow(),
                metadata={"channel": "line"},
            )
            if source_mode == "video":
                intake_request = enrich_video_intake_request(intake_request, source_label="line_video")
            estimate = await _estimate_with_knowledge(
                provider,
                db=db,
                user=user,
                text=intake_request.text,
                meal_type=intake_request.meal_type,
                mode=intake_request.mode,
                source_mode=intake_request.source_mode,
                clarification_count=0,
                attachments=[attachment],
                metadata=intake_request.metadata,
            )
            draft = create_or_update_draft(db, user, intake_request, estimate)
            if _is_auto_recordable(draft):
                log = confirm_draft(db, user, draft)
                attribute_recommendation_outcome(db, user, log)
                _maybe_queue_post_intake_job(
                    db,
                    user,
                    trace_id=event_trace_id,
                    source_mode=log.source_mode,
                    text=log.description_raw,
                    meal_type=log.meal_type,
                    attachments=draft.attachments,
                    metadata=draft.draft_context or {},
                    log=log,
                )
            elif source_mode == "video":
                _maybe_queue_post_intake_job(
                    db,
                    user,
                    trace_id=event_trace_id,
                    source_mode="video",
                    text=intake_request.text,
                    meal_type=intake_request.meal_type,
                    attachments=intake_request.attachments,
                    metadata=intake_request.metadata,
                    draft=draft,
                    notify_on_complete=False,
                )
            reply_text, quick_reply = _build_draft_message(draft)
            await reply_line_message(reply_token, reply_text, quick_reply=quick_reply, flex_message=_build_draft_flex_payload(draft))

    return {"ok": True}
