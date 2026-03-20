from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import MealLog, ReportingBias, User
from ..providers.base import EstimateResult


HIGH_IMPACT_SLOTS = {
    "main_items",
    "portion",
    "rice_portion",
    "high_calorie_items",
    "fried_or_sauce",
    "sharing_ratio",
    "leftover_ratio",
    "drink",
}
MEDIUM_IMPACT_SLOTS = {"secondary_sides", "dessert_presence", "soup"}

QUESTION_TEMPLATES = {
    "portion": "飯或主食大概吃多少？如果不好說，也可以回我半碗 / 一碗 / 比便當白飯少。",
    "rice_portion": "飯大概吃多少？如果不好說，也可以回我半碗 / 一碗 / 比便當白飯少。",
    "main_items": "這餐主要吃了哪些東西？主菜和主食各是什麼？",
    "high_calorie_items": "這餐有炸物、甜點、濃醬或含糖飲料嗎？",
    "fried_or_sauce": "炸物或醬料大概多嗎？如果不好說，也可以直接回少 / 普通 / 偏多。",
    "sharing_ratio": "這份是你自己吃，還是有分人？如果有分，大概你吃少一點 / 一半 / 比較多？",
    "leftover_ratio": "哪些有吃完，哪些沒吃完？你也可以直接說大概吃幾成。",
    "drink": "這餐的飲料有喝完嗎？大概半杯還是一整杯？",
}

COMPARISON_OPTIONS = [
    "半碗",
    "一碗",
    "比便當白飯少",
    "比便當白飯多",
    "一個手掌大小",
    "跟上次差不多",
]


@dataclass
class ConfirmationDecision:
    confirmation_mode: str
    estimation_confidence: float
    confirmation_calibration: float
    primary_uncertainties: list[str]
    clarification_kind: str | None
    answer_mode: str | None
    answer_options: list[str]
    followup_question: str | None
    stop_reason: str | None
    needs_confirmation: bool


def get_question_budget(mode: str) -> int:
    return {"quick": 1, "standard": 2, "fine": 4}.get(mode, 2)


def calculate_estimation_confidence(estimate: EstimateResult) -> float:
    slots = estimate.evidence_slots or {}
    source_mode = str(slots.get("source_mode") or "text")
    base_by_source = {
        "favorite": 0.82,
        "known_food": 0.82,
        "text": 0.58,
        "voice": 0.50,
        "audio": 0.50,
        "video": 0.56,
        "image": 0.42,
        "single-photo": 0.42,
        "before-after-photo": 0.55,
    }
    confidence = base_by_source.get(source_mode, 0.52)

    if slots.get("identified_items"):
        confidence += 0.18
    if slots.get("portion_signal"):
        confidence += 0.20
    if slots.get("high_calorie_modifiers"):
        confidence += 0.12
    if slots.get("leftover_signal") or slots.get("sharing_signal"):
        confidence += 0.12
    if slots.get("drink_or_dessert_presence"):
        confidence += 0.08
    if estimate.parsed_items:
        confidence += 0.05

    penalties = 0.0
    penalties += 0.08 * sum(1 for slot in estimate.missing_slots if slot in HIGH_IMPACT_SLOTS)
    penalties += 0.04 * len(estimate.ambiguity_flags or [])
    if source_mode in {"image", "single-photo"} and not slots.get("identified_items"):
        penalties += 0.08

    confidence -= penalties
    return max(0.15, min(round(confidence, 2), 0.95))


def calculate_confirmation_calibration(
    db: Session,
    user: User,
    *,
    target_date: date,
) -> float:
    window_start = target_date - timedelta(days=6)
    logs = list(
        db.scalars(
            select(MealLog)
            .where(MealLog.user_id == user.id, MealLog.date >= window_start, MealLog.date <= target_date)
            .order_by(desc(MealLog.date), desc(MealLog.created_at))
        )
    )
    bias = db.scalar(select(ReportingBias).where(ReportingBias.user_id == user.id))
    correction_count = sum(1 for log in logs if bool((log.memory_metadata or {}).get("edited_after_confirm")))
    correction_rate = correction_count / max(len(logs), 1)
    completeness = sum(1 for log in logs if not (log.memory_metadata or {}).get("uncertainty_factors")) / max(len(logs), 1)

    calibration = 1.0
    if bias:
        calibration += min(0.18, bias.vagueness_score * 0.2)
        calibration += min(0.12, bias.missing_detail_score * 0.15)
    calibration += min(0.18, correction_rate * 0.4)
    calibration -= min(0.12, completeness * 0.1)

    weekly_status = calculate_weekly_drift_status(db, user, target_date)
    if weekly_status == "meaningfully_over":
        calibration += 0.08
    elif weekly_status == "slightly_over":
        calibration += 0.03

    return max(0.85, min(round(calibration, 2), 1.35))


def decide_confirmation(
    db: Session,
    user: User,
    *,
    estimate: EstimateResult,
    mode: str,
    target_date: date,
    clarification_used: int,
    requested_force_confirm: bool = False,
) -> ConfirmationDecision:
    estimation_confidence = calculate_estimation_confidence(estimate)
    confirmation_calibration = calculate_confirmation_calibration(db, user, target_date=target_date)
    adjusted_gate = 0.78 + max(0.0, confirmation_calibration - 1.0) * 0.12
    budget = get_question_budget(mode)
    primary_uncertainties = build_primary_uncertainties(estimate.missing_slots)
    high_impact_missing = [slot for slot in estimate.missing_slots if slot in HIGH_IMPACT_SLOTS]
    source_mode = str((estimate.evidence_slots or {}).get("source_mode") or "").lower()

    if requested_force_confirm:
        return ConfirmationDecision(
            confirmation_mode="needs_confirmation",
            estimation_confidence=estimation_confidence,
            confirmation_calibration=confirmation_calibration,
            primary_uncertainties=primary_uncertainties,
            clarification_kind=None,
            answer_mode=None,
            answer_options=[],
            followup_question=None,
            stop_reason="force_confirm_requested",
            needs_confirmation=True,
        )

    if estimation_confidence >= adjusted_gate and not high_impact_missing:
        return ConfirmationDecision(
            confirmation_mode="auto_recordable",
            estimation_confidence=estimation_confidence,
            confirmation_calibration=confirmation_calibration,
            primary_uncertainties=primary_uncertainties,
            clarification_kind=None,
            answer_mode=None,
            answer_options=[],
            followup_question=None,
            stop_reason="resolved",
            needs_confirmation=False,
        )

    if source_mode in {"voice", "audio"} and estimate.confidence >= 0.82 and not high_impact_missing:
        return ConfirmationDecision(
            confirmation_mode="auto_recordable",
            estimation_confidence=estimation_confidence,
            confirmation_calibration=confirmation_calibration,
            primary_uncertainties=primary_uncertainties,
            clarification_kind=None,
            answer_mode=None,
            answer_options=[],
            followup_question=None,
            stop_reason="high_confidence_voice_shortcut",
            needs_confirmation=False,
        )

    if clarification_used >= budget:
        return ConfirmationDecision(
            confirmation_mode="needs_confirmation",
            estimation_confidence=estimation_confidence,
            confirmation_calibration=confirmation_calibration,
            primary_uncertainties=primary_uncertainties,
            clarification_kind=None,
            answer_mode=None,
            answer_options=[],
            followup_question="資訊還是不夠完整，我先用一般份量估這餐，你之後可以直接補一句我再改。",
            stop_reason="budget_exhausted",
            needs_confirmation=True,
        )

    slot = choose_next_question_slot(estimate.missing_slots)
    if not slot:
        return ConfirmationDecision(
            confirmation_mode="needs_confirmation",
            estimation_confidence=estimation_confidence,
            confirmation_calibration=confirmation_calibration,
            primary_uncertainties=primary_uncertainties,
            clarification_kind=None,
            answer_mode=None,
            answer_options=[],
            followup_question=None,
            stop_reason="resolved",
            needs_confirmation=True,
        )

    answer_mode = None
    answer_options: list[str] = []
    if slot in {"portion", "rice_portion"}:
        answer_mode = "chips_first_with_text_fallback"
        answer_options = build_portion_answer_options(db, user)

    return ConfirmationDecision(
        confirmation_mode="needs_clarification",
        estimation_confidence=estimation_confidence,
        confirmation_calibration=confirmation_calibration,
        primary_uncertainties=primary_uncertainties,
        clarification_kind=slot,
        answer_mode=answer_mode,
        answer_options=answer_options,
        followup_question=QUESTION_TEMPLATES.get(slot, estimate.followup_question),
        stop_reason=None,
        needs_confirmation=False,
    )


def build_primary_uncertainties(missing_slots: list[str]) -> list[str]:
    labels = {
        "main_items": "主食內容",
        "portion": "份量",
        "rice_portion": "飯量",
        "high_calorie_items": "高熱量項目",
        "fried_or_sauce": "炸物或醬料",
        "sharing_ratio": "分食比例",
        "leftover_ratio": "沒吃完比例",
        "drink": "飲料",
        "secondary_sides": "配菜",
        "dessert_presence": "甜點",
        "soup": "湯",
    }
    return [labels.get(slot, slot) for slot in missing_slots[:2]]


def choose_next_question_slot(missing_slots: list[str]) -> str | None:
    ordered = [
        "main_items",
        "portion",
        "rice_portion",
        "high_calorie_items",
        "fried_or_sauce",
        "sharing_ratio",
        "leftover_ratio",
        "drink",
        "secondary_sides",
        "dessert_presence",
        "soup",
    ]
    for slot in ordered:
        if slot in missing_slots:
            return slot
    return None


def build_portion_answer_options(db: Session, user: User) -> list[str]:
    options = list(COMPARISON_OPTIONS)
    recent_logs = list(
        db.scalars(
            select(MealLog)
            .where(MealLog.user_id == user.id)
            .order_by(desc(MealLog.event_at), desc(MealLog.created_at))
            .limit(8)
        )
    )
    for log in recent_logs:
        meta = log.memory_metadata or {}
        if bool(meta.get("force_confirmed")):
            continue
        description = log.description_raw.strip()
        if not description:
            continue
        options.append(f"跟「{description[:12]}」差不多")
        if len(options) >= 8:
            break
    options.append("我自己補一句")
    seen: set[str] = set()
    unique: list[str] = []
    for option in options:
        if option not in seen:
            unique.append(option)
            seen.add(option)
    return unique[:8]


def calculate_weekly_drift_status(db: Session, user: User, target_date: date) -> str:
    window_start = target_date - timedelta(days=6)
    logs = list(
        db.scalars(
            select(MealLog)
            .where(MealLog.user_id == user.id, MealLog.date >= window_start, MealLog.date <= target_date)
        )
    )
    weekly_target = user.daily_calorie_target * 7
    weekly_consumed = sum(log.kcal_estimate for log in logs)
    drift = weekly_consumed - weekly_target
    if drift > 900:
        return "meaningfully_over"
    if drift > 300:
        return "slightly_over"
    if drift < -900:
        return "meaningfully_under"
    return "on_track"
