from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import MealLog, User, WeightLog
from ..schemas import DaySummaryResponse, MealLogResponse


def build_day_summary(db: Session, user: User, target_date: date) -> DaySummaryResponse:
    logs = list(db.scalars(select(MealLog).where(MealLog.user_id == user.id, MealLog.date == target_date).order_by(MealLog.created_at)))
    consumed = sum(log.kcal_estimate for log in logs)
    remaining = user.daily_calorie_target - consumed

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

    if direction == "down" and consumed <= user.daily_calorie_target * 1.05:
        hint = "趨勢方向大致正確，先維持目前目標。"
    elif direction == "up" and consumed > user.daily_calorie_target * 1.05:
        hint = "近兩週可能偏高，先把記錄品質穩住，再考慮小降 100 kcal。"
    else:
        hint = "先累積 14 天較完整紀錄，再決定是否調整目標。"

    return DaySummaryResponse(
        date=target_date,
        target_kcal=user.daily_calorie_target,
        consumed_kcal=consumed,
        remaining_kcal=remaining,
        logs=[
            MealLogResponse(
                id=log.id,
                date=log.date,
                meal_type=log.meal_type,
                description_raw=log.description_raw,
                kcal_estimate=log.kcal_estimate,
                kcal_low=log.kcal_low,
                kcal_high=log.kcal_high,
                confidence=log.confidence,
                source_mode=log.source_mode,
                parsed_items=log.parsed_items,
                uncertainty_note=log.uncertainty_note,
            )
            for log in logs
        ],
        seven_day_average_weight=seven_day_average,
        fourteen_day_direction=direction,
        target_adjustment_hint=hint,
    )
