from __future__ import annotations

from datetime import date, timedelta
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import MealLog, PlanEvent, User, WeightLog
from ..schemas import DaySummaryResponse
from .body_metrics import (
    base_target_kcal,
    delta_to_goal,
    effective_target_kcal,
    get_or_create_body_goal,
    latest_weight_value,
    total_activity_burn,
)
from .intake import log_to_response
from .proactive import count_unread_notifications


def build_day_summary(db: Session, user: User, target_date: date) -> DaySummaryResponse:
    goal = get_or_create_body_goal(db, user)
    overlay = _active_overlay(db, user, target_date)
    base_target = base_target_kcal(goal)
    activity_burn = total_activity_burn(db, user, target_date)
    effective_target = effective_target_kcal(goal, activity_burn, overlay, target_date=target_date)

    logs = list(
        db.scalars(
            select(MealLog)
            .where(MealLog.user_id == user.id, MealLog.date == target_date)
            .order_by(MealLog.event_at, MealLog.created_at)
        )
    )
    meal_subtotals: dict[str, int] = {}
    meal_counts: dict[str, int] = {}
    consumed = 0
    for log in logs:
        typ = log.meal_type or "unknown"
        cur_cal = log.kcal_estimate or 0
        meal_subtotals[typ] = meal_subtotals.get(typ, 0) + cur_cal
        meal_counts[typ] = meal_counts.get(typ, 0) + 1
        consumed += cur_cal

    remaining = effective_target - consumed
    latest_weight, has_today_weight = latest_weight_value(db, user, target_date=target_date)

    weights = list(
        db.scalars(
            select(WeightLog)
            .where(WeightLog.user_id == user.id, WeightLog.date >= target_date - timedelta(days=13), WeightLog.date <= target_date)
            .order_by(WeightLog.date)
        )
    )
    seven_day = weights[-7:] if len(weights) >= 7 else weights
    seven_day_average = round(sum(item.weight for item in seven_day) / len(seven_day), 2) if seven_day else None
    if len(weights) >= 2:
        diff = weights[-1].weight - weights[0].weight
        direction = "down" if diff < -0.2 else "up" if diff > 0.2 else "flat"
    else:
        direction = "insufficient-data"

    weekly_target = base_target * 7
    weekly_consumed = _weekly_consumed_kcal(db, user, target_date)
    weekly_drift = weekly_consumed - weekly_target
    weekly_remaining = weekly_target - weekly_consumed
    weekly_status = _weekly_drift_status(weekly_drift)

    if direction == "down" and consumed <= effective_target * 1.05:
        hint = "最近的方向還在往目標前進，先維持現在的節奏。"
    elif direction == "up" and consumed > effective_target * 1.05:
        hint = "最近熱量和體重都偏高一些，這週可以考慮溫和收回。"
    else:
        hint = "先觀察最近 14 天的方向，再決定要不要調整目標。"

    return DaySummaryResponse(
        date=target_date,
        target_kcal=effective_target,
        base_target_kcal=base_target,
        effective_target_kcal=effective_target,
        consumed_kcal=consumed,
        remaining_kcal=remaining,
        today_activity_burn_kcal=activity_burn,
        meal_subtotals=meal_subtotals,
        meal_counts=meal_counts,
        logs=[log_to_response(log) for log in logs],
        latest_weight=latest_weight,
        has_today_weight=has_today_weight,
        target_weight_kg=goal.target_weight_kg,
        delta_to_goal_kg=delta_to_goal(latest_weight, goal.target_weight_kg),
        seven_day_average_weight=seven_day_average,
        fourteen_day_direction=direction,
        target_adjustment_hint=hint,
        weekly_target_kcal=weekly_target,
        weekly_consumed_kcal=weekly_consumed,
        weekly_remaining_kcal=weekly_remaining,
        weekly_drift_kcal=weekly_drift,
        weekly_drift_status=weekly_status,
        should_offer_weekly_recovery=weekly_status == "meaningfully_over",
        recovery_overlay=overlay,
        pending_async_updates_count=count_unread_notifications(db, user),
    )


def build_logbook_range(db: Session, user: User, *, start_date: date, end_date: date) -> list[dict[str, int | date]]:
    goal = get_or_create_body_goal(db, user)
    base_target = base_target_kcal(goal)
    rows = db.execute(
        select(MealLog.date, MealLog.id, MealLog.kcal_estimate)
        .where(MealLog.user_id == user.id, MealLog.date >= start_date, MealLog.date <= end_date)
        .order_by(MealLog.date)
    ).all()
    by_day: dict[date, dict[str, int | date]] = {}
    for day, _log_id, kcal in rows:
        bucket = by_day.setdefault(day, {"date": day, "consumed_kcal": 0, "target_kcal": base_target, "meal_count": 0})
        bucket["consumed_kcal"] = int(bucket["consumed_kcal"]) + int(kcal or 0)
        bucket["meal_count"] = int(bucket["meal_count"]) + 1

    items: list[dict[str, int | date]] = []
    current = start_date
    while current <= end_date:
        items.append(by_day.get(current, {"date": current, "consumed_kcal": 0, "target_kcal": base_target, "meal_count": 0}))
        current += timedelta(days=1)
    return items


def _weekly_consumed_kcal(db: Session, user: User, target_date: date) -> int:
    window_start = target_date - timedelta(days=6)
    logs = list(
        db.scalars(
            select(MealLog).where(MealLog.user_id == user.id, MealLog.date >= window_start, MealLog.date <= target_date)
        )
    )
    return sum(log.kcal_estimate for log in logs)


def _weekly_drift_status(drift: int) -> str:
    if drift > 900:
        return "meaningfully_over"
    if drift > 300:
        return "slightly_over"
    if drift < -900:
        return "meaningfully_under"
    return "on_track"


def _active_overlay(db: Session, user: User, target_date: date) -> dict | None:
    events = list(
        db.scalars(
            select(PlanEvent)
            .where(PlanEvent.user_id == user.id, PlanEvent.event_type == "recovery_overlay")
            .order_by(PlanEvent.date.desc())
        )
    )
    for event in events:
        try:
            data = json.loads(event.notes or "{}")
        except json.JSONDecodeError:
            continue
        active_until = data.get("overlay_active_until")
        if not active_until:
            continue
        if event.date <= target_date <= date.fromisoformat(active_until):
            return data
    return None
