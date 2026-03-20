from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from sqlalchemy.orm import Session

from ..models import User
from ..schemas import BodyGoalResponse, DaySummaryResponse
from .body_metrics import body_goal_to_response, get_or_create_body_goal
from .knowledge import KNOWLEDGE_DIR, KnowledgeResult, answer_nutrition_question, canonicalize, load_json_records
from .summary import build_day_summary


ACTIVITY_PACK_FILE = "activity_met_values_tw.json"
ENERGY_RULES_PATH = str(KNOWLEDGE_DIR / "energy_model_rules_tw.md")

REMAINING_HINTS = (
    "還剩",
    "還能吃",
    "剩餘熱量",
    "剩多少熱量",
    "remaining",
    "left today",
    "budget left",
)
RECOMMENDATION_HINTS = ("推薦", "吃什麼", "suggest", "recommend", "nearby", "附近")
TDEE_HINTS = ("tdee", "bmr", "rmr", "基礎代謝", "代謝", "總消耗", "總熱量消耗")
ACTIVITY_HINTS = (
    "運動",
    "消耗",
    "burn",
    "burned",
    "calories burned",
    "跳舞",
    "dance",
    "散步",
    "走路",
    "快走",
    "慢跑",
    "跑步",
    "jog",
    "run",
    "騎車",
    "cycling",
    "bike",
    "重訓",
    "重量訓練",
    "strength training",
    "weight training",
    "健身",
    "籃球",
    "足球",
    "housework",
    "打掃",
)
BURN_HINTS = ("消耗", "burn", "burned", "熱量", "卡路里", "kcal", "calorie", "calories")
QUESTION_HINTS = ("多少", "幾", "how much", "how many", "estimate", "估")
LIGHT_HINTS = ("輕鬆", "慢慢", "不累", "easy", "light", "social")
VIGOROUS_HINTS = ("爆汗", "很喘", "超喘", "激烈", "快", "hard", "intense", "vigorous", "performance", "cardio")
WEIGHT_PATTERN = re.compile(r"(?P<weight>\d{2,3}(?:\.\d+)?)\s*(?:kg|公斤)", re.IGNORECASE)


@dataclass(frozen=True)
class EnergyContext:
    summary: DaySummaryResponse
    body_goal: BodyGoalResponse
    latest_weight_kg: float | None


def build_energy_context(db: Session, user: User, *, target_date: date | None = None) -> EnergyContext:
    target = target_date or date.today()
    summary = build_day_summary(db, user, target)
    goal = get_or_create_body_goal(db, user)
    body_goal = body_goal_to_response(db, user, goal, target_date=target)
    latest_weight = body_goal.latest_weight if body_goal.latest_weight is not None else summary.latest_weight
    return EnergyContext(summary=summary, body_goal=body_goal, latest_weight_kg=latest_weight)


def looks_like_remaining_calorie_question(text: str) -> bool:
    normalized = canonicalize(text)
    return any(hint in normalized for hint in REMAINING_HINTS)


def looks_like_energy_question(text: str) -> bool:
    normalized = canonicalize(text)
    if looks_like_remaining_calorie_question(normalized):
        return True
    if any(hint in normalized for hint in TDEE_HINTS):
        return True
    activity_signal = any(hint in normalized for hint in ACTIVITY_HINTS)
    burn_signal = any(hint in normalized for hint in BURN_HINTS)
    question_signal = any(hint in normalized for hint in QUESTION_HINTS)
    return activity_signal and (burn_signal or question_signal)


def answer_calorie_question(
    question: str,
    *,
    allow_search: bool = True,
    source_hint: str | None = None,
    context: EnergyContext | None = None,
) -> KnowledgeResult:
    combined = " ".join(part for part in [question, source_hint] if part).strip()
    energy_result = answer_energy_question(combined, context=context)
    if energy_result is not None:
        return energy_result
    return answer_nutrition_question(question, allow_search=allow_search, source_hint=source_hint)


def answer_energy_question(question: str, *, context: EnergyContext | None = None) -> KnowledgeResult | None:
    normalized = canonicalize(question)
    if context is not None and looks_like_remaining_calorie_question(normalized):
        return _answer_remaining_calories(context)
    if context is not None and any(hint in normalized for hint in TDEE_HINTS):
        return _answer_tdee_question(context)
    if looks_like_energy_question(normalized):
        estimate = estimate_activity_burn(question, context=context)
        if estimate is not None:
            return _answer_activity_burn(estimate)
    return None


def estimate_activity_burn(question: str, *, context: EnergyContext | None = None) -> dict[str, object] | None:
    match = _lookup_activity(question)
    if match is None:
        return None

    duration_minutes = _extract_duration_minutes(question)
    weight_from_query = _extract_weight_kg(question)
    weight_kg = weight_from_query if weight_from_query is not None else (context.latest_weight_kg if context is not None else None)
    weight_source = "query" if weight_from_query is not None else ("profile_latest_weight" if weight_kg is not None else "generic_range")

    met_low = float(match["met_low"])
    met_high = float(match["met_high"])
    met_low, met_high = _adjust_met_range_for_intensity(question, met_low, met_high)

    if duration_minutes is not None and weight_kg is not None:
        hours = duration_minutes / 60
        kcal_low = int(round(met_low * weight_kg * hours))
        kcal_high = int(round(met_high * weight_kg * hours))
    elif duration_minutes is not None:
        hours = duration_minutes / 60
        kcal_low = int(round(met_low * 60 * hours))
        kcal_high = int(round(met_high * 75 * hours))
    elif weight_kg is not None:
        kcal_low = int(round(met_low * weight_kg))
        kcal_high = int(round(met_high * weight_kg))
    else:
        kcal_low = int(round(met_low * 60))
        kcal_high = int(round(met_high * 75))

    return {
        "activity_name": match["name"],
        "activity_family": match.get("activity_family", ""),
        "source_path": str(KNOWLEDGE_DIR / ACTIVITY_PACK_FILE),
        "notes": match.get("notes", ""),
        "risk_flags": list(match.get("risk_flags", [])),
        "followup_slots": list(match.get("followup_slots", [])),
        "met_low": round(met_low, 2),
        "met_high": round(met_high, 2),
        "duration_minutes": duration_minutes,
        "weight_kg": round(weight_kg, 1) if weight_kg is not None else None,
        "weight_source": weight_source,
        "estimated_kcal_low": kcal_low,
        "estimated_kcal_high": kcal_high,
        "intensity_hint": _intensity_hint(question),
    }


def _answer_remaining_calories(context: EnergyContext) -> KnowledgeResult:
    summary = context.summary
    lines = [
        f"Today you have about {summary.remaining_kcal} kcal left.",
        f"Base target: {summary.base_target_kcal} kcal.",
        f"Activity added back today: +{summary.today_activity_burn_kcal} kcal, so the effective target is {summary.effective_target_kcal} kcal.",
        f"Consumed so far: {summary.consumed_kcal} kcal.",
    ]
    if summary.remaining_kcal < 0:
        lines.append("You are currently over the adjusted daily budget, so keep the next meal conservative.")
    return KnowledgeResult(
        answer="\n".join(lines),
        sources=[
            {"title": "energy_model_rules_tw", "path": ENERGY_RULES_PATH},
            {"title": "day_summary", "path": "app_state://day_summary"},
        ],
        packet={
            "match_mode": "remaining_budget",
            "matched_items": ["remaining_kcal"],
            "matched_packs": ["energy_model_rules_tw"],
            "remaining_kcal": summary.remaining_kcal,
            "base_target_kcal": summary.base_target_kcal,
            "effective_target_kcal": summary.effective_target_kcal,
            "today_activity_burn_kcal": summary.today_activity_burn_kcal,
            "consumed_kcal": summary.consumed_kcal,
        },
    )


def _answer_tdee_question(context: EnergyContext) -> KnowledgeResult:
    body_goal = context.body_goal
    summary = context.summary
    confidence_pct = int(round(body_goal.calibration_confidence * 100))
    lines = [
        f"Current app TDEE estimate: {body_goal.estimated_tdee_kcal} kcal/day.",
        f"Base intake target: {body_goal.base_target_kcal} kcal/day = TDEE {body_goal.estimated_tdee_kcal} - deficit {body_goal.default_daily_deficit_kcal}.",
        f"Today's activity burn is tracked separately at +{summary.today_activity_burn_kcal} kcal, so today's effective target is {summary.effective_target_kcal} kcal.",
        f"Calibration confidence: {confidence_pct}%.",
    ]
    if body_goal.latest_weight is not None:
        lines.append(f"Latest recorded weight: {body_goal.latest_weight} kg.")
    return KnowledgeResult(
        answer="\n".join(lines),
        sources=[
            {"title": "energy_model_rules_tw", "path": ENERGY_RULES_PATH},
            {"title": "body_goal", "path": "app_state://body_goal"},
        ],
        packet={
            "match_mode": "tdee_context",
            "matched_items": ["estimated_tdee_kcal"],
            "matched_packs": ["energy_model_rules_tw"],
            "estimated_tdee_kcal": body_goal.estimated_tdee_kcal,
            "base_target_kcal": body_goal.base_target_kcal,
            "default_daily_deficit_kcal": body_goal.default_daily_deficit_kcal,
            "calibration_confidence": body_goal.calibration_confidence,
            "today_activity_burn_kcal": summary.today_activity_burn_kcal,
            "effective_target_kcal": summary.effective_target_kcal,
        },
    )


def _answer_activity_burn(estimate: dict[str, object]) -> KnowledgeResult:
    activity_name = str(estimate["activity_name"])
    kcal_low = int(estimate["estimated_kcal_low"])
    kcal_high = int(estimate["estimated_kcal_high"])
    duration_minutes = estimate.get("duration_minutes")
    weight_kg = estimate.get("weight_kg")
    lines: list[str] = []

    if duration_minutes is not None and weight_kg is not None:
        lines.append(
            f"Estimated burn for `{activity_name}` is about {kcal_low}-{kcal_high} kcal."
        )
        lines.append(
            f"I used {duration_minutes} minutes, body weight {weight_kg} kg, and a {estimate['met_low']}-{estimate['met_high']} MET range."
        )
    elif duration_minutes is not None:
        lines.append(
            f"Estimated burn for `{activity_name}` is about {kcal_low}-{kcal_high} kcal for a generic 60-75 kg adult."
        )
        lines.append(
            f"I used {duration_minutes} minutes and a {estimate['met_low']}-{estimate['met_high']} MET range because your weight was not explicit in the question."
        )
    elif weight_kg is not None:
        lines.append(
            f"For `{activity_name}`, a one-hour burn estimate is about {kcal_low}-{kcal_high} kcal at {weight_kg} kg."
        )
        lines.append("Give me the duration and I can convert that to a session total.")
    else:
        lines.append(
            f"For `{activity_name}`, a one-hour burn estimate is about {kcal_low}-{kcal_high} kcal for a generic 60-75 kg adult."
        )
        lines.append("Give me your weight and duration and I can tighten the estimate.")

    notes = str(estimate.get("notes") or "")
    if notes:
        lines.append(f"Why the range is wide: {notes}")

    return KnowledgeResult(
        answer="\n".join(lines),
        sources=[
            {"title": activity_name, "path": str(estimate["source_path"])},
            {"title": "energy_model_rules_tw", "path": ENERGY_RULES_PATH},
        ],
        packet={
            "match_mode": "activity_estimate",
            "matched_items": [activity_name],
            "matched_packs": ["activity_met_values_tw", "energy_model_rules_tw"],
            "activity_name": activity_name,
            "met_low": estimate["met_low"],
            "met_high": estimate["met_high"],
            "duration_minutes": duration_minutes,
            "weight_kg": weight_kg,
            "weight_source": estimate["weight_source"],
            "estimated_kcal_low": kcal_low,
            "estimated_kcal_high": kcal_high,
            "intensity_hint": estimate["intensity_hint"],
            "followup_slots": estimate["followup_slots"],
            "risk_flags": estimate["risk_flags"],
        },
    )


def _lookup_activity(question: str) -> dict[str, object] | None:
    normalized = canonicalize(question)
    ranked: list[tuple[float, dict[str, object]]] = []
    for item in load_json_records(ACTIVITY_PACK_FILE):
        aliases = [canonicalize(value) for value in [item.get("name", ""), *item.get("aliases", []), *item.get("examples", [])] if value]
        score = 0.0
        for alias in aliases:
            if alias and alias in normalized:
                score += 5 + min(len(alias), 10) / 10
        if str(item.get("activity_family", "")) and str(item.get("activity_family")) in normalized:
            score += 2
        if score > 0:
            ranked.append((score, item))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return ranked[0][1] if ranked else None


def _adjust_met_range_for_intensity(question: str, met_low: float, met_high: float) -> tuple[float, float]:
    normalized = canonicalize(question)
    midpoint = (met_low + met_high) / 2
    if any(hint in normalized for hint in VIGOROUS_HINTS):
        return round(midpoint, 2), round(met_high, 2)
    if any(hint in normalized for hint in LIGHT_HINTS):
        return round(met_low, 2), round(midpoint, 2)
    return round(met_low, 2), round(met_high, 2)


def _intensity_hint(question: str) -> str:
    normalized = canonicalize(question)
    if any(hint in normalized for hint in VIGOROUS_HINTS):
        return "vigorous"
    if any(hint in normalized for hint in LIGHT_HINTS):
        return "light"
    return "unspecified"


def _extract_weight_kg(text: str) -> float | None:
    match = WEIGHT_PATTERN.search(text)
    if not match:
        return None
    return float(match.group("weight"))


def _extract_duration_minutes(text: str) -> int | None:
    normalized = canonicalize(text)
    total_minutes = 0

    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr|小時)", normalized, flags=re.IGNORECASE):
        total_minutes += int(round(float(match.group(1)) * 60))
    for match in re.finditer(r"(\d+)\s*(?:minutes?|mins?|min|分鐘)", normalized, flags=re.IGNORECASE):
        total_minutes += int(match.group(1))

    if total_minutes == 0:
        for phrase, value in _chinese_hour_phrases():
            if phrase in normalized:
                total_minutes = max(total_minutes, int(round(value * 60)))
        for phrase, value in _chinese_minute_phrases():
            if phrase in normalized:
                total_minutes += value

    return total_minutes or None


def _chinese_hour_phrases() -> list[tuple[str, float]]:
    return [
        ("兩個半小時", 2.5),
        ("两个半小时", 2.5),
        ("一個半小時", 1.5),
        ("一个半小时", 1.5),
        ("半小時", 0.5),
        ("半小时", 0.5),
        ("三小時", 3.0),
        ("三小时", 3.0),
        ("兩小時", 2.0),
        ("兩小时", 2.0),
        ("二小時", 2.0),
        ("二小时", 2.0),
        ("一小時", 1.0),
        ("一小时", 1.0),
    ]


def _chinese_minute_phrases() -> list[tuple[str, int]]:
    return [
        ("九十分鐘", 90),
        ("九十分钟", 90),
        ("六十分鐘", 60),
        ("六十分钟", 60),
        ("四十五分鐘", 45),
        ("四十五分钟", 45),
        ("三十分鐘", 30),
        ("三十分钟", 30),
    ]
