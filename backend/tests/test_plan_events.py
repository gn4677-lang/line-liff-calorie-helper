from __future__ import annotations

from datetime import date, timedelta

from app.models import PlanEvent


def test_plan_events_empty(client):
    response = client.get("/api/plan-events")
    assert response.status_code == 200
    data = response.json()
    assert data["payload"]["plan_events"] == []


def test_plan_events_returns_upcoming(client, db_session_factory):
    db = db_session_factory()
    user = db.execute(__import__("sqlalchemy").text("SELECT id FROM users LIMIT 1")).fetchone()
    user_id = user[0]

    today = date.today()
    event = PlanEvent(
        user_id=user_id,
        date=today + timedelta(days=3),
        event_type="dinner_party",
        title="週六晚餐聚會",
        expected_extra_kcal=500,
        planning_status="planned",
        notes="跟朋友聚餐",
    )
    db.add(event)
    db.commit()
    db.close()

    response = client.get("/api/plan-events")
    assert response.status_code == 200
    items = response.json()["payload"]["plan_events"]
    assert len(items) == 1
    assert items[0]["title"] == "週六晚餐聚會"
    assert items[0]["planning_status"] == "planned"
    assert items[0]["expected_extra_kcal"] == 500


def test_plan_events_excludes_past(client, db_session_factory):
    db = db_session_factory()
    user = db.execute(__import__("sqlalchemy").text("SELECT id FROM users LIMIT 1")).fetchone()
    user_id = user[0]

    past_event = PlanEvent(
        user_id=user_id,
        date=date.today() - timedelta(days=5),
        event_type="buffet",
        title="上週 buffet",
        expected_extra_kcal=800,
    )
    far_future_event = PlanEvent(
        user_id=user_id,
        date=date.today() + timedelta(days=30),
        event_type="trip",
        title="下月旅行",
        expected_extra_kcal=600,
    )
    db.add_all([past_event, far_future_event])
    db.commit()
    db.close()

    response = client.get("/api/plan-events")
    assert response.status_code == 200
    items = response.json()["payload"]["plan_events"]
    assert len(items) == 0
