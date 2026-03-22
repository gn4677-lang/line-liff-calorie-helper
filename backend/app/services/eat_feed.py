from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import resolved_timezone, settings
from ..models import FavoriteStore, Food, GoldenOrder, MealLog, RecommendationProfile, RecommendationSession, User, utcnow
from ..providers.factory import get_ai_provider
from ..schemas import EatFeedCandidateResponse, EatFeedRequest, EatFeedResponse, EatFeedSectionResponse, SmartChipResponse
from .llm_support import _extract_provider_usage, complete_structured_sync, rerank_candidates_sync, select_relevant_memory_slice_sync
from .memory import build_recommendation_memory_packet
from .proactive import build_nearby_heuristics, resolve_location_context


SOURCE_PRIOR = {
    "golden_order": 30.0,
    "favorite_food": 24.0,
    "favorite_store": 20.0,
    "nearby_heuristic": 14.0,
    "external_nearby_result": 8.0,
}

SMART_CHIP_LIBRARY: dict[str, dict[str, str]] = {
    "high_protein": {"label": "高蛋白", "intent_kind": "nutrition"},
    "soup": {"label": "想喝湯", "intent_kind": "texture"},
    "light": {"label": "清爽一點", "intent_kind": "nutrition"},
    "comfort": {"label": "想吃療癒", "intent_kind": "mood"},
    "filling": {"label": "想吃飽", "intent_kind": "satiety"},
    "nearby": {"label": "近一點", "intent_kind": "distance"},
    "quick_pickup": {"label": "拿了就走", "intent_kind": "speed"},
    "repeat_safe": {"label": "吃熟悉的", "intent_kind": "safety"},
    "rice_or_noodle": {"label": "飯或麵", "intent_kind": "format"},
    "indulgent": {"label": "今天放鬆", "intent_kind": "mood"},
}

TOKEN_HINTS = {
    "high_protein": ("雞", "雞胸", "蛋", "subway", "沙拉", "豆腐", "牛肉", "魚"),
    "soup": ("湯", "味噌", "清燉", "鍋", "拉麵", "麵線"),
    "light": ("沙拉", "輕食", "清蒸", "便當", "subway", "優格", "水果"),
    "comfort": ("炸", "披薩", "火鍋", "燒肉", "拉麵", "咖哩", "雞排"),
    "filling": ("飯", "麵", "便當", "丼", "漢堡", "pizza", "鍋"),
    "rice_or_noodle": ("飯", "麵", "便當", "丼", "粥", "冬粉", "米粉"),
    "indulgent": ("炸", "燒肉", "火鍋", "pizza", "蛋糕", "甜點", "宵夜"),
}


@dataclass
class Candidate:
    candidate_id: str
    title: str
    store_name: str = ""
    meal_types: list[str] = field(default_factory=list)
    kcal_low: int = 0
    kcal_high: int = 0
    distance_meters: int | None = None
    travel_minutes: int | None = None
    open_now: bool | None = None
    source_type: str = "favorite_food"
    reason_factors: list[str] = field(default_factory=list)
    external_link: str = ""
    usage_count: int = 0
    last_used_at: Any = None
    support_tags: set[str] = field(default_factory=set)
    source_prior: float = 0.0
    memory_fit: float = 0.0
    context_fit: float = 0.0
    familiarity_bonus: float = 0.0
    repeat_penalty: float = 0.0
    distance_penalty: float = 0.0
    risk_penalty: float = 0.0
    chip_bonus: float = 0.0
    final_score: float = 0.0


def build_eat_feed(
    db: Session,
    user: User,
    request: EatFeedRequest,
    *,
    remaining_kcal: int,
    provider: Any | None = None,
) -> EatFeedResponse:
    profile = _get_or_create_profile(db, user)
    provider = provider or get_ai_provider()
    memory_packet = build_recommendation_memory_packet(db, user, meal_type=request.meal_type, remaining_kcal=remaining_kcal)
    if settings.eat_policy_llm_enabled:
        memory_packet = select_relevant_memory_slice_sync(
            provider,
            task_label="eat_feed",
            text=request.query or request.style_context or "",
            meal_type=request.meal_type,
            memory_packet=memory_packet,
        )
    memory_contract = memory_packet.pop("_relevant_memory_slice_contract", None)
    memory_usage = memory_packet.pop("_relevant_memory_slice_usage", None)
    communication_profile = memory_packet.get("communication_profile") or {}
    recent_logs = list(
        db.scalars(
            select(MealLog)
            .where(MealLog.user_id == user.id)
            .order_by(desc(MealLog.event_at), desc(MealLog.created_at))
            .limit(18)
        )
    )
    location_context = _safe_location_context(db, user, request)
    candidates = _build_candidates(db, user, request, remaining_kcal=remaining_kcal, location_context=location_context)
    ranked = _rank_candidates(
        candidates,
        request=request,
        remaining_kcal=remaining_kcal,
        memory_packet=memory_packet,
        recent_logs=recent_logs,
        profile=profile,
        selected_chip_id=None,
    )
    smart_chips, chip_usage = generate_session_smart_chips(
        request=request,
        memory_packet=memory_packet,
        ranked_candidates=ranked,
        recent_logs=recent_logs,
        profile=profile,
        provider=provider,
    )
    smart_chips = _filter_material_smart_chips(
        smart_chips,
        candidates=candidates,
        request=request,
        remaining_kcal=remaining_kcal,
        memory_packet=memory_packet,
        recent_logs=recent_logs,
        profile=profile,
        baseline_ranked=ranked,
    )
    selected_chip_id = request.selected_chip_id if any(chip.id == request.selected_chip_id for chip in smart_chips) else None
    if selected_chip_id:
        ranked = _rank_candidates(
            candidates,
            request=request,
            remaining_kcal=remaining_kcal,
            memory_packet=memory_packet,
            recent_logs=recent_logs,
            profile=profile,
            selected_chip_id=selected_chip_id,
        )

    rerank_payload = _apply_llm_candidate_rerank(
        ranked,
        provider=provider if settings.eat_policy_llm_enabled else None,
        request=request,
        remaining_kcal=remaining_kcal,
        memory_packet=memory_packet,
        communication_profile=communication_profile,
    )
    hero_reason = rerank_payload["hero_reason"]
    top_pick = _candidate_to_response(ranked[0]) if ranked else None
    backup_picks = [_candidate_to_response(item) for item in ranked[1:3]]
    exploration_sections = _build_exploration_sections(ranked[3:], request=request)
    session = create_recommendation_session(
        db,
        user,
        request=request,
        top_pick=top_pick,
        backup_picks=backup_picks,
        ranked_candidates=ranked,
        location_context=location_context,
    )
    return EatFeedResponse(
        session_id=session.id,
        remaining_kcal=remaining_kcal,
        top_pick=top_pick,
        backup_picks=backup_picks,
        exploration_sections=exploration_sections,
        location_context_used=location_context.get("location_context") if location_context else None,
        smart_chips=smart_chips,
        hero_reason=hero_reason or (top_pick.reason_factors[0] if top_pick and top_pick.reason_factors else ""),
        refining=False,
        policy_contract={
            **(rerank_payload.get("policy_contract") or {}),
            "relevant_memory_slice": memory_contract,
            "llm_usage": _merge_usage(memory_usage, chip_usage, rerank_payload.get("provider_usage")),
        },
        more_results_available=any(section.items for section in exploration_sections),
    )


def create_recommendation_session(
    db: Session,
    user: User,
    *,
    request: EatFeedRequest,
    top_pick: EatFeedCandidateResponse | None,
    backup_picks: list[EatFeedCandidateResponse],
    ranked_candidates: list[Candidate],
    location_context: dict[str, Any] | None,
) -> RecommendationSession:
    session = RecommendationSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        surface="eat",
        meal_type=request.meal_type,
        time_context=request.time_context,
        style_context=request.style_context or "",
        location_context=(location_context or {}).get("location_context", ""),
        status="shown",
        shown_top_pick=top_pick.model_dump() if top_pick else {},
        shown_backup_picks=[item.model_dump() for item in backup_picks],
        shown_scores=[
            {
                "candidate_id": item.candidate_id,
                "title": item.title,
                "source_type": item.source_type,
                "travel_minutes": item.travel_minutes,
                "final_score": round(item.final_score, 2),
            }
            for item in ranked_candidates[:12]
        ],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def attribute_recommendation_outcome(db: Session, user: User, log: MealLog) -> dict[str, Any] | None:
    sessions = list(
        db.scalars(
            select(RecommendationSession)
            .where(
                RecommendationSession.user_id == user.id,
                RecommendationSession.meal_type == log.meal_type,
                RecommendationSession.status == "shown",
                RecommendationSession.created_at >= utcnow() - timedelta(hours=2),
            )
            .order_by(desc(RecommendationSession.created_at))
        )
    )
    for session in sessions:
        matched = _match_session_candidate(session, log.description_raw)
        if not matched:
            continue
        session.status = "accepted"
        session.accepted_candidate = matched["candidate"]
        session.accepted_event_type = matched["event_type"]
        session.accepted_at = utcnow()
        profile = _get_or_create_profile(db, user)
        _apply_profile_adjustment(profile, matched["event_type"])
        _maybe_apply_distance_adjustment(profile, matched["candidate"])
        db.add(session)
        db.add(profile)
        db.commit()
        db.refresh(session)
        return {"session_id": session.id, "event_type": matched["event_type"]}
    return None


def mark_recommendation_manual_correction(db: Session, user: User, log: MealLog, *, before_kcal: int) -> dict[str, Any] | None:
    delta = abs((log.kcal_estimate or 0) - (before_kcal or 0))
    if delta < 80:
        return None
    sessions = list(
        db.scalars(
            select(RecommendationSession)
            .where(
                RecommendationSession.user_id == user.id,
                RecommendationSession.status == "accepted",
                RecommendationSession.meal_type == log.meal_type,
                RecommendationSession.accepted_at >= utcnow() - timedelta(days=1),
            )
            .order_by(desc(RecommendationSession.accepted_at))
        )
    )
    for session in sessions:
        candidate = session.accepted_candidate or {}
        if _titles_match(log.description_raw, candidate.get("title", "")):
            session.status = "corrected_after_acceptance"
            session.accepted_event_type = "post_log_manual_correction"
            db.add(session)
            db.commit()
            db.refresh(session)
            return {"session_id": session.id, "event_type": "post_log_manual_correction"}
    return None


def generate_session_smart_chips(
    *,
    request: EatFeedRequest,
    memory_packet: dict[str, Any],
    ranked_candidates: list[Candidate],
    recent_logs: list[MealLog],
    profile: RecommendationProfile,
    provider: Any | None = None,
) -> tuple[list[SmartChipResponse], dict[str, Any]]:
    """Returns (smart_chips, chip_selection_usage)."""
    top_window = ranked_candidates[:10]
    if not top_window:
        return [], {}
    scored: list[dict[str, Any]] = []
    for chip_id, spec in SMART_CHIP_LIBRARY.items():
        supported = sum(1 for candidate in top_window if _candidate_supports_chip(candidate, chip_id))
        if not _chip_passes_gate(chip_id, supported, len(top_window), request=request, memory_packet=memory_packet):
            continue
        scored.append(
            {
                "id": chip_id,
                "label": spec["label"],
                "intent_kind": spec["intent_kind"],
                "supported_candidate_count": supported,
                "score": _smart_chip_score(chip_id, request=request, memory_packet=memory_packet, recent_logs=recent_logs, profile=profile),
            }
        )
    scored.sort(key=lambda item: (-item["score"], -item["supported_candidate_count"], item["label"]))
    shortlist = scored[:6]
    selected_ids, chip_usage = _choose_chip_ids(shortlist, request=request, memory_packet=memory_packet, provider=provider)
    if not selected_ids:
        selected_ids = [item["id"] for item in shortlist[:3]]
    chosen = [item for item in shortlist if item["id"] in selected_ids]
    chosen.sort(key=lambda item: selected_ids.index(item["id"]))
    chips = [
        SmartChipResponse(
            id=item["id"],
            label=item["label"],
            intent_kind=item["intent_kind"],
            supported_candidate_count=item["supported_candidate_count"],
        )
        for item in chosen[:3]
    ]
    return chips, chip_usage


def _filter_material_smart_chips(
    smart_chips: list[SmartChipResponse],
    *,
    candidates: list[Candidate],
    request: EatFeedRequest,
    remaining_kcal: int,
    memory_packet: dict[str, Any],
    recent_logs: list[MealLog],
    profile: RecommendationProfile,
    baseline_ranked: list[Candidate],
) -> list[SmartChipResponse]:
    if not smart_chips:
        return []
    baseline_top_ids = [item.candidate_id for item in baseline_ranked[:3]]
    material: list[SmartChipResponse] = []
    for chip in smart_chips:
        reranked = _rank_candidates(
            candidates,
            request=request,
            remaining_kcal=remaining_kcal,
            memory_packet=memory_packet,
            recent_logs=recent_logs,
            profile=profile,
            selected_chip_id=chip.id,
        )
        reranked_top_ids = [item.candidate_id for item in reranked[:3]]
        if reranked_top_ids != baseline_top_ids:
            material.append(chip)
    if material:
        return material[:3]
    if len(baseline_ranked) <= 2:
        return smart_chips[:2]
    return []


def _safe_location_context(db: Session, user: User, request: EatFeedRequest) -> dict[str, Any] | None:
    if request.location_mode == "none":
        return None
    try:
        return resolve_location_context(
            db,
            user,
            {
                "mode": request.location_mode,
                "saved_place_id": request.saved_place_id,
                "lat": request.lat,
                "lng": request.lng,
                "query": request.query,
                "label": request.query,
            },
        )
    except Exception:
        return None


def _get_or_create_profile(db: Session, user: User) -> RecommendationProfile:
    profile = db.scalar(select(RecommendationProfile).where(RecommendationProfile.user_id == user.id))
    if profile:
        return profile
    profile = RecommendationProfile(user_id=user.id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _build_candidates(
    db: Session,
    user: User,
    request: EatFeedRequest,
    *,
    remaining_kcal: int,
    location_context: dict[str, Any] | None,
) -> list[Candidate]:
    deduped: dict[str, Candidate] = {}
    golden_orders = list(
        db.scalars(
            select(GoldenOrder)
            .where(GoldenOrder.user_id == user.id)
            .order_by(desc(GoldenOrder.usage_count), desc(GoldenOrder.last_used_at))
            .limit(8)
        )
    )
    foods = list(
        db.scalars(
            select(Food)
            .where(Food.user_id == user.id, ((Food.is_favorite.is_(True)) | (Food.usage_count >= 2)))
            .order_by(desc(Food.is_golden), desc(Food.is_favorite), desc(Food.usage_count), desc(Food.last_used_at))
            .limit(12)
        )
    )
    favorite_stores = list(
        db.scalars(
            select(FavoriteStore)
            .where(FavoriteStore.user_id == user.id)
            .order_by(desc(FavoriteStore.usage_count), desc(FavoriteStore.last_used_at))
            .limit(8)
        )
    )
    golden_by_place = {row.place_id: row for row in golden_orders if row.place_id}
    golden_by_store = {row.store_name.lower(): row for row in golden_orders if row.store_name}

    for row in golden_orders:
        if request.meal_type and row.meal_types and request.meal_type not in row.meal_types:
            continue
        candidate = Candidate(
            candidate_id=f"golden:{row.id}",
            title=row.title,
            store_name=row.store_name or "",
            meal_types=list(row.meal_types or [request.meal_type]),
            kcal_low=row.kcal_low,
            kcal_high=row.kcal_high,
            source_type="golden_order",
            reason_factors=["這是你反覆接受的穩定選項", _kcal_reason(row.kcal_low, row.kcal_high, remaining_kcal)],
            usage_count=row.usage_count or 0,
            last_used_at=row.last_used_at,
        )
        _put_candidate(deduped, candidate)

    for row in foods:
        if request.meal_type and row.meal_types and request.meal_type not in row.meal_types:
            continue
        store_context = row.store_context or {}
        top_store_name = str(store_context.get("top_store_name") or "").strip()
        store_profile = _top_store_profile(store_context)
        kcal_low = store_profile.get("kcal_low", row.kcal_low) if store_profile else row.kcal_low
        kcal_high = store_profile.get("kcal_high", row.kcal_high) if store_profile else row.kcal_high
        reasons = ["你最近常接受這個品項", _kcal_reason(kcal_low, kcal_high, remaining_kcal)]
        if top_store_name:
            reasons.insert(1, f"而且多半是在 {top_store_name}")
        store_context_reason = _store_context_reason(store_profile)
        if store_context_reason:
            reasons.insert(2 if top_store_name else 1, store_context_reason)
        candidate = Candidate(
            candidate_id=f"food:{row.id}",
            title=row.name,
            store_name=top_store_name,
            meal_types=list(row.meal_types or [request.meal_type]),
            kcal_low=kcal_low,
            kcal_high=kcal_high,
            source_type="favorite_food",
            reason_factors=reasons,
            external_link=(row.external_links or [""])[0] if row.external_links else "",
            usage_count=row.usage_count or 0,
            last_used_at=row.last_used_at,
        )
        _put_candidate(deduped, candidate)

    for row in favorite_stores:
        golden = golden_by_place.get(row.place_id) or golden_by_store.get((row.name or "").lower())
        kcal_low = golden.kcal_low if golden else 420
        kcal_high = golden.kcal_high if golden else 720
        meal_types = list(golden.meal_types) if golden and golden.meal_types else [request.meal_type]
        title = golden.title if golden else row.name
        candidate = Candidate(
            candidate_id=f"store:{row.id}",
            title=title,
            store_name=row.name,
            meal_types=meal_types,
            kcal_low=kcal_low,
            kcal_high=kcal_high,
            source_type="favorite_store",
            reason_factors=["這家店是你的熟悉選項", _kcal_reason(kcal_low, kcal_high, remaining_kcal)],
            external_link=row.external_link or "",
            usage_count=row.usage_count or 0,
            last_used_at=row.last_used_at,
        )
        _put_candidate(deduped, candidate)

    if location_context:
        nearby = build_nearby_heuristics(
            db,
            user,
            location_context=location_context,
            meal_type=request.meal_type,
            remaining_kcal=remaining_kcal,
        )
        for index, row in enumerate(nearby.heuristic_items):
            candidate = Candidate(
                candidate_id=f"nearby:{index}:{row.place_id or row.name}",
                title=row.name,
                store_name=row.name,
                meal_types=[request.meal_type],
                kcal_low=row.kcal_low,
                kcal_high=row.kcal_high,
                distance_meters=row.distance_meters,
                travel_minutes=row.travel_minutes,
                open_now=row.open_now,
                source_type="nearby_heuristic" if row.source != "external" else "external_nearby_result",
                reason_factors=(row.reason_factors or [row.reason or "附近現在可行"]),
                external_link=row.external_link or "",
            )
            _put_candidate(deduped, candidate)

    for candidate in deduped.values():
        candidate.support_tags = _derive_support_tags(candidate)
    return list(deduped.values())


def _put_candidate(bucket: dict[str, Candidate], candidate: Candidate) -> None:
    key = _normalize_title(candidate.title)
    current = bucket.get(key)
    if current is None or SOURCE_PRIOR.get(candidate.source_type, 0.0) > SOURCE_PRIOR.get(current.source_type, 0.0):
        bucket[key] = candidate


def _rank_candidates(
    candidates: list[Candidate],
    *,
    request: EatFeedRequest,
    remaining_kcal: int,
    memory_packet: dict[str, Any],
    recent_logs: list[MealLog],
    profile: RecommendationProfile,
    selected_chip_id: str | None,
) -> list[Candidate]:
    ranked: list[Candidate] = []
    preferences = memory_packet.get("preferences", {})
    hard_dislikes = {_normalize_title(item) for item in preferences.get("hard_dislikes", []) if item and item != "none"}
    for candidate in candidates:
        if not _passes_hard_filters(candidate, request=request, remaining_kcal=remaining_kcal, hard_dislikes=hard_dislikes):
            continue
        candidate.source_prior = _source_prior_score(candidate, profile=profile)
        candidate.memory_fit = _memory_fit(candidate, request=request, memory_packet=memory_packet)
        candidate.context_fit = _context_fit(candidate, request=request, remaining_kcal=remaining_kcal)
        candidate.familiarity_bonus = _familiarity_bonus(candidate, recent_logs=recent_logs)
        candidate.repeat_penalty = _repeat_penalty(candidate, recent_logs=recent_logs, profile=profile)
        candidate.distance_penalty = _distance_penalty(candidate, profile=profile)
        candidate.risk_penalty = _risk_penalty(candidate)
        candidate.chip_bonus = _chip_bonus(candidate, selected_chip_id)
        candidate.final_score = round(
            candidate.source_prior
            + candidate.memory_fit
            + candidate.context_fit
            + candidate.familiarity_bonus
            - candidate.repeat_penalty
            - candidate.distance_penalty
            - candidate.risk_penalty
            + candidate.chip_bonus,
            4,
        )
        ranked.append(candidate)
    ranked.sort(key=lambda item: (-item.final_score, -item.usage_count, item.title.lower()))
    return _enforce_memory_first_top_pick(ranked, profile=profile)


def _passes_hard_filters(candidate: Candidate, *, request: EatFeedRequest, remaining_kcal: int, hard_dislikes: set[str]) -> bool:
    normalized = _normalize_title(candidate.title)
    if any(dislike and dislike in normalized for dislike in hard_dislikes):
        return False
    if request.meal_type and candidate.meal_types and request.meal_type not in candidate.meal_types:
        return False
    if candidate.kcal_high and candidate.kcal_high > remaining_kcal + 180 and request.style_context != "indulge":
        return False
    if candidate.open_now is False and candidate.source_type in {"nearby_heuristic", "external_nearby_result"}:
        return False
    return True


def _source_prior_score(candidate: Candidate, *, profile: RecommendationProfile) -> float:
    base = SOURCE_PRIOR.get(candidate.source_type, 0.0)
    if candidate.source_type in {"golden_order", "favorite_food", "favorite_store"}:
        return base + (profile.favorite_bias_strength - 0.6) * 12
    if candidate.source_type in {"nearby_heuristic", "external_nearby_result"}:
        return base + (profile.nearby_exploration_preference - 0.35) * 14
    return base


def _memory_fit(candidate: Candidate, *, request: EatFeedRequest, memory_packet: dict[str, Any]) -> float:
    score = 0.0
    preferences = memory_packet.get("preferences", {})
    hypotheses_text = " ".join((item.get("label", "") + " " + item.get("statement", "")) for item in memory_packet.get("active_hypotheses", []))
    signals_text = " ".join(item.get("canonical_label", "") for item in memory_packet.get("relevant_signals", []))
    recent_text = " ".join(item.get("description", "") for item in memory_packet.get("recent_acceptance", []))
    haystack = " ".join([candidate.title.lower(), candidate.store_name.lower()])
    meal_pattern = (memory_packet.get("meal_acceptance_pattern", {}) or {}).get(request.meal_type or "", {})
    local_now = datetime.now(resolved_timezone())
    segment_tags = meal_pattern.get("weekday_dominant_tags", []) if local_now.weekday() < 5 else meal_pattern.get("weekend_dominant_tags", [])

    for like in preferences.get("likes", []):
        if _normalize_title(like) in haystack:
            score += 6

    for chip_id in ("high_protein", "soup", "light", "comfort", "filling", "rice_or_noodle"):
        if chip_id in candidate.support_tags and chip_id in _normalize_title(hypotheses_text):
            score += 5
        if chip_id in candidate.support_tags and chip_id in _normalize_title(signals_text):
            score += 3
        if chip_id in candidate.support_tags and any(token in _normalize_title(recent_text) for token in TOKEN_HINTS.get(chip_id, ())):
            score += 2
        if chip_id in candidate.support_tags and chip_id in meal_pattern.get("dominant_tags", []):
            score += 3
        if chip_id in candidate.support_tags and chip_id in segment_tags:
            score += 2

    if preferences.get("carb_need") == "high" and "rice_or_noodle" in candidate.support_tags:
        score += 4
    if preferences.get("dinner_style") == "high_protein" and "high_protein" in candidate.support_tags:
        score += 5
    if preferences.get("dinner_style") == "light" and "light" in candidate.support_tags:
        score += 5
    if request.meal_type == "dinner" and preferences.get("dinner_style") == "indulgent" and "comfort" in candidate.support_tags:
        score += 4

    store_memory = memory_packet.get("store_context_memory", [])
    for item in store_memory:
        if _normalize_title(item.get("food_name")) != _normalize_title(candidate.title):
            continue
        if candidate.store_name and _normalize_title(item.get("top_store_name")) == _normalize_title(candidate.store_name):
            score += 5
            if float(item.get("top_portion_ratio") or 1.0) >= 1.08 and candidate.kcal_high >= candidate.kcal_low + 40:
                score += 1
        elif not candidate.store_name:
            score += 2
    return min(score, 25.0)


def _context_fit(candidate: Candidate, *, request: EatFeedRequest, remaining_kcal: int) -> float:
    score = 0.0
    midpoint = (candidate.kcal_low + candidate.kcal_high) / 2 if candidate.kcal_high else candidate.kcal_low
    if midpoint <= remaining_kcal:
        score += 10
        score += max(0.0, 4 - abs(remaining_kcal - midpoint) / 120)
    elif midpoint <= remaining_kcal + 120:
        score += 4
    if request.meal_type and candidate.meal_types and request.meal_type in candidate.meal_types:
        score += 5
    if request.time_context == "now" and candidate.travel_minutes is not None and candidate.travel_minutes <= 12:
        score += 3
    if candidate.distance_meters is not None and candidate.distance_meters <= 800:
        score += 2
    if candidate.open_now is True:
        score += 2
    return min(score, 25.0)


def _familiarity_bonus(candidate: Candidate, *, recent_logs: list[MealLog]) -> float:
    score = min(5.0, math.log1p(max(candidate.usage_count, 0)) * 2.1)
    exact_matches = sum(1 for row in recent_logs[:14] if _titles_match(row.description_raw, candidate.title))
    return min(8.0, score + min(exact_matches, 3))


def _repeat_penalty(candidate: Candidate, *, recent_logs: list[MealLog], profile: RecommendationProfile) -> float:
    recent_names = [_normalize_title(row.description_raw) for row in recent_logs[:6]]
    penalty = 0.0
    candidate_name = _normalize_title(candidate.title)
    if recent_names[:3].count(candidate_name):
        penalty += 6.0
    if candidate.store_name and any(_normalize_title(row.description_raw).find(_normalize_title(candidate.store_name)) >= 0 for row in recent_logs[:2]):
        penalty += 4.0
    return penalty * (1.3 - profile.repeat_tolerance)


def _distance_penalty(candidate: Candidate, *, profile: RecommendationProfile) -> float:
    if candidate.travel_minutes is not None:
        return max(0.0, candidate.travel_minutes - 8) * 0.45 * profile.distance_sensitivity
    if candidate.distance_meters is not None:
        return max(0.0, candidate.distance_meters - 600) / 250 * 0.35 * profile.distance_sensitivity
    return 0.0


def _risk_penalty(candidate: Candidate) -> float:
    spread = max(candidate.kcal_high - candidate.kcal_low, 0)
    penalty = 0.0
    if spread > 260:
        penalty += 6.0
    elif spread > 180:
        penalty += 4.0
    if candidate.source_type in {"nearby_heuristic", "external_nearby_result"} and candidate.distance_meters is None and candidate.travel_minutes is None:
        penalty += 2.0
    if not candidate.reason_factors:
        penalty += 2.0
    return penalty


def _chip_bonus(candidate: Candidate, selected_chip_id: str | None) -> float:
    if not selected_chip_id:
        return 0.0
    if _candidate_supports_chip(candidate, selected_chip_id):
        if selected_chip_id in {"nearby", "quick_pickup"}:
            return 10.0
        if selected_chip_id in {"high_protein", "soup", "light", "comfort", "filling"}:
            return 8.0
        return 7.0
    return 0.0


def _enforce_memory_first_top_pick(ranked: list[Candidate], *, profile: RecommendationProfile) -> list[Candidate]:
    if len(ranked) < 2:
        return ranked
    best = ranked[0]
    if best.source_type not in {"nearby_heuristic", "external_nearby_result"}:
        return ranked
    best_memory = next((item for item in ranked[1:] if item.source_type in {"golden_order", "favorite_food", "favorite_store"}), None)
    if best_memory and best.final_score < best_memory.final_score + 5 - (profile.nearby_exploration_preference * 2):
        return [best_memory, best, *[item for item in ranked[1:] if item.candidate_id != best_memory.candidate_id]]
    return ranked


def _build_exploration_sections(candidates: list[Candidate], *, request: EatFeedRequest) -> list[EatFeedSectionResponse]:
    familiar = [_candidate_to_response(item) for item in candidates if item.source_type in {"golden_order", "favorite_food", "favorite_store"}][:4]
    nearby = [_candidate_to_response(item) for item in candidates if item.source_type in {"nearby_heuristic", "external_nearby_result"}][:4]
    more = [_candidate_to_response(item) for item in candidates][:6] if request.explore_mode else []
    sections: list[EatFeedSectionResponse] = []
    if familiar:
        sections.append(EatFeedSectionResponse(key="familiar", title="熟悉選項", items=familiar))
    if nearby:
        sections.append(EatFeedSectionResponse(key="nearby", title="附近可行", items=nearby))
    if more:
        sections.append(EatFeedSectionResponse(key="all", title="更多結果", items=more))
    return sections


def _candidate_to_response(candidate: Candidate) -> EatFeedCandidateResponse:
    return EatFeedCandidateResponse(
        candidate_id=candidate.candidate_id,
        title=candidate.title,
        store_name=candidate.store_name,
        meal_types=candidate.meal_types,
        kcal_low=int(candidate.kcal_low),
        kcal_high=int(candidate.kcal_high),
        distance_meters=candidate.distance_meters,
        travel_minutes=candidate.travel_minutes,
        open_now=candidate.open_now,
        source_type=candidate.source_type,
        reason_factors=candidate.reason_factors[:3],
        external_link=candidate.external_link,
    )


def _derive_support_tags(candidate: Candidate) -> set[str]:
    text = _normalize_title(" ".join(part for part in [candidate.title, candidate.store_name] if part))
    tags = {chip_id for chip_id, tokens in TOKEN_HINTS.items() if any(_normalize_title(token) in text for token in tokens)}
    if candidate.source_type in {"golden_order", "favorite_food", "favorite_store"}:
        tags.add("repeat_safe")
    if candidate.source_type in {"nearby_heuristic", "external_nearby_result"} or candidate.distance_meters is not None:
        tags.add("nearby")
    if candidate.travel_minutes is not None and candidate.travel_minutes <= 12:
        tags.add("quick_pickup")
    if candidate.kcal_high and candidate.kcal_high <= 450:
        tags.add("light")
    if candidate.kcal_low and candidate.kcal_low >= 560:
        tags.add("filling")
    return tags


def _candidate_supports_chip(candidate: Candidate, chip_id: str) -> bool:
    if chip_id == "repeat_safe":
        return candidate.source_type in {"golden_order", "favorite_food", "favorite_store"}
    if chip_id == "nearby":
        return candidate.source_type in {"nearby_heuristic", "external_nearby_result"} or candidate.distance_meters is not None
    return chip_id in candidate.support_tags


def _chip_passes_gate(chip_id: str, supported: int, total: int, *, request: EatFeedRequest, memory_packet: dict[str, Any]) -> bool:
    if supported <= 0:
        return False
    if supported >= total:
        if total <= 3 and chip_id in {"light", "quick_pickup", "repeat_safe", "high_protein"}:
            return True
        return False
    if total > 3 and supported < 2:
        return False
    dislikes = {_normalize_title(item) for item in memory_packet.get("preferences", {}).get("hard_dislikes", [])}
    if chip_id == "indulgent" and request.meal_type == "breakfast":
        return False
    if chip_id == "soup" and "cold_food" in dislikes:
        return False
    return True


def _smart_chip_score(
    chip_id: str,
    *,
    request: EatFeedRequest,
    memory_packet: dict[str, Any],
    recent_logs: list[MealLog],
    profile: RecommendationProfile,
) -> float:
    score = 0.0
    preferences = memory_packet.get("preferences", {})
    recent_text = " ".join(row.description_raw for row in recent_logs[:10])
    meal_pattern = (memory_packet.get("meal_acceptance_pattern", {}) or {}).get(request.meal_type or "", {})
    local_now = datetime.now(resolved_timezone())
    segment_tags = meal_pattern.get("weekday_dominant_tags", []) if local_now.weekday() < 5 else meal_pattern.get("weekend_dominant_tags", [])
    if request.meal_type == "breakfast":
        score += {"light": 8, "quick_pickup": 7, "repeat_safe": 5, "high_protein": 2}.get(chip_id, 0)
        score -= {"filling": 3, "rice_or_noodle": 2, "comfort": 2, "indulgent": 4}.get(chip_id, 0)
    elif request.meal_type == "lunch":
        score += {"high_protein": 6, "filling": 5, "nearby": 3, "rice_or_noodle": 4, "soup": 3}.get(chip_id, 0)
    elif request.meal_type == "dinner":
        score += {"comfort": 5, "soup": 4, "light": 3}.get(chip_id, 0)
    else:
        score += {"light": 4, "quick_pickup": 3, "indulgent": 2}.get(chip_id, 0)
    if chip_id == "nearby":
        score += profile.nearby_exploration_preference * 8
        if request.location_mode == "none":
            score -= 5
    if chip_id == "repeat_safe":
        score += (0.8 - profile.repeat_tolerance) * 10
    if chip_id == "high_protein" and preferences.get("dinner_style") == "high_protein":
        score += 6
    if chip_id == "light" and preferences.get("dinner_style") == "light":
        score += 6
    if chip_id == "rice_or_noodle" and preferences.get("carb_need") == "high":
        score += 5
    if chip_id in {"soup", "comfort", "high_protein", "rice_or_noodle"} and any(_normalize_title(token) in _normalize_title(recent_text) for token in TOKEN_HINTS.get(chip_id, ())):
        score += 3
    if chip_id in meal_pattern.get("dominant_tags", []):
        score += 3
    if chip_id in segment_tags:
        score += 2
    if chip_id == "light" and memory_packet.get("remaining_kcal", 0) <= 450:
        score += 5
    if chip_id in {"filling", "indulgent"} and memory_packet.get("remaining_kcal", 0) >= 700:
        score += 4
    return score


def _choose_chip_ids(
    shortlist: list[dict[str, Any]],
    *,
    request: EatFeedRequest,
    memory_packet: dict[str, Any],
    provider: Any | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Returns (selected_chip_ids, provider_usage)."""
    if len(shortlist) <= 3:
        return [item["id"] for item in shortlist], {}
    provider = provider or get_ai_provider()
    if not settings.ai_builder_token:
        return [item["id"] for item in shortlist[:3]], {}
    prompt = {
        "meal_type": request.meal_type,
        "time_context": request.time_context,
        "remaining_kcal": memory_packet.get("remaining_kcal"),
        "preferences": {
            "carb_need": memory_packet.get("preferences", {}).get("carb_need"),
            "dinner_style": memory_packet.get("preferences", {}).get("dinner_style"),
        },
        "recent_acceptance": [item.get("description", "") for item in memory_packet.get("recent_acceptance", [])[:5]],
        "store_context_memory": memory_packet.get("store_context_memory", [])[:4],
        "chips": shortlist,
    }
    parsed = complete_structured_sync(
        provider,
        system_prompt='Pick the 3 most useful session-only meal intent chips. Reply with JSON only: {"ids":[...]}',
        user_payload=prompt,
        max_tokens=120,
        temperature=0.1,
        model_hint="chat",
    )
    # Extract provider_usage before the parsed dict is consumed
    provider_usage = _extract_provider_usage(parsed)
    allowed = {item["id"] for item in shortlist}
    ids = [str(item) for item in parsed.get("ids", []) if str(item) in allowed]
    return ids or [item["id"] for item in shortlist[:3]], provider_usage


def _apply_llm_candidate_rerank(
    ranked: list[Candidate],
    *,
    provider: Any | None,
    request: EatFeedRequest,
    remaining_kcal: int,
    memory_packet: dict[str, Any],
    communication_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    if not ranked:
        return {"hero_reason": "", "policy_contract": {}, "provider_usage": {}}
    payload = rerank_candidates_sync(
        provider,
        task_label="eat_feed",
        meal_type=request.meal_type,
        remaining_kcal=remaining_kcal,
        memory_packet=memory_packet,
        communication_profile=communication_profile,
        candidates=[
            {
                "key": item.candidate_id,
                "name": item.title,
                "group": item.source_type,
                "kcal_low": item.kcal_low,
                "kcal_high": item.kcal_high,
                "store_name": item.store_name,
                "travel_minutes": item.travel_minutes,
                "distance_meters": item.distance_meters,
                "reason_factors": item.reason_factors,
                "support_tags": sorted(item.support_tags),
                "final_score": item.final_score,
            }
            for item in ranked[:10]
        ],
    )
    if payload["ordered_keys"]:
        by_key = {item.candidate_id: item for item in ranked}
        reordered = [by_key[key] for key in payload["ordered_keys"] if key in by_key]
        reordered.extend(item for item in ranked if item.candidate_id not in payload["ordered_keys"])
        ranked[:] = reordered
    for candidate in ranked:
        override = payload["reason_factors"].get(candidate.candidate_id)
        if override:
            candidate.reason_factors = override[:4]
    return {
        "hero_reason": payload["hero_reason"],
        "policy_contract": payload.get("policy_contract") or {},
        "provider_usage": payload.get("provider_usage") or {},
    }


def _merge_usage(*parts: object) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "request_count": 0,
        "estimated_cost_usd": 0.0,
        "model_names": [],
        "model_hints": [],
    }
    seen_models: set[str] = set()
    seen_hints: set[str] = set()
    last_non_null: dict[str, Any] = {}
    for part in parts:
        if not isinstance(part, dict):
            continue
        merged["prompt_tokens"] += int(part.get("prompt_tokens") or 0)
        merged["completion_tokens"] += int(part.get("completion_tokens") or 0)
        merged["total_tokens"] += int(part.get("total_tokens") or 0)
        merged["request_count"] += int(part.get("request_count") or 0)
        merged["estimated_cost_usd"] = round(float(merged["estimated_cost_usd"]) + float(part.get("estimated_cost_usd") or 0.0), 6)
        model_name = str(part.get("model_name") or "").strip()
        if model_name and model_name not in seen_models:
            seen_models.add(model_name)
            merged["model_names"].append(model_name)
        model_hint = str(part.get("model_hint") or "").strip()
        if model_hint and model_hint not in seen_hints:
            seen_hints.add(model_hint)
            merged["model_hints"].append(model_hint)
        for key in (
            "provider_name",
            "rate_limit_remaining_requests",
            "rate_limit_remaining_tokens",
            "rate_limit_reset_requests_s",
            "rate_limit_reset_tokens_s",
            "request_budget_per_hour",
            "token_budget_per_hour",
            "cost_budget_usd_per_day",
        ):
            if part.get(key) is not None:
                last_non_null[key] = part.get(key)
    if not merged["total_tokens"]:
        merged["total_tokens"] = merged["prompt_tokens"] + merged["completion_tokens"]
    merged.update(last_non_null)
    return merged


def _match_session_candidate(session: RecommendationSession, description_raw: str) -> dict[str, Any] | None:
    top = session.shown_top_pick or {}
    backups = list(session.shown_backup_picks or [])
    scores = list(session.shown_scores or [])
    if top and _titles_match(description_raw, top.get("title", "")):
        return {"event_type": "accepted_top_pick", "candidate": top}
    for item in backups:
        if _titles_match(description_raw, item.get("title", "")):
            return {"event_type": "accepted_backup_pick", "candidate": item}
    for item in scores:
        if _titles_match(description_raw, item.get("title", "")):
            event_type = "accepted_nearby_new" if item.get("source_type") in {"nearby_heuristic", "external_nearby_result"} else "accepted_backup_pick"
            return {"event_type": event_type, "candidate": item}
    return None


def _maybe_apply_distance_adjustment(profile: RecommendationProfile, candidate: dict[str, Any]) -> None:
    travel_minutes = candidate.get("travel_minutes")
    if travel_minutes is None:
        return
    if travel_minutes >= 18:
        profile.distance_sensitivity = _clamp(profile.distance_sensitivity - 0.04, 0.2, 0.9)
    elif travel_minutes <= 8:
        profile.distance_sensitivity = _clamp(profile.distance_sensitivity + 0.03, 0.2, 0.9)


def _apply_profile_adjustment(profile: RecommendationProfile, event_type: str) -> None:
    if event_type == "accepted_top_pick":
        profile.favorite_bias_strength = _clamp(profile.favorite_bias_strength + 0.03, 0.3, 0.85)
        profile.sample_size += 1
    elif event_type == "accepted_nearby_new":
        profile.nearby_exploration_preference = _clamp(profile.nearby_exploration_preference + 0.04, 0.1, 0.7)
        profile.sample_size += 1
    elif event_type == "accepted_backup_pick":
        profile.sample_size += 1
    elif event_type == "rejected_repeated_top_pick":
        profile.repeat_tolerance = _clamp(profile.repeat_tolerance - 0.03, 0.2, 0.8)
        profile.favorite_bias_strength = _clamp(profile.favorite_bias_strength - 0.02, 0.3, 0.85)
        profile.sample_size += 1


def _titles_match(left: str | None, right: str | None) -> bool:
    lhs = _normalize_title(left)
    rhs = _normalize_title(right)
    return bool(lhs and rhs and (lhs == rhs or lhs in rhs or rhs in lhs))


def _normalize_title(value: str | None) -> str:
    return "".join((value or "").strip().lower().split())


def _kcal_reason(kcal_low: int, kcal_high: int, remaining_kcal: int) -> str:
    if kcal_high <= remaining_kcal:
        return f"今天剩餘 {remaining_kcal} kcal 內就能吃"
    if kcal_low <= remaining_kcal + 120:
        return "稍微彈性一下也還在可接受範圍"
    return "熱量偏高，先放到查看更多會更合適"


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _top_store_profile(store_context: dict[str, Any]) -> dict[str, Any] | None:
    top_key = store_context.get("top_store_key")
    by_store = store_context.get("by_store") or {}
    if not top_key or not isinstance(by_store, dict):
        return None
    profile = by_store.get(top_key)
    return profile if isinstance(profile, dict) else None


def _store_context_reason(store_profile: dict[str, Any] | None) -> str:
    if not store_profile:
        return ""
    count = int(store_profile.get("count", 0))
    if count < 2:
        return ""
    ratio = float(store_profile.get("portion_ratio", 1.0) or 1.0)
    if ratio >= 1.08:
        return "這家店的份量通常比一般版本再大一點。"
    if ratio <= 0.92:
        return "這家店的份量通常比一般版本小一點。"
    return "這家店的份量波動不大，屬於穩定選項。"
