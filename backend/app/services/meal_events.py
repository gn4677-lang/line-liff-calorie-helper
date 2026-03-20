from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import resolved_timezone
from ..models import MealEvent, PlanEvent, User, utcnow
from ..schemas import MealEventRequest, MealEventResponse


WEEKDAY_MAP = {
    "週一": 0,
    "星期一": 0,
    "禮拜一": 0,
    "monday": 0,
    "週二": 1,
    "星期二": 1,
    "禮拜二": 1,
    "tuesday": 1,
    "週三": 2,
    "星期三": 2,
    "禮拜三": 2,
    "wednesday": 2,
    "週四": 3,
    "星期四": 3,
    "禮拜四": 3,
    "thursday": 3,
    "週五": 4,
    "星期五": 4,
    "禮拜五": 4,
    "friday": 4,
    "週六": 5,
    "星期六": 5,
    "禮拜六": 5,
    "saturday": 5,
    "週日": 6,
    "星期日": 6,
    "禮拜日": 6,
    "星期天": 6,
    "禮拜天": 6,
    "sunday": 6,
}

MEAL_TYPE_KEYWORDS = {
    "breakfast": ("早餐", "breakfast", "早上"),
    "lunch": ("午餐", "lunch", "中午"),
    "dinner": ("晚餐", "聚餐", "宵夜", "dinner", "supper", "hotpot", "bbq"),
    "snack": ("點心", "下午茶", "snack", "dessert"),
}

HIGH_CALORIE_KEYWORDS = {
    "火鍋": 1050,
    "燒肉": 1100,
    "吃到飽": 1200,
    "聚餐": 950,
    "宵夜": 850,
    "buffet": 1200,
    "hotpot": 1050,
    "bbq": 1100,
    "pizza": 900,
    "dessert": 650,
}


@dataclass
class ParsedMealEvent:
    event_date: date
    meal_type: str
    title: str
    expected_kcal: int
    notes: str = ""


def parse_future_meal_event_text(text: str, *, now: datetime | None = None) -> ParsedMealEvent | None:
    normalized = (text or "").strip()
    if not normalized:
        return None
    lower = normalized.lower()
    tz = resolved_timezone()
    current = now.astimezone(tz) if now else datetime.now(tz)
    target_date = _extract_future_date(normalized, lower, current.date())
    if target_date is None:
        return None
    meal_type = _extract_meal_type(normalized, lower)
    expected_kcal = _estimate_event_kcal(normalized, lower, meal_type)
    title = normalized[:160]
    return ParsedMealEvent(
        event_date=target_date,
        meal_type=meal_type,
        title=title,
        expected_kcal=expected_kcal,
    )


def create_meal_event(db: Session, user: User, request: MealEventRequest) -> MealEvent:
    plan_event = PlanEvent(
        user_id=user.id,
        date=request.event_date,
        event_type="meal_event",
        title=request.title,
        expected_extra_kcal=request.expected_kcal or 0,
        planning_status="planned",
        notes=request.notes,
    )
    db.add(plan_event)
    db.flush()

    meal_event = MealEvent(
        user_id=user.id,
        plan_event_id=plan_event.id,
        event_date=request.event_date,
        meal_type=request.meal_type,
        title=request.title,
        expected_kcal=request.expected_kcal or 0,
        status="planned",
        source=request.source,
        notes=request.notes,
    )
    db.add(meal_event)
    db.commit()
    db.refresh(meal_event)
    return meal_event


def list_meal_events(db: Session, user: User, *, start_date: date | None = None, days: int = 14) -> list[MealEventResponse]:
    start = start_date or date.today()
    end = start + timedelta(days=days)
    rows = list(
        db.scalars(
            select(MealEvent)
            .where(MealEvent.user_id == user.id, MealEvent.event_date >= start, MealEvent.event_date <= end)
            .order_by(MealEvent.event_date, MealEvent.meal_type, MealEvent.created_at)
        )
    )
    return [meal_event_to_response(row) for row in rows]


def meal_event_to_response(row: MealEvent) -> MealEventResponse:
    return MealEventResponse(
        id=row.id,
        plan_event_id=row.plan_event_id,
        event_date=row.event_date,
        meal_type=row.meal_type,
        title=row.title,
        expected_kcal=row.expected_kcal,
        status=row.status,
        source=row.source,
        notes=row.notes,
    )


def upcoming_meal_event_for_day(db: Session, user: User, target_date: date) -> list[MealEvent]:
    return list(
        db.scalars(
            select(MealEvent)
            .where(MealEvent.user_id == user.id, MealEvent.event_date == target_date, MealEvent.status == "planned")
            .order_by(MealEvent.meal_type, MealEvent.created_at)
        )
    )


def _extract_future_date(text: str, lower: str, today: date) -> date | None:
    for pattern in (r"(\d{4})-(\d{1,2})-(\d{1,2})", r"(\d{1,2})/(\d{1,2})"):
        match = re.search(pattern, text)
        if not match:
            continue
        groups = [int(item) for item in match.groups()]
        if len(groups) == 3:
            year, month, day = groups
        else:
            year, month, day = today.year, groups[0], groups[1]
            if date(year, month, day) < today:
                year += 1
        try:
            target = date(year, month, day)
            if target >= today:
                return target
        except ValueError:
            continue

    if "明天" in text or "tomorrow" in lower:
        return today + timedelta(days=1)
    if "後天" in text:
        return today + timedelta(days=2)

    for token, weekday in WEEKDAY_MAP.items():
        if token not in lower and token not in text:
            continue
        delta = (weekday - today.weekday()) % 7
        if delta == 0:
            delta = 7
        return today + timedelta(days=delta)
    return None


def _extract_meal_type(text: str, lower: str) -> str:
    for meal_type, keywords in MEAL_TYPE_KEYWORDS.items():
        if any(keyword in text or keyword in lower for keyword in keywords):
            return meal_type
    return "dinner"


def _estimate_event_kcal(text: str, lower: str, meal_type: str) -> int:
    for keyword, kcal in HIGH_CALORIE_KEYWORDS.items():
        if keyword in text or keyword in lower:
            return kcal
    return {
        "breakfast": 420,
        "lunch": 700,
        "dinner": 900,
        "snack": 320,
    }.get(meal_type, 800)
