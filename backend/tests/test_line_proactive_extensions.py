from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.api import routes as route_module
from app.models import Food, MealDraft, MealEvent, MealLog, Notification, PlanEvent, User, utcnow
from app.providers.base import EstimateResult
from app.services import daily_nudge


def test_line_webhook_uses_flex_confirmation_card(client, db_session_factory, monkeypatch):
    captured: dict[str, object] = {}

    async def fake_reply(reply_token: str, text: str | None = None, *, quick_reply=None, flex_message=None, messages=None) -> None:
        captured["reply_token"] = reply_token
        captured["text"] = text
        captured["flex"] = flex_message

    def fake_route_text_task(text: str) -> tuple[str, float]:
        return "meal_log_now", 0.9

    async def fake_estimate_with_knowledge(*args, **kwargs):
        return EstimateResult(
            parsed_items=[{"name": "雞胸便當", "kcal": 520}],
            estimate_kcal=520,
            kcal_low=480,
            kcal_high=560,
            confidence=0.65,
            uncertainty_note="Portion seems clear enough.",
        )

    def fake_create_or_update_draft(db, user, request, estimate):
        return MealDraft(
            id="draft-flex",
            user_id=user.id,
            meal_session_id="session-flex",
            date=date.today(),
            event_at=utcnow(),
            meal_type="lunch",
            status="ready_to_confirm",
            raw_input_text="雞胸便當",
            source_mode="text",
            mode="standard",
            attachments=[],
            parsed_items=estimate.parsed_items,
            missing_slots=[],
            followup_question=None,
            draft_context={"confirmation_mode": "needs_confirmation", "primary_uncertainties": []},
            estimate_kcal=estimate.estimate_kcal,
            kcal_low=estimate.kcal_low,
            kcal_high=estimate.kcal_high,
            confidence=estimate.confidence,
            uncertainty_note=estimate.uncertainty_note,
        )

    monkeypatch.setattr(route_module, "reply_line_message", fake_reply)
    monkeypatch.setattr(route_module, "verify_line_signature", lambda body, signature: True)
    monkeypatch.setattr(route_module, "_route_text_task", fake_route_text_task)
    monkeypatch.setattr(route_module, "_estimate_with_knowledge", fake_estimate_with_knowledge)
    monkeypatch.setattr(route_module, "create_or_update_draft", fake_create_or_update_draft)

    response = client.post(
        "/webhooks/line",
        json={
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "timestamp": 12345,
                    "source": {"userId": "test-user"},
                    "message": {"id": "message-1", "type": "text", "text": "幫我記雞胸便當"},
                }
            ]
        },
    )

    assert response.status_code == 200
    assert captured["reply_token"] == "reply-token"
    assert captured["flex"] is not None


def test_line_webhook_can_confirm_latest_open_draft(client, db_session_factory, monkeypatch):
    captured: dict[str, str] = {}

    async def fake_reply(reply_token: str, text: str | None = None, *, quick_reply=None, flex_message=None, messages=None) -> None:
        captured["text"] = text or ""

    monkeypatch.setattr(route_module, "reply_line_message", fake_reply)
    monkeypatch.setattr(route_module, "verify_line_signature", lambda body, signature: True)

    with db_session_factory() as db:
        user = db.query(User).filter_by(line_user_id="test-user").one()
        draft = MealDraft(
            id="draft-confirm",
            user_id=user.id,
            meal_session_id="session-confirm",
            date=date.today(),
            event_at=utcnow(),
            meal_type="dinner",
            status="ready_to_confirm",
            raw_input_text="火鍋",
            source_mode="text",
            mode="standard",
            attachments=[],
            parsed_items=[{"name": "火鍋", "kcal": 900}],
            missing_slots=[],
            followup_question=None,
            draft_context={"confirmation_mode": "needs_confirmation"},
            estimate_kcal=900,
            kcal_low=820,
            kcal_high=980,
            confidence=0.72,
            uncertainty_note="",
        )
        db.add(draft)
        db.commit()

    response = client.post(
        "/webhooks/line",
        json={
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "timestamp": 12345,
                    "source": {"userId": "test-user"},
                    "message": {"id": "message-2", "type": "text", "text": "確認這餐"},
                }
            ]
        },
    )

    assert response.status_code == 200
    assert "已記錄" in captured["text"]
    with db_session_factory() as db:
        logs = db.query(MealLog).filter_by(meal_session_id="session-confirm").all()
        assert len(logs) == 1


def test_line_future_event_probe_creates_meal_event(client, db_session_factory, monkeypatch):
    captured: dict[str, str] = {}

    async def fake_reply(reply_token: str, text: str | None = None, *, quick_reply=None, flex_message=None, messages=None) -> None:
        captured["text"] = text or ""

    monkeypatch.setattr(route_module, "reply_line_message", fake_reply)
    monkeypatch.setattr(route_module, "verify_line_signature", lambda body, signature: True)
    monkeypatch.setattr(route_module, "_route_text_task", lambda text: ("future_event_probe", 0.9))

    response = client.post(
        "/webhooks/line",
        json={
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "timestamp": 12345,
                    "source": {"userId": "test-user"},
                    "message": {"id": "message-3", "type": "text", "text": "明天晚餐火鍋聚餐"},
                }
            ]
        },
    )

    assert response.status_code == 200
    assert "已先記下" in captured["text"]
    with db_session_factory() as db:
        assert db.query(MealEvent).count() == 1
        assert db.query(PlanEvent).filter_by(event_type="meal_event").count() == 1


def test_daily_nudge_sends_only_once_per_day(db_session_factory, monkeypatch):
    sent_messages: list[str] = []

    async def fake_push(line_user_id: str, text: str | None = None, *, flex_message=None, messages=None) -> None:
        sent_messages.append(text or "")

    monkeypatch.setattr(daily_nudge, "push_line_message", fake_push)

    with db_session_factory() as db:
        first = daily_nudge.process_proactive_pushes_once(
            db,
            now=datetime(2026, 3, 20, 20, 30, tzinfo=timezone(timedelta(hours=8))),
        )
        second = daily_nudge.process_proactive_pushes_once(
            db,
            now=datetime(2026, 3, 20, 20, 31, tzinfo=timezone(timedelta(hours=8))),
        )
        assert first == 1
        assert second == 0
        notifications = db.query(Notification).filter_by(type="daily_nudge").all()
        assert len(notifications) == 1

    assert len(sent_messages) == 1
    assert "今天好像還沒記錄" in sent_messages[0]


def test_food_store_context_is_updated_after_confirm(client, db_session_factory):
    with db_session_factory() as db:
        user = db.query(User).filter_by(line_user_id="test-user").one()
        draft = MealDraft(
            id="draft-store-context",
            user_id=user.id,
            meal_session_id="session-store",
            date=date.today(),
            event_at=utcnow(),
            meal_type="lunch",
            status="ready_to_confirm",
            raw_input_text="Subway 雞胸潛艇堡",
            source_mode="text",
            mode="standard",
            attachments=[],
            parsed_items=[{"name": "Subway 雞胸潛艇堡", "kcal": 430}],
            missing_slots=[],
            followup_question=None,
            draft_context={
                "confirmation_mode": "needs_confirmation",
                "store_name": "Subway Xinyi",
                "place_id": "place-subway-xinyi",
                "location_context": "公司附近",
            },
            estimate_kcal=430,
            kcal_low=390,
            kcal_high=470,
            confidence=0.72,
            uncertainty_note="",
        )
        db.add(draft)
        db.commit()

    response = client.post("/api/intake/draft-store-context/confirm", json={"force_confirm": True})
    assert response.status_code == 200

    with db_session_factory() as db:
        food = db.query(Food).filter_by(name="Subway 雞胸潛艇堡").one()
        assert food.store_context["top_store_name"] == "Subway Xinyi"
        assert food.store_context["top_place_id"] == "place-subway-xinyi"
