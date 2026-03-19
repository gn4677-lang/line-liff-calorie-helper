from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import MealDraft, MealLog, MemoryHypothesis, MemorySignal, Preference, ReportingBias, User, utcnow
from ..schemas import (
    MemoryHypothesisResponse,
    MemoryProfileResponse,
    MemorySignalResponse,
    OnboardingPreferencesRequest,
    OnboardingStateResponse,
    PreferenceCorrectionRequest,
    PreferenceResponse,
)


SOURCE_PRIORITY = {
    "model_hypothesis": 0,
    "behavior_inferred": 1,
    "user_stated": 2,
    "user_corrected": 3,
}

DISLIKE_LABELS = {
    "韓式": "korean",
    "炸物": "fried",
    "手搖 / 含糖飲料": "sugary_drink",
    "早餐店": "breakfast_shop",
    "沙拉 / 冷食": "cold_food",
    "便利商店": "convenience_store",
    "none": "none",
}

CANONICAL_ALIASES = {
    "cuisine_preference": {
        "韓式": "korean",
        "韓國": "korean",
        "韓國料理": "korean",
        "日式": "japanese",
        "日料": "japanese",
        "日本料理": "japanese",
        "超商": "convenience_store",
        "便利商店": "convenience_store",
        "便當": "bento",
        "早餐店": "breakfast_shop",
    },
    "taste_preference": {
        "重鹹": "salty",
        "鹹": "salty",
        "辣": "spicy",
        "炸": "fried",
        "湯": "soupy",
    },
    "meal_structure": {
        "飯": "carb_forward",
        "麵": "carb_forward",
        "吐司": "carb_forward",
        "雞胸": "high_protein",
        "高蛋白": "high_protein",
        "蛋白": "high_protein",
    },
}


def get_or_create_preferences(db: Session, user: User) -> Preference:
    preference = db.scalar(select(Preference).where(Preference.user_id == user.id))
    if preference:
        return preference

    preference = Preference(user_id=user.id)
    db.add(preference)
    db.commit()
    db.refresh(preference)
    return preference


def preference_to_response(preference: Preference) -> PreferenceResponse:
    return PreferenceResponse(
        likes=preference.likes or [],
        dislikes=preference.dislikes or [],
        hard_dislikes=preference.hard_dislikes or [],
        breakfast_habit=preference.breakfast_habit,
        carb_need=preference.carb_need,
        dinner_style=preference.dinner_style,
        compensation_style=preference.compensation_style,
        notes=preference.notes or "",
    )


def build_onboarding_state(user: User, preference: Preference) -> OnboardingStateResponse:
    completed = bool(user.onboarding_completed_at)
    skipped = bool(user.onboarding_skipped_at and not completed)
    return OnboardingStateResponse(
        should_show=not completed,
        completed=completed,
        skipped=skipped,
        version=user.onboarding_version,
        preferences=preference_to_response(preference),
    )


def apply_onboarding_preferences(db: Session, user: User, request: OnboardingPreferencesRequest) -> Preference:
    preference = get_or_create_preferences(db, user)
    preference.breakfast_habit = request.breakfast_habit
    preference.carb_need = request.carb_need
    preference.must_have_carbs = request.carb_need == "high"
    preference.dinner_style = request.dinner_style
    preference.compensation_style = request.compensation_style
    preference.hard_dislikes = [] if "none" in request.hard_dislikes else request.hard_dislikes

    user.onboarding_completed_at = utcnow()
    user.onboarding_skipped_at = None

    db.add(preference)
    db.add(user)
    db.commit()
    db.refresh(preference)

    _seed_user_stated_signals(db, user, preference, source="user_stated")
    synthesize_hypotheses(db, user, force_user_stated=True)
    return preference


def mark_onboarding_skipped(db: Session, user: User) -> User:
    user.onboarding_skipped_at = utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def apply_preference_correction(db: Session, user: User, request: PreferenceCorrectionRequest) -> Preference:
    preference = get_or_create_preferences(db, user)
    updates = request.model_dump(exclude_none=True)
    correction_note = updates.pop("correction_note", None)

    changed_fields: list[tuple[str, str]] = []
    for field, value in updates.items():
        setattr(preference, field, value)
        if isinstance(value, list):
            changed_fields.append((field, ",".join(value)))
        else:
            changed_fields.append((field, str(value)))

    if correction_note:
        note = f"[correction] {correction_note}"
        preference.notes = f"{preference.notes}\n{note}".strip()

    db.add(preference)
    db.commit()
    db.refresh(preference)

    _seed_user_stated_signals(db, user, preference, source="user_corrected")
    _apply_counter_evidence_for_corrections(db, user, changed_fields)
    synthesize_hypotheses(db, user, force_user_stated=True)
    return preference


def detect_chat_correction(text: str) -> PreferenceCorrectionRequest | None:
    normalized = text.strip()
    correction: dict[str, Any] = {}

    if "不喜歡韓式" in normalized or "不要再推韓式" in normalized:
        correction["hard_dislikes"] = ["韓式"]
    elif "不喜歡炸物" in normalized or "不要再推炸物" in normalized:
        correction["hard_dislikes"] = ["炸物"]
    elif "最近開始吃早餐" in normalized or "我有吃早餐" in normalized:
        correction["breakfast_habit"] = "regular"
    elif "我不吃早餐" in normalized or "我通常不吃早餐" in normalized:
        correction["breakfast_habit"] = "rare"
    elif "我需要主食" in normalized or "我每餐都要飯" in normalized:
        correction["carb_need"] = "high"
    elif "我不用主食" in normalized or "我不太需要主食" in normalized:
        correction["carb_need"] = "low"
    elif "晚餐想吃輕一點" in normalized or "晚餐想吃清淡" in normalized:
        correction["dinner_style"] = "light"
    elif "晚餐想吃爽一點" in normalized or "晚餐要吃爽" in normalized:
        correction["dinner_style"] = "indulgent"
    elif "晚餐高蛋白" in normalized:
        correction["dinner_style"] = "high_protein"

    if not correction:
        return None

    correction["correction_note"] = normalized
    return PreferenceCorrectionRequest(**correction)


def update_memory_after_log(db: Session, user: User, log: MealLog) -> None:
    for signal in _extract_behavioral_signals(log):
        _upsert_signal(
            db,
            user_id=user.id,
            pattern_type=signal["pattern_type"],
            dimension=signal["dimension"],
            canonical_label=signal["canonical_label"],
            raw_label=signal["raw_label"],
            value=signal.get("value", signal["canonical_label"]),
            source="behavior_inferred",
            confidence=signal.get("confidence", 0.65),
            sample_log_id=log.id,
            metadata=signal.get("metadata"),
        )
    synthesize_hypotheses(db, user)


def build_memory_profile(db: Session, user: User) -> MemoryProfileResponse:
    preference = get_or_create_preferences(db, user)
    bias = db.scalar(select(ReportingBias).where(ReportingBias.user_id == user.id))

    stable_signals = list(
        db.scalars(
            select(MemorySignal)
            .where(MemorySignal.user_id == user.id, MemorySignal.status.in_(("stable", "candidate")))
            .order_by(desc(MemorySignal.evidence_score), desc(MemorySignal.last_seen_at))
            .limit(12)
        )
    )
    active_hypotheses = list(
        db.scalars(
            select(MemoryHypothesis)
            .where(MemoryHypothesis.user_id == user.id, MemoryHypothesis.status.in_(("active", "tentative")))
            .order_by(desc(MemoryHypothesis.confidence), desc(MemoryHypothesis.last_confirmed_at))
            .limit(8)
        )
    )

    return MemoryProfileResponse(
        onboarding=build_onboarding_state(user, preference),
        reporting_bias={
            "underreport_score": round(bias.underreport_score if bias else 0.0, 3),
            "overreport_score": round(bias.overreport_score if bias else 0.0, 3),
            "vagueness_score": round(bias.vagueness_score if bias else 0.0, 3),
            "missing_detail_score": round(bias.missing_detail_score if bias else 0.0, 3),
            "log_confidence_score": round(bias.log_confidence_score if bias else 1.0, 3),
        },
        stable_signals=[_signal_to_response(item) for item in stable_signals],
        active_hypotheses=[_hypothesis_to_response(item) for item in active_hypotheses],
        intake_packet=build_intake_memory_packet(db, user),
        recommendation_packet=build_recommendation_memory_packet(db, user, meal_type=None, remaining_kcal=None),
        planning_packet=build_planning_memory_packet(db, user),
    )


def build_intake_memory_packet(db: Session, user: User, draft: MealDraft | None = None) -> dict[str, Any]:
    preference = get_or_create_preferences(db, user)
    signals = list(
        db.scalars(
            select(MemorySignal)
            .where(MemorySignal.user_id == user.id)
            .order_by(desc(MemorySignal.evidence_score), desc(MemorySignal.last_seen_at))
            .limit(5)
        )
    )
    recent_logs = list(
        db.scalars(
            select(MealLog)
            .where(MealLog.user_id == user.id)
            .order_by(desc(MealLog.event_at), desc(MealLog.created_at))
            .limit(3)
        )
    )

    return {
        "meal_session_id": draft.meal_session_id if draft else None,
        "user_stated_constraints": {
            "breakfast_habit": preference.breakfast_habit,
            "carb_need": preference.carb_need,
            "dinner_style": preference.dinner_style,
            "hard_dislikes": preference.hard_dislikes,
        },
        "relevant_signals": [_signal_to_packet(item) for item in signals],
        "recent_evidence": [
            {
                "log_id": log.id,
                "meal_type": log.meal_type,
                "parsed_items": log.parsed_items[:3],
                "event_at": log.event_at.isoformat() if log.event_at else None,
            }
            for log in recent_logs
        ],
    }


def build_recommendation_memory_packet(
    db: Session,
    user: User,
    meal_type: str | None,
    remaining_kcal: int | None,
) -> dict[str, Any]:
    preference = get_or_create_preferences(db, user)
    hypotheses = list(
        db.scalars(
            select(MemoryHypothesis)
            .where(MemoryHypothesis.user_id == user.id, MemoryHypothesis.status.in_(("active", "tentative")))
            .order_by(desc(MemoryHypothesis.confidence), desc(MemoryHypothesis.last_confirmed_at))
            .limit(6)
        )
    )
    signals = list(
        db.scalars(
            select(MemorySignal)
            .where(MemorySignal.user_id == user.id, MemorySignal.status.in_(("stable", "candidate")))
            .order_by(desc(MemorySignal.evidence_score), desc(MemorySignal.last_seen_at))
            .limit(8)
        )
    )

    return {
        "meal_type": meal_type,
        "remaining_kcal": remaining_kcal,
        "preferences": preference_to_response(preference).model_dump(),
        "active_hypotheses": [_hypothesis_to_packet(item) for item in hypotheses],
        "relevant_signals": [_signal_to_packet(item) for item in signals],
    }


def build_planning_memory_packet(db: Session, user: User) -> dict[str, Any]:
    preference = get_or_create_preferences(db, user)
    cutoff = utcnow() - timedelta(days=21)
    logs = list(
        db.scalars(
            select(MealLog)
            .where(MealLog.user_id == user.id, MealLog.created_at >= cutoff)
            .order_by(desc(MealLog.created_at))
        )
    )
    total_kcal = sum(log.kcal_estimate for log in logs)
    hypotheses = list(
        db.scalars(
            select(MemoryHypothesis)
            .where(MemoryHypothesis.user_id == user.id, MemoryHypothesis.status.in_(("active", "tentative")))
            .order_by(desc(MemoryHypothesis.confidence), desc(MemoryHypothesis.last_confirmed_at))
            .limit(6)
        )
    )

    return {
        "preferences": preference_to_response(preference).model_dump(),
        "recent_log_count": len(logs),
        "recent_average_kcal": round(total_kcal / len(logs)) if logs else None,
        "active_hypotheses": [_hypothesis_to_packet(item) for item in hypotheses],
    }


def synthesize_hypotheses(db: Session, user: User, *, force_user_stated: bool = False) -> None:
    preference = get_or_create_preferences(db, user)
    signals = list(db.scalars(select(MemorySignal).where(MemorySignal.user_id == user.id)))
    signal_map = {signal.canonical_label: signal for signal in signals}

    recent_logs = list(
        db.scalars(
            select(MealLog)
            .where(MealLog.user_id == user.id)
            .order_by(desc(MealLog.event_at), desc(MealLog.created_at))
            .limit(90)
        )
    )

    by_day: dict[str, set[str]] = defaultdict(set)
    for log in recent_logs:
        key = str(log.event_at.date()) if log.event_at else str(log.date)
        by_day[key].add(log.meal_type)

    active_labels: set[str] = set()

    if preference.breakfast_habit == "rare":
        _upsert_hypothesis(
            db,
            user.id,
            "meal_timing",
            "rarely_eats_breakfast",
            "Breakfast is usually skipped unless the user explicitly says otherwise.",
            "user_stated",
            0.98,
            [],
        )
        active_labels.add("rarely_eats_breakfast")
    elif preference.breakfast_habit == "regular":
        _stale_hypothesis(db, user.id, "rarely_eats_breakfast")

    if preference.carb_need == "high":
        _upsert_hypothesis(
            db,
            user.id,
            "meal_structure",
            "needs_carbs",
            "Meals usually work better when they include a carb source.",
            "user_stated",
            0.97,
            [],
        )
        active_labels.add("needs_carbs")
    elif preference.carb_need == "low":
        _upsert_hypothesis(
            db,
            user.id,
            "meal_structure",
            "low_carb_ok",
            "Meals can work without a clear carb source.",
            "user_stated",
            0.97,
            [],
        )
        active_labels.add("low_carb_ok")

    for raw in preference.hard_dislikes:
        canonical = DISLIKE_LABELS.get(raw, raw)
        if canonical == "none":
            continue
        _upsert_hypothesis(
            db,
            user.id,
            "cuisine_preference",
            f"dislikes_{canonical}",
            f"Avoid recommending {raw} unless the user explicitly asks for it.",
            "user_stated",
            0.98,
            [],
        )
        active_labels.add(f"dislikes_{canonical}")

    if not force_user_stated and len(by_day) >= 5:
        breakfast_presence = sum(1 for meals in by_day.values() if "breakfast" in meals)
        ratio = breakfast_presence / len(by_day)
        if ratio <= 0.2:
            _upsert_hypothesis(
                db,
                user.id,
                "meal_timing",
                "rarely_eats_breakfast",
                "Recent logs suggest breakfast is often skipped.",
                "behavior_inferred",
                0.72 if len(by_day) < 10 else 0.84,
                [],
                status="tentative" if len(by_day) < 10 else "active",
            )
            active_labels.add("rarely_eats_breakfast")

    for canonical_label, hypothesis_label, statement in [
        ("salty", "prefers_salty_food", "Recent logs suggest stronger salty flavors are often accepted."),
        ("korean", "likes_korean_food", "Korean-style meals appear repeatedly in recent logs."),
    ]:
        signal = signal_map.get(canonical_label)
        if not signal:
            continue
        net_score = signal.evidence_score - signal.counter_evidence_score
        if net_score < 2.5:
            continue
        _upsert_hypothesis(
            db,
            user.id,
            signal.dimension,
            hypothesis_label,
            statement,
            signal.source,
            min(0.92, 0.55 + signal.evidence_score / 10),
            [signal.id],
            status="tentative" if signal.evidence_score < 4 else "active",
        )
        active_labels.add(hypothesis_label)

    existing = list(db.scalars(select(MemoryHypothesis).where(MemoryHypothesis.user_id == user.id)))
    for hypothesis in existing:
        if hypothesis.label not in active_labels and hypothesis.source != "user_corrected":
            if hypothesis.status != "stale":
                hypothesis.status = "stale"
                db.add(hypothesis)
    db.commit()


def build_explainability_factors(db: Session, user: User, *, meal_type: str | None = None) -> list[str]:
    preference = get_or_create_preferences(db, user)
    factors: list[str] = []

    if preference.dinner_style == "high_protein" and meal_type in {None, "dinner"}:
        factors.append("晚餐你通常比較接受高蛋白選項。")
    if preference.breakfast_habit == "rare" and meal_type == "breakfast":
        factors.append("最近早餐紀錄偏少，所以這次不會優先推早餐型選項。")
    if preference.carb_need == "high":
        factors.append("你通常需要主食，這次會保留澱粉型選項。")
    if preference.hard_dislikes:
        factors.append(f"這次先避開你明確排斥的類型：{', '.join(preference.hard_dislikes)}。")

    hypotheses = list(
        db.scalars(
            select(MemoryHypothesis)
            .where(MemoryHypothesis.user_id == user.id, MemoryHypothesis.status.in_(("active", "tentative")))
            .order_by(desc(MemoryHypothesis.confidence), desc(MemoryHypothesis.last_confirmed_at))
            .limit(4)
        )
    )
    for item in hypotheses:
        if item.label == "prefers_salty_food":
            factors.append("近期紀錄顯示你比較能接受口味重一點的選項。")
        elif item.label == "rarely_eats_breakfast" and meal_type == "breakfast":
            factors.append("最近看起來你不常吃早餐，所以早餐推薦會更保守。")
    return factors[:4]


def _seed_user_stated_signals(db: Session, user: User, preference: Preference, *, source: str) -> None:
    if preference.breakfast_habit and preference.breakfast_habit != "unknown":
        _upsert_signal(
            db,
            user_id=user.id,
            pattern_type="onboarding_preference",
            dimension="meal_timing",
            canonical_label=f"breakfast_habit:{preference.breakfast_habit}",
            raw_label=preference.breakfast_habit,
            value=preference.breakfast_habit,
            source=source,
            confidence=0.98,
        )
    if preference.carb_need:
        _upsert_signal(
            db,
            user_id=user.id,
            pattern_type="onboarding_preference",
            dimension="meal_structure",
            canonical_label=f"carb_need:{preference.carb_need}",
            raw_label=preference.carb_need,
            value=preference.carb_need,
            source=source,
            confidence=0.98,
        )
    if preference.dinner_style:
        _upsert_signal(
            db,
            user_id=user.id,
            pattern_type="onboarding_preference",
            dimension="meal_structure",
            canonical_label=f"dinner_style:{preference.dinner_style}",
            raw_label=preference.dinner_style,
            value=preference.dinner_style,
            source=source,
            confidence=0.98,
        )
    if preference.compensation_style:
        _upsert_signal(
            db,
            user_id=user.id,
            pattern_type="onboarding_preference",
            dimension="context_behavior",
            canonical_label=f"compensation_style:{preference.compensation_style}",
            raw_label=preference.compensation_style,
            value=preference.compensation_style,
            source=source,
            confidence=0.98,
        )
    for raw in preference.hard_dislikes:
        canonical = DISLIKE_LABELS.get(raw, raw)
        if canonical == "none":
            continue
        _upsert_signal(
            db,
            user_id=user.id,
            pattern_type="hard_dislike",
            dimension="cuisine_preference",
            canonical_label=canonical,
            raw_label=raw,
            value=raw,
            source=source,
            confidence=0.99,
        )


def _apply_counter_evidence_for_corrections(db: Session, user: User, changed_fields: list[tuple[str, str]]) -> None:
    active_hypotheses = list(
        db.scalars(
            select(MemoryHypothesis)
            .where(MemoryHypothesis.user_id == user.id, MemoryHypothesis.status != "stale")
        )
    )

    for field, value in changed_fields:
        if field == "hard_dislikes":
            continue
        for hypothesis in active_hypotheses:
            if field == "breakfast_habit" and hypothesis.label == "rarely_eats_breakfast" and value == "regular":
                hypothesis.counter_evidence_count += 1
                hypothesis.status = "stale"
                db.add(hypothesis)
            if field == "carb_need" and hypothesis.label == "needs_carbs" and value == "low":
                hypothesis.counter_evidence_count += 1
                hypothesis.status = "stale"
                db.add(hypothesis)
    db.commit()


def _extract_behavioral_signals(log: MealLog) -> list[dict[str, Any]]:
    raw_text = f"{log.description_raw} {' '.join(item.get('name', '') for item in log.parsed_items or [])}".strip()
    signals: list[dict[str, Any]] = []

    for item in log.parsed_items or []:
        name = item.get("name")
        if name:
            signals.append(
                {
                    "pattern_type": "food_repeat",
                    "dimension": "food_repeat",
                    "canonical_label": name.lower(),
                    "raw_label": name,
                    "value": name,
                    "confidence": 0.7,
                }
            )

    for dimension, aliases in CANONICAL_ALIASES.items():
        for raw_label, canonical in aliases.items():
            if raw_label in raw_text:
                signals.append(
                    {
                        "pattern_type": dimension,
                        "dimension": dimension,
                        "canonical_label": canonical,
                        "raw_label": raw_label,
                        "value": raw_label,
                        "confidence": 0.62,
                    }
                )

    signals.append(
        {
            "pattern_type": "meal_timing",
            "dimension": "meal_timing",
            "canonical_label": f"meal_type:{log.meal_type}",
            "raw_label": log.meal_type,
            "value": log.meal_type,
            "confidence": 0.55,
        }
    )
    return signals


def _upsert_signal(
    db: Session,
    *,
    user_id: int,
    pattern_type: str,
    dimension: str,
    canonical_label: str,
    raw_label: str,
    value: str,
    source: str,
    confidence: float,
    sample_log_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    counter: bool = False,
) -> MemorySignal:
    now = utcnow()
    signal = db.scalar(
        select(MemorySignal).where(
            MemorySignal.user_id == user_id,
            MemorySignal.pattern_type == pattern_type,
            MemorySignal.canonical_label == canonical_label,
        )
    )

    if not signal:
        signal = MemorySignal(
            user_id=user_id,
            pattern_type=pattern_type,
            dimension=dimension,
            canonical_label=canonical_label,
            raw_labels=[],
            value=value,
            source=source,
            confidence=confidence,
            first_seen_at=now,
            last_seen_at=now,
            sample_log_ids=[],
            status="candidate",
            extra=metadata or {},
        )
        db.add(signal)
        db.flush()

    if SOURCE_PRIORITY[source] >= SOURCE_PRIORITY.get(signal.source, 0):
        signal.source = source
    signal.confidence = max(signal.confidence, confidence)
    signal.raw_labels = sorted({*(signal.raw_labels or []), raw_label})
    signal.value = value
    signal.evidence_score = _decay(signal.evidence_score, signal.last_seen_at, now)
    signal.counter_evidence_score = _decay(signal.counter_evidence_score, signal.last_seen_at, now)
    signal.last_seen_at = now

    if sample_log_id and sample_log_id not in (signal.sample_log_ids or []):
        signal.sample_log_ids = [*(signal.sample_log_ids or [])[-4:], sample_log_id]

    if counter:
        signal.counter_evidence_count += 1
        signal.counter_evidence_score += 1.0
    else:
        signal.evidence_count += 1
        signal.evidence_score += 1.0

    signal.status = _signal_status(signal.evidence_score, signal.counter_evidence_score)
    if metadata:
        signal.extra = {**(signal.extra or {}), **metadata}
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal


def _upsert_hypothesis(
    db: Session,
    user_id: int,
    dimension: str,
    label: str,
    statement: str,
    source: str,
    confidence: float,
    supporting_signal_ids: list[int],
    *,
    status: str = "active",
) -> MemoryHypothesis:
    now = utcnow()
    hypothesis = db.scalar(
        select(MemoryHypothesis).where(MemoryHypothesis.user_id == user_id, MemoryHypothesis.label == label)
    )

    if not hypothesis:
        hypothesis = MemoryHypothesis(
            user_id=user_id,
            dimension=dimension,
            label=label,
            statement=statement,
            source=source,
            confidence=confidence,
            supporting_signal_ids=supporting_signal_ids,
            evidence_count=max(1, len(supporting_signal_ids)),
            last_confirmed_at=now,
            status=status,
        )
        db.add(hypothesis)
    else:
        if SOURCE_PRIORITY[source] >= SOURCE_PRIORITY.get(hypothesis.source, 0):
            hypothesis.source = source
        hypothesis.dimension = dimension
        hypothesis.statement = statement
        hypothesis.confidence = max(hypothesis.confidence, confidence)
        hypothesis.supporting_signal_ids = supporting_signal_ids or hypothesis.supporting_signal_ids
        hypothesis.evidence_count = max(hypothesis.evidence_count, len(supporting_signal_ids) or 1)
        hypothesis.last_confirmed_at = now
        hypothesis.status = status
        db.add(hypothesis)

    db.commit()
    db.refresh(hypothesis)
    return hypothesis


def _stale_hypothesis(db: Session, user_id: int, label: str) -> None:
    hypothesis = db.scalar(
        select(MemoryHypothesis).where(MemoryHypothesis.user_id == user_id, MemoryHypothesis.label == label)
    )
    if not hypothesis:
        return
    hypothesis.status = "stale"
    hypothesis.counter_evidence_count += 1
    db.add(hypothesis)
    db.commit()


def _decay(score: float, last_seen_at: datetime | None, now: datetime, *, half_life_days: int = 30) -> float:
    if not last_seen_at:
        return score
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    elapsed_days = max((now - last_seen_at).total_seconds() / 86400, 0)
    return score * math.pow(0.5, elapsed_days / half_life_days)


def _signal_status(evidence_score: float, counter_evidence_score: float) -> str:
    net = evidence_score - counter_evidence_score
    if net >= 4:
        return "stable"
    if net >= 1:
        return "candidate"
    if counter_evidence_score > evidence_score:
        return "decaying"
    return "candidate"


def _signal_to_packet(signal: MemorySignal) -> dict[str, Any]:
    return {
        "pattern_type": signal.pattern_type,
        "dimension": signal.dimension,
        "canonical_label": signal.canonical_label,
        "source": signal.source,
        "confidence": signal.confidence,
        "status": signal.status,
    }


def _hypothesis_to_packet(hypothesis: MemoryHypothesis) -> dict[str, Any]:
    return {
        "dimension": hypothesis.dimension,
        "label": hypothesis.label,
        "confidence": hypothesis.confidence,
        "status": hypothesis.status,
    }


def _signal_to_response(signal: MemorySignal) -> MemorySignalResponse:
    return MemorySignalResponse(
        id=signal.id,
        pattern_type=signal.pattern_type,
        dimension=signal.dimension,
        canonical_label=signal.canonical_label,
        source=signal.source,
        confidence=signal.confidence,
        evidence_count=signal.evidence_count,
        counter_evidence_count=signal.counter_evidence_count,
        evidence_score=round(signal.evidence_score, 3),
        counter_evidence_score=round(signal.counter_evidence_score, 3),
        status=signal.status,
        sample_log_ids=signal.sample_log_ids or [],
    )


def _hypothesis_to_response(hypothesis: MemoryHypothesis) -> MemoryHypothesisResponse:
    return MemoryHypothesisResponse(
        id=hypothesis.id,
        dimension=hypothesis.dimension,
        label=hypothesis.label,
        statement=hypothesis.statement,
        source=hypothesis.source,
        confidence=hypothesis.confidence,
        evidence_count=hypothesis.evidence_count,
        counter_evidence_count=hypothesis.counter_evidence_count,
        status=hypothesis.status,
        supporting_signal_ids=hypothesis.supporting_signal_ids or [],
    )
