from __future__ import annotations

from datetime import date, timedelta

from app.api import routes
from app.main import app
from app.models import InboundEvent, MealDraft, MealLog, OutcomeEvent, SearchJob, TaskRun, User, utcnow
from app.services import background_jobs


def test_healthz_and_readyz_are_available(client):
    health = client.get("/healthz")
    ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_readyz_reports_missing_production_config(client, monkeypatch):
    monkeypatch.setattr(routes.settings, "environment", "production")
    monkeypatch.setattr(routes.settings, "ai_builder_token", None)
    monkeypatch.setattr(routes.settings, "app_base_url", None)
    monkeypatch.setattr(routes.settings, "cors_allowed_origins", "")

    response = client.get("/readyz")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["status"] == "not_ready"
    assert "AI_BUILDER_TOKEN" in detail["errors"]
    assert "APP_BASE_URL" in detail["errors"]
    assert "CORS_ALLOWED_ORIGINS" in detail["errors"]


def test_header_demo_auth_is_blocked_in_production(client, monkeypatch):
    app.dependency_overrides.pop(routes.current_user, None)
    monkeypatch.setattr(routes.settings, "environment", "production")

    response = client.get("/api/me", headers={"X-Line-User-Id": "demo-user"})

    assert response.status_code == 401
    assert response.json()["detail"] == "LINE authentication is required"


def test_line_webhook_ack_fast_queues_without_processing_inline(client, db_session_factory, monkeypatch):
    monkeypatch.setattr(routes, "verify_line_signature", lambda body, signature: True)
    monkeypatch.setattr(background_jobs, "SessionLocal", db_session_factory)
    monkeypatch.setattr(
        routes,
        "send_line_response",
        lambda **kwargs: __import__("asyncio").sleep(0, result="reply"),
    )

    with db_session_factory() as db:
        user = db.query(User).filter_by(line_user_id="test-user").one()
        draft = MealDraft(
            id="draft-ack-fast",
            user_id=user.id,
            meal_session_id="session-ack-fast",
            date=date.today(),
            event_at=utcnow(),
            meal_type="dinner",
            status="ready_to_confirm",
            raw_input_text="burger",
            source_mode="text",
            mode="standard",
            attachments=[],
            parsed_items=[{"name": "burger", "kcal": 900}],
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
                    "message": {"id": "message-ack-fast", "type": "text", "text": "ok"},
                }
            ]
        },
    )

    assert response.status_code == 200
    with db_session_factory() as db:
        assert db.query(InboundEvent).filter_by(external_event_id="message-ack-fast").count() == 1
        assert db.query(MealLog).filter_by(meal_session_id="session-ack-fast").count() == 0

    background_jobs.process_inbound_events_once(limit=5)

    with db_session_factory() as db:
        assert db.query(MealLog).filter_by(meal_session_id="session-ack-fast").count() == 1


def test_line_webhook_dedupes_same_message_id(client, db_session_factory, monkeypatch):
    monkeypatch.setattr(routes, "verify_line_signature", lambda body, signature: True)

    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "reply-token",
                "timestamp": 12345,
                "source": {"userId": "test-user"},
                "message": {"id": "message-dedupe", "type": "text", "text": "hello"},
            }
        ]
    }

    first = client.post("/webhooks/line", json=payload)
    second = client.post("/webhooks/line", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    with db_session_factory() as db:
        events = db.query(InboundEvent).filter_by(external_event_id="message-dedupe").all()
        assert len(events) == 1


def test_legacy_inline_webhook_uses_unified_processor_and_records_ingress(client, db_session_factory, monkeypatch):
    monkeypatch.setattr(routes, "verify_line_signature", lambda body, signature: True)
    monkeypatch.setattr(
        routes,
        "send_line_response",
        lambda **kwargs: __import__("asyncio").sleep(0, result="reply"),
    )

    with db_session_factory() as db:
        user = db.query(User).filter_by(line_user_id="test-user").one()
        draft = MealDraft(
            id="draft-legacy-inline",
            user_id=user.id,
            meal_session_id="session-legacy-inline",
            date=date.today(),
            event_at=utcnow(),
            meal_type="dinner",
            status="ready_to_confirm",
            raw_input_text="burger",
            source_mode="text",
            mode="standard",
            attachments=[],
            parsed_items=[{"name": "burger", "kcal": 900}],
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
        "/webhooks/line/_legacy_inline",
        json={
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-token-legacy",
                    "timestamp": 12346,
                    "source": {"userId": "test-user"},
                    "message": {"id": "message-legacy-inline", "type": "text", "text": "ok"},
                }
            ]
        },
    )

    assert response.status_code == 200
    with db_session_factory() as db:
        assert db.query(MealLog).filter_by(meal_session_id="session-legacy-inline").count() == 1
        ingress_run = (
            db.query(TaskRun)
            .filter_by(task_family="line_webhook_ingress")
            .order_by(TaskRun.started_at.desc())
            .first()
        )
        assert ingress_run is not None
        summary = ingress_run.result_summary or {}
        assert summary["ingress_mode"] == "legacy_inline"
        assert summary["enqueue_outcome"] == "processed_inline"
        outcome = (
            db.query(OutcomeEvent)
            .filter_by(trace_id=ingress_run.trace_id, outcome_type="processed_inline")
            .order_by(OutcomeEvent.created_at.desc())
            .first()
        )
        assert outcome is not None


def test_inbound_event_reclaims_expired_lease(db_session_factory, monkeypatch):
    async def fake_process(db, payload, *, trace_id: str, reply_token: str | None = None) -> None:
        return None

    monkeypatch.setattr(background_jobs, "SessionLocal", db_session_factory)
    monkeypatch.setattr(routes, "process_line_event_payload", fake_process)

    with db_session_factory() as db:
        event = InboundEvent(
            id="event-reclaim",
            source="line_webhook",
            external_event_id="message-reclaim",
            line_user_id="test-user",
            reply_token="reply-token",
            trace_id="trace-reclaim",
            payload={"type": "message", "source": {"userId": "test-user"}, "message": {"id": "message-reclaim", "type": "text", "text": "hello"}},
            status="running",
            claimed_at=utcnow() - timedelta(minutes=5),
            lease_expires_at=utcnow() - timedelta(seconds=1),
            claim_token="stale-token",
        )
        db.add(event)
        db.commit()

    background_jobs.process_inbound_events_once(limit=5)

    with db_session_factory() as db:
        event = db.get(InboundEvent, "event-reclaim")
        assert event is not None
        assert event.status == "completed"
        assert event.claim_token is None
        assert event.processed_at is not None


def test_search_job_reclaims_expired_lease(db_session_factory, monkeypatch):
    monkeypatch.setattr(background_jobs, "SessionLocal", db_session_factory)
    monkeypatch.setattr(background_jobs, "_run_external_food_job", lambda db, payload: ({"message": "ok"}, {}))

    with db_session_factory() as db:
        user = db.query(User).filter_by(line_user_id="test-user").one()
        job = SearchJob(
            id="job-reclaim",
            user_id=user.id,
            job_type="external_food_check",
            status="running",
            request_payload={"text": "check this"},
            claimed_at=utcnow() - timedelta(minutes=5),
            lease_expires_at=utcnow() - timedelta(seconds=1),
            claim_token="stale-token",
        )
        db.add(job)
        db.commit()

    background_jobs.process_search_jobs_once(limit=5)

    with db_session_factory() as db:
        job = db.get(SearchJob, "job-reclaim")
        assert job is not None
        assert job.status == "completed"
        assert job.claim_token is None
        assert job.finished_at is not None
