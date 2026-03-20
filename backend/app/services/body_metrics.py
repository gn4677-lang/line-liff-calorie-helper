from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ActivityAdjustment, BodyGoal, MealLog, User, WeightLog, utcnow
from ..schemas import (
    ActivityAdjustmentRequest,
    ActivityAdjustmentResponse,
    ActivityAdjustmentUpdateRequest,
    BodyGoalResponse,
    BodyGoalUpdateRequest,
    ProgressSeriesPoint,
    ProgressSeriesResponse,
)


DEFAULT_TDEE_BUFFER = 300
DEFAULT_DAILY_DEFICIT = 300
MIN_TARGET_KCAL = 1200
MIN_TDEE_KCAL = 1500
MAX_TDEE_KCAL = 4000
MAX_TDEE_STEP = 80
CALIBRATION_WINDOW_DAYS = 14


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def get_or_create_body_goal(db: Session, user: User) -> BodyGoal:
    goal = db.scalar(select(BodyGoal).where(BodyGoal.user_id == user.id))
    if goal:
        return goal

    goal = BodyGoal(
        user_id=user.id,
        estimated_tdee_kcal=max(user.daily_calorie_target + DEFAULT_TDEE_BUFFER, MIN_TARGET_KCAL + DEFAULT_DAILY_DEFICIT),
        default_daily_deficit_kcal=DEFAULT_DAILY_DEFICIT,
        calibration_confidence=0.1,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    _sync_user_target(db, user, goal)
    return goal


def _sync_user_target(db: Session, user: User, goal: BodyGoal) -> None:
    new_target = base_target_kcal(goal)
    if user.daily_calorie_target != new_target:
        user.daily_calorie_target = new_target
        db.add(user)
        db.commit()
        db.refresh(user)


def base_target_kcal(goal: BodyGoal) -> int:
    return max(int(round(goal.estimated_tdee_kcal - goal.default_daily_deficit_kcal)), MIN_TARGET_KCAL)


def latest_weight_value(db: Session, user: User, *, target_date: date | None = None) -> tuple[float | None, bool]:
    query = select(WeightLog).where(WeightLog.user_id == user.id)
    if target_date is not None:
        query = query.where(WeightLog.date <= target_date)
    row = db.scalar(query.order_by(WeightLog.date.desc()))
    if row is None:
        return None, False
    return row.weight, bool(target_date and row.date == target_date)


def delta_to_goal(latest_weight: float | None, target_weight_kg: float | None) -> float | None:
    if latest_weight is None or target_weight_kg is None:
        return None
    return round(latest_weight - target_weight_kg, 1)


def body_goal_to_response(db: Session, user: User, goal: BodyGoal, *, target_date: date | None = None) -> BodyGoalResponse:
    latest_weight, _ = latest_weight_value(db, user, target_date=target_date)
    return BodyGoalResponse(
        target_weight_kg=goal.target_weight_kg,
        estimated_tdee_kcal=goal.estimated_tdee_kcal,
        default_daily_deficit_kcal=goal.default_daily_deficit_kcal,
        base_target_kcal=base_target_kcal(goal),
        calibration_confidence=round(goal.calibration_confidence, 3),
        latest_weight=latest_weight,
        delta_to_goal=delta_to_goal(latest_weight, goal.target_weight_kg),
        last_calibrated_at=goal.last_calibrated_at,
    )


def update_body_goal(db: Session, user: User, request: BodyGoalUpdateRequest) -> BodyGoal:
    goal = get_or_create_body_goal(db, user)
    updates = request.model_dump(exclude_none=True)
    if "target_weight_kg" in updates:
        goal.target_weight_kg = updates["target_weight_kg"]
    if "estimated_tdee_kcal" in updates:
        goal.estimated_tdee_kcal = int(clamp(float(updates["estimated_tdee_kcal"]), MIN_TDEE_KCAL, MAX_TDEE_KCAL))
    if "default_daily_deficit_kcal" in updates:
        goal.default_daily_deficit_kcal = max(int(updates["default_daily_deficit_kcal"]), 0)
    goal.updated_at = utcnow()
    db.add(goal)
    db.commit()
    db.refresh(goal)
    _sync_user_target(db, user, goal)
    return goal


def list_activity_adjustments(
    db: Session,
    user: User,
    *,
    target_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[ActivityAdjustmentResponse]:
    query = select(ActivityAdjustment).where(ActivityAdjustment.user_id == user.id)
    if target_date is not None:
        query = query.where(ActivityAdjustment.date == target_date)
    if start_date is not None:
        query = query.where(ActivityAdjustment.date >= start_date)
    if end_date is not None:
        query = query.where(ActivityAdjustment.date <= end_date)
    rows = list(db.scalars(query.order_by(ActivityAdjustment.date.desc(), ActivityAdjustment.updated_at.desc())))
    return [activity_to_response(row) for row in rows]


def activity_to_response(row: ActivityAdjustment) -> ActivityAdjustmentResponse:
    return ActivityAdjustmentResponse(
        id=row.id,
        date=row.date,
        label=row.label,
        estimated_burn_kcal=row.estimated_burn_kcal,
        duration_minutes=row.duration_minutes,
        source=row.source,
        raw_input_text=row.raw_input_text or "",
        notes=row.notes or "",
    )


def create_activity_adjustment(db: Session, user: User, request: ActivityAdjustmentRequest) -> ActivityAdjustment:
    row = ActivityAdjustment(
        user_id=user.id,
        date=request.date or date.today(),
        label=request.label,
        estimated_burn_kcal=request.estimated_burn_kcal,
        duration_minutes=request.duration_minutes,
        source=request.source,
        raw_input_text=request.raw_input_text,
        notes=request.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    refresh_body_goal_calibration(db, user)
    return row


def update_activity_adjustment(db: Session, user: User, adjustment_id: int, request: ActivityAdjustmentUpdateRequest) -> ActivityAdjustment:
    row = db.get(ActivityAdjustment, adjustment_id)
    if not row or row.user_id != user.id:
        raise ValueError("Activity adjustment not found")
    updates = request.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(row, field, value)
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    refresh_body_goal_calibration(db, user)
    return row


def delete_activity_adjustment(db: Session, user: User, adjustment_id: int) -> None:
    row = db.get(ActivityAdjustment, adjustment_id)
    if not row or row.user_id != user.id:
        raise ValueError("Activity adjustment not found")
    db.delete(row)
    db.commit()
    refresh_body_goal_calibration(db, user)


def total_activity_burn(db: Session, user: User, target_date: date) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(ActivityAdjustment.estimated_burn_kcal), 0))
        .where(ActivityAdjustment.user_id == user.id, ActivityAdjustment.date == target_date)
    )
    return int(total or 0)


def effective_target_kcal(goal: BodyGoal, activity_burn_kcal: int, overlay: dict | None = None, *, target_date: date | None = None) -> int:
    base = base_target_kcal(goal)
    adjusted = base + activity_burn_kcal
    if overlay and target_date is not None:
        by_date = overlay.get("overlay_allocations", {}).get("by_date", {})
        adjusted = int(by_date.get(target_date.isoformat(), adjusted))
    elif overlay:
        adjusted = int(overlay.get("overlay_allocations", {}).get("today_target", adjusted))
    return max(adjusted, MIN_TARGET_KCAL)


def refresh_body_goal_calibration(db: Session, user: User) -> BodyGoal:
    goal = get_or_create_body_goal(db, user)
    window_end = date.today()
    window_start = window_end - timedelta(days=CALIBRATION_WINDOW_DAYS - 1)

    weights = list(
        db.scalars(
            select(WeightLog)
            .where(WeightLog.user_id == user.id, WeightLog.date >= window_start, WeightLog.date <= window_end)
            .order_by(WeightLog.date)
        )
    )
    logs = list(
        db.scalars(
            select(MealLog)
            .where(MealLog.user_id == user.id, MealLog.date >= window_start, MealLog.date <= window_end)
            .order_by(MealLog.date)
        )
    )
    activities = list(
        db.scalars(
            select(ActivityAdjustment)
            .where(ActivityAdjustment.user_id == user.id, ActivityAdjustment.date >= window_start, ActivityAdjustment.date <= window_end)
            .order_by(ActivityAdjustment.date)
        )
    )

    weight_days = len({item.date for item in weights})
    logged_days = len({item.date for item in logs})
    confidence = round(min(weight_days / 5, 1.0) * 0.45 + min(logged_days / 10, 1.0) * 0.55, 3)
    goal.calibration_confidence = confidence

    if weight_days < 5 or logged_days < 10:
        db.add(goal)
        db.commit()
        db.refresh(goal)
        return goal

    days_span = max((weights[-1].date - weights[0].date).days, 1)
    avg_intake = sum(log.kcal_estimate for log in logs) / CALIBRATION_WINDOW_DAYS
    avg_activity = sum(item.estimated_burn_kcal for item in activities) / CALIBRATION_WINDOW_DAYS
    weight_delta = weights[-1].weight - weights[0].weight
    observed_tdee = avg_intake - (weight_delta * 7700 / days_span) - avg_activity
    bounded_observed = clamp(observed_tdee, MIN_TDEE_KCAL, MAX_TDEE_KCAL)
    proposed = goal.estimated_tdee_kcal * 0.85 + bounded_observed * 0.15
    limited = clamp(proposed, goal.estimated_tdee_kcal - MAX_TDEE_STEP, goal.estimated_tdee_kcal + MAX_TDEE_STEP)
    goal.estimated_tdee_kcal = int(round(clamp(limited, MIN_TDEE_KCAL, MAX_TDEE_KCAL)))
    goal.last_calibrated_at = datetime.now(timezone.utc)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    _sync_user_target(db, user, goal)
    return goal


def build_progress_series(db: Session, user: User, *, range_key: str, resolution: str = "day") -> ProgressSeriesResponse:
    days = _range_days(range_key)
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    goal = get_or_create_body_goal(db, user)

    weight_rows = {
        row.date: row.weight
        for row in db.scalars(
            select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.date >= start_date, WeightLog.date <= end_date)
        )
    }
    calorie_rows = {
        row[0]: int(row[1] or 0)
        for row in db.execute(
            select(MealLog.date, func.sum(MealLog.kcal_estimate))
            .where(MealLog.user_id == user.id, MealLog.date >= start_date, MealLog.date <= end_date)
            .group_by(MealLog.date)
        ).all()
    }
    activity_rows = {
        row[0]: int(row[1] or 0)
        for row in db.execute(
            select(ActivityAdjustment.date, func.sum(ActivityAdjustment.estimated_burn_kcal))
            .where(ActivityAdjustment.user_id == user.id, ActivityAdjustment.date >= start_date, ActivityAdjustment.date <= end_date)
            .group_by(ActivityAdjustment.date)
        ).all()
    }

    weight_points: list[ProgressSeriesPoint] = []
    calorie_points: list[ProgressSeriesPoint] = []
    activity_points: list[ProgressSeriesPoint] = []
    current = start_date
    while current <= end_date:
        target = base_target_kcal(goal)
        if current in weight_rows:
            weight_points.append(ProgressSeriesPoint(date=current, value=round(weight_rows[current], 1)))
        calorie_points.append(ProgressSeriesPoint(date=current, value=calorie_rows.get(current, 0), target=target))
        activity_points.append(ProgressSeriesPoint(date=current, value=activity_rows.get(current, 0)))
        current += timedelta(days=1)

    if resolution in ("week", "month"):
        def group_points(pts: list[ProgressSeriesPoint], res: str) -> list[ProgressSeriesPoint]:
            if not pts:
                return []
            grouped = {}
            for p in pts:
                if res == "month":
                    key = p.date.replace(day=1)
                else:
                    key = p.date - timedelta(days=p.date.weekday())
                
                if key not in grouped:
                    grouped[key] = {"sum": 0.0, "count": 0, "target": 0.0, "target_count": 0}
                
                grouped[key]["sum"] += float(p.value)
                grouped[key]["count"] += 1
                if p.target is not None:
                    grouped[key]["target"] += float(p.target)
                    grouped[key]["target_count"] += 1

            ret = []
            for k, agg in sorted(grouped.items()):
                val = round(agg["sum"] / agg["count"], 2)
                tgt = round(agg["target"] / agg["target_count"], 2) if agg["target_count"] > 0 else None
                ret.append(ProgressSeriesPoint(date=k, value=val, target=tgt))
            return ret

        weight_points = group_points(weight_points, resolution)
        calorie_points = group_points(calorie_points, resolution)
        activity_points = group_points(activity_points, resolution)

    return ProgressSeriesResponse(
        range=range_key,
        weight_points=weight_points,
        calorie_points=calorie_points,
        activity_points=activity_points,
    )


def _range_days(range_key: str) -> int:
    mapping = {
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "1y": 365,
    }
    return mapping.get(range_key, 30)
