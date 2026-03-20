from __future__ import annotations

import uuid

from app.models import MealLog, Preference, ReportingBias, SearchJob, User
from app.services import background_jobs


def _ensure_user(db_session_factory):
    with db_session_factory() as db:
        user = db.query(User).filter_by(line_user_id="test-user").first()
        if not user:
            user = User(line_user_id="test-user", display_name="Test User", daily_calorie_target=1800)
            db.add(user)
            db.flush()
            db.add(Preference(user_id=user.id))
            db.add(ReportingBias(user_id=user.id))
            db.commit()
            db.refresh(user)
        return user.id


def test_nearby_recommendations_create_job_and_use_store_memory(client):
    client.post(
        "/api/favorite-stores",
        json={
            "name": "Subway Xinyi",
            "label": "Subway",
            "place_id": "place_subway",
            "kcal_low": 380,
            "kcal_high": 520,
            "meal_types": ["lunch", "dinner"],
            "mark_golden": True,
        },
    )

    response = client.post(
        "/api/recommendations/nearby",
        json={"mode": "manual", "query": "Xinyi District", "meal_type": "dinner"},
    )

    assert response.status_code == 200
    nearby = response.json()["payload"]["nearby"]
    assert nearby["search_job_id"]
    assert len(nearby["heuristic_items"]) >= 1
    assert nearby["heuristic_items"][0]["source"] in {"golden_order", "favorite_store", "place_cache"}


def test_apply_search_job_updates_existing_log(client, db_session_factory):
    intake = client.post("/api/intake", json={"text": "subway chicken sandwich", "mode": "quick"})
    assert intake.status_code == 200
    draft_id = intake.json()["draft"]["id"]
    confirm = client.post(f"/api/intake/{draft_id}/confirm", json={"force_confirm": True})
    assert confirm.status_code == 200
    log_id = confirm.json()["log"]["id"]

    with db_session_factory() as db:
        user = db.query(User).filter_by(line_user_id="test-user").first()
        job = SearchJob(
            id=str(uuid.uuid4()),
            user_id=user.id,
            job_type="menu_precision",
            status="completed",
            suggested_update={
                "target_log_id": log_id,
                "suggested_kcal": 610,
                "suggested_range": {"low": 560, "high": 680},
                "reason": "Matched brand menu info.",
                "sources": [{"title": "Subway menu", "path": "knowledge/food_catalog_tw.json"}],
                "store_name": "Subway Xinyi",
            },
        )
        db.add(job)
        db.commit()
        job_id = job.id

    response = client.post(f"/api/search-jobs/{job_id}/apply")
    assert response.status_code == 200
    assert response.json()["payload"]["search_job"]["status"] == "applied"

    with db_session_factory() as db:
        log = db.get(MealLog, log_id)
        assert log.kcal_estimate == 610
        assert log.memory_metadata["async_update_applied"] is True
        assert log.memory_metadata["store_name"] == "Subway Xinyi"


def test_notifications_can_be_listed_and_marked_read(client, db_session_factory):
    _ensure_user(db_session_factory)
    with db_session_factory() as db:
        user = db.query(User).filter_by(line_user_id="test-user").first()
        job = SearchJob(
            id=str(uuid.uuid4()),
            user_id=user.id,
            job_type="nearby_places",
            status="completed",
            result_payload={"places": [{"name": "Store A"}]},
            notification_sent_at=None,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        background_jobs._maybe_create_job_notification(db, job)

    monkey_title = "Nearby search updated"

    listing = client.get("/api/notifications")
    assert listing.status_code == 200
    notifications = listing.json()["payload"]["notifications"]
    assert len(notifications) >= 1
    assert notifications[0]["title"] == monkey_title

    notification_id = notifications[0]["id"]
    mark = client.post(f"/api/notifications/{notification_id}/read")
    assert mark.status_code == 200
    assert mark.json()["payload"]["notification"]["status"] == "read"


def test_background_jobs_retry_cap_marks_failed(client, db_session_factory, monkeypatch):
    user_id = _ensure_user(db_session_factory)
    monkeypatch.setattr(background_jobs, "SessionLocal", db_session_factory)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(background_jobs, "build_external_food_job_result", boom)

    with db_session_factory() as db:
        job = SearchJob(
            id=str(uuid.uuid4()),
            user_id=user_id,
            job_type="external_food_check",
            status="pending",
            request_payload={"text": "mystery ig meal"},
        )
        db.add(job)
        db.commit()
        job_id = job.id

    background_jobs.process_search_jobs_once(limit=5)
    background_jobs.process_search_jobs_once(limit=5)
    background_jobs.process_search_jobs_once(limit=5)

    with db_session_factory() as db:
        job = db.get(SearchJob, job_id)
        assert job.status == "failed"
        assert job.job_retry_count == 3
        assert "boom" in job.last_error
