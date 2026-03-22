from __future__ import annotations

from app.api import routes as route_module
from app.services import background_jobs


def test_calorie_qa_answers_remaining_budget_from_day_summary(client):
    client.patch(
        "/api/body-goal",
        json={
            "target_weight_kg": 65.0,
            "estimated_tdee_kcal": 2200,
            "default_daily_deficit_kcal": 400,
        },
    )
    client.post(
        "/api/activity-adjustments",
        json={"label": "dance class", "estimated_burn_kcal": 220, "duration_minutes": 45},
    )
    client.post(
        "/api/meal-logs/manual",
        json={"meal_type": "lunch", "description_raw": "test lunch", "kcal_estimate": 620},
    )

    response = client.post(
        "/api/qa/nutrition",
        json={"question": "How many calories do I have left today?", "allow_search": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payload"]["packet"]["match_mode"] == "remaining_budget"
    assert body["payload"]["packet"]["remaining_kcal"] == 1400
    assert "1400 kcal left" in body["coach_message"]
    assert "effective target is 2020 kcal" in body["coach_message"]


def test_calorie_qa_answers_tdee_with_daily_activity_context(client):
    client.patch(
        "/api/body-goal",
        json={
            "target_weight_kg": 65.0,
            "estimated_tdee_kcal": 2200,
            "default_daily_deficit_kcal": 400,
        },
    )
    client.post(
        "/api/activity-adjustments",
        json={"label": "evening walk", "estimated_burn_kcal": 180, "duration_minutes": 60},
    )

    response = client.post(
        "/api/qa/nutrition",
        json={"question": "What is my current TDEE?", "allow_search": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payload"]["packet"]["match_mode"] == "tdee_context"
    assert body["payload"]["packet"]["estimated_tdee_kcal"] == 2200
    assert "2200 kcal/day" in body["coach_message"]
    assert "today's effective target is 1980 kcal" in body["coach_message"]


def test_calorie_qa_estimates_dance_burn_using_latest_weight(client):
    client.post("/api/weights", json={"weight": 70.0})

    response = client.post(
        "/api/qa/nutrition",
        json={"question": "How many calories does 2 hours of dance burn?", "allow_search": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payload"]["packet"]["match_mode"] == "activity_estimate"
    assert body["payload"]["packet"]["weight_source"] == "profile_latest_weight"
    assert body["payload"]["packet"]["duration_minutes"] == 120
    assert "490-910 kcal" in body["coach_message"]


def test_line_webhook_answers_activity_burn_question(client, db_session_factory, monkeypatch):
    client.post("/api/weights", json={"weight": 70.0})
    captured: dict[str, str] = {}

    async def fake_send(*, line_user_id: str, reply_token: str | None, text: str | None = None, quick_reply=None, flex_message=None, messages=None) -> str:
        captured["reply_token"] = reply_token or ""
        captured["text"] = text or ""
        return "reply"

    async def fake_route(provider, text: str, *, open_draft_present: bool) -> tuple[str, float]:
        return "nutrition_or_food_qa", 0.95

    monkeypatch.setattr(route_module, "send_line_response", fake_send)
    monkeypatch.setattr(route_module, "verify_line_signature", lambda body, signature: True)
    monkeypatch.setattr(route_module, "_route_text_task_hybrid", fake_route)
    monkeypatch.setattr(background_jobs, "SessionLocal", db_session_factory)

    response = client.post(
        "/webhooks/line",
        json={
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "timestamp": 12345,
                    "source": {"userId": "test-user"},
                    "message": {
                        "id": "message-1",
                        "type": "text",
                        "text": "How many calories does 2 hours of dance burn?",
                    },
                }
            ]
        },
    )

    assert response.status_code == 200
    background_jobs.process_inbound_events_once(limit=5)
    assert captured["reply_token"] == "reply-token"
    assert "490-910 kcal" in captured["text"]
