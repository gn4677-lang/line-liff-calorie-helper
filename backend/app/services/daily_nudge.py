from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import resolved_timezone, settings
from ..models import Notification, User
from ..schemas import EatFeedRequest
from .eat_feed import build_eat_feed
from .line import build_action_flex_message, build_liff_tab_url, push_line_message
from .meal_events import upcoming_meal_event_for_day
from .proactive import create_notification
from .summary import build_day_summary


PROACTIVE_NOTIFICATION_TYPES = {"daily_nudge", "meal_event_reminder", "dinner_pick"}


def process_proactive_pushes_once(db: Session, *, now: datetime | None = None) -> int:
    if not settings.proactive_push_enabled:
        return 0
    tz = resolved_timezone()
    local_now = now.astimezone(tz) if now else datetime.now(tz)
    sent = 0
    users = list(db.scalars(select(User).order_by(User.id)))
    for user in users:
        if not user.line_user_id:
            continue
        if _already_sent_today(db, user, local_now.date()):
            continue
        if _maybe_send_event_reminder(db, user, local_now):
            sent += 1
            continue
        if _maybe_send_daily_nudge(db, user, local_now):
            sent += 1
    return sent


def _maybe_send_event_reminder(db: Session, user: User, now: datetime) -> bool:
    if now.hour < settings.event_reminder_hour:
        return False
    target_date = now.date() + timedelta(days=1)
    events = upcoming_meal_event_for_day(db, user, target_date)
    if not events:
        return False
    event = events[0]
    message = (
        f"提醒一下，你明天的 { _meal_type_label(event.meal_type) } 已先記成「{event.title}」"
        f"（約 {event.expected_kcal} kcal）。如果情況變了，直接在 LINE 回我就好。"
    )
    flex_message = build_action_flex_message(
        title="明日大餐提醒",
        subtitle=f"{target_date.isoformat()} · {_meal_type_label(event.meal_type)}",
        lines=[
            f"已先幫你記下「{event.title}」。",
            f"目前先抓約 {event.expected_kcal} kcal。",
            "如果情況變了，直接回 LINE 修正就好。",
        ],
        primary_label="看策略",
        primary_uri=build_liff_tab_url("progress"),
        secondary_label="看今天",
        secondary_uri=build_liff_tab_url("today"),
    )
    _create_and_push(
        db,
        user,
        notification_type="meal_event_reminder",
        title="明日大餐提醒",
        body=message,
        payload={"date": now.date().isoformat(), "event_date": target_date.isoformat(), "meal_event_id": event.id},
        text=message,
        flex_message=flex_message,
    )
    return True


def _maybe_send_daily_nudge(db: Session, user: User, now: datetime) -> bool:
    if not settings.daily_nudge_enabled or now.hour < settings.daily_nudge_hour:
        return False
    summary = build_day_summary(db, user, now.date())
    if summary.consumed_kcal == 0:
        text = "今天好像還沒記錄。直接回一句、拍照，或丟語音給我就可以。"
        flex_message = build_action_flex_message(
            title="今天還沒記錄",
            subtitle="直接回一句、拍照，或丟語音都可以",
            lines=[
                "如果你現在方便，回我一句吃了什麼就好。",
                "也可以直接拍照或用語音，我會幫你整理。",
            ],
            primary_label="打開今日",
            primary_uri=build_liff_tab_url("today"),
        )
        _create_and_push(
            db,
            user,
            notification_type="daily_nudge",
            title="今天還沒記錄",
            body=text,
            payload={"date": now.date().isoformat(), "mode": "no_log"},
            text=text,
            flex_message=flex_message,
        )
        return True

    has_dinner = any(log.meal_type == "dinner" for log in summary.logs)
    if has_dinner or summary.remaining_kcal < 250 or summary.remaining_kcal > 950:
        return False

    feed = build_eat_feed(
        db,
        user,
        EatFeedRequest(meal_type="dinner", time_context="now", location_mode="none"),
        remaining_kcal=summary.remaining_kcal,
    )
    if not feed.top_pick:
        return False
    top_pick = feed.top_pick
    text = (
        f"你今天還剩 {summary.remaining_kcal} kcal。"
        f"我先幫你縮成一個低風險答案：{top_pick.title} "
        f"({top_pick.kcal_low}-{top_pick.kcal_high} kcal)。"
    )
    flex_message = build_action_flex_message(
        title="晚餐主推",
        subtitle=f"今天還剩 {summary.remaining_kcal} kcal",
        lines=[
            top_pick.title,
            f"{top_pick.kcal_low}-{top_pick.kcal_high} kcal",
            top_pick.reason_factors[0] if top_pick.reason_factors else "我先幫你縮成一個低風險答案。",
        ],
        primary_label="看推薦",
        primary_uri=build_liff_tab_url("eat"),
        secondary_label="看今天",
        secondary_uri=build_liff_tab_url("today"),
    )
    _create_and_push(
        db,
        user,
        notification_type="dinner_pick",
        title="晚餐主推",
        body=text,
        payload={"date": now.date().isoformat(), "session_id": feed.session_id, "candidate_id": top_pick.candidate_id},
        text=text,
        flex_message=flex_message,
    )
    return True


def _already_sent_today(db: Session, user: User, target_date: date) -> bool:
    rows = list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id, Notification.type.in_(tuple(PROACTIVE_NOTIFICATION_TYPES)))
        )
    )
    for row in rows:
        payload = row.payload or {}
        if payload.get("date") == target_date.isoformat():
            return True
    return False


def _create_and_push(
    db: Session,
    user: User,
    *,
    notification_type: str,
    title: str,
    body: str,
    payload: dict,
    text: str,
    flex_message: dict | None = None,
) -> None:
    create_notification(
        db,
        user,
        notification_type=notification_type,
        title=title,
        body=body,
        payload=payload,
    )
    try:
        import asyncio

        asyncio.run(push_line_message(user.line_user_id, text, flex_message=flex_message))
    except Exception:
        pass


def _meal_type_label(meal_type: str) -> str:
    return {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "snack": "點心",
    }.get(meal_type, meal_type)
