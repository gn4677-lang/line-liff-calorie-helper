from __future__ import annotations

import uuid

from app.models import ConversationTrace, ErrorEvent, FeedbackEvent, OutcomeEvent, SearchJob, TaskRun, UncertaintyEvent, UnknownCaseEvent, User
from app.services.background_jobs import process_search_jobs_once


def test_intake_creates_trace_task_and_uncertainty_events(client, db_session_factory):
    response = client.post("/api/intake", json={"text": "雞胸便當 半碗飯", "mode": "standard"})
    assert response.status_code == 200
    trace_id = response.headers.get("x-trace-id")
    assert trace_id

    with db_session_factory() as db:
        trace = db.get(ConversationTrace, trace_id)
        assert trace is not None
        assert trace.task_family == "meal_log_now"

        task_run = db.query(TaskRun).filter_by(trace_id=trace_id).one()
        assert task_run.task_family == "meal_log_now"
        assert task_run.status in {"success", "partial"}

        uncertainty = db.query(UncertaintyEvent).filter_by(trace_id=trace_id).one()
        assert uncertainty.task_family == "meal_log_now"
        assert uncertainty.estimation_confidence is not None


def test_nutrition_qa_unknown_case_is_logged(client, db_session_factory):
    response = client.post(
        "/api/qa/nutrition",
        json={"question": "mystery alien food 12345", "allow_search": False},
    )
    assert response.status_code == 200
    trace_id = response.headers.get("x-trace-id")
    assert trace_id

    with db_session_factory() as db:
        task_run = db.query(TaskRun).filter_by(trace_id=trace_id).one()
        assert task_run.task_family == "nutrition_or_food_qa"

        unknown = db.query(UnknownCaseEvent).filter_by(trace_id=trace_id).one()
        assert unknown.unknown_type == "unknown_nutrition_fact"
        assert "mystery alien food" in unknown.raw_query


def test_apply_and_dismiss_search_job_log_feedback(client, db_session_factory):
    with db_session_factory() as db:
        user = db.query(User).filter_by(line_user_id="test-user").one()
        apply_job = SearchJob(
            id=str(uuid.uuid4()),
            user_id=user.id,
            job_type="menu_precision",
            status="completed",
            request_payload={"trace_id": "seed-apply"},
            suggested_update={"suggested_kcal": 540},
        )
        dismiss_job = SearchJob(
            id=str(uuid.uuid4()),
            user_id=user.id,
            job_type="menu_precision",
            status="completed",
            request_payload={"trace_id": "seed-dismiss"},
            suggested_update={"suggested_kcal": 610},
        )
        db.add(apply_job)
        db.add(dismiss_job)
        db.commit()
        apply_job_id = apply_job.id
        dismiss_job_id = dismiss_job.id

    apply_response = client.post(f"/api/search-jobs/{apply_job_id}/apply")
    dismiss_response = client.post(f"/api/search-jobs/{dismiss_job_id}/dismiss")
    assert apply_response.status_code == 200
    assert dismiss_response.status_code == 200

    apply_trace_id = apply_response.headers.get("x-trace-id")
    dismiss_trace_id = dismiss_response.headers.get("x-trace-id")

    with db_session_factory() as db:
        apply_feedback = db.query(FeedbackEvent).filter_by(trace_id=apply_trace_id).one()
        assert apply_feedback.feedback_type == "apply_suggested_update"
        apply_outcome = db.query(OutcomeEvent).filter_by(trace_id=apply_trace_id).one()
        assert apply_outcome.outcome_type == "suggested_update_applied"

        dismiss_feedback = db.query(FeedbackEvent).filter_by(trace_id=dismiss_trace_id).one()
        assert dismiss_feedback.feedback_type == "dismiss_suggested_update"
        dismiss_outcome = db.query(OutcomeEvent).filter_by(trace_id=dismiss_trace_id).one()
        assert dismiss_outcome.outcome_type == "suggested_update_dismissed"


def test_background_job_failure_logs_error_event(client, db_session_factory, monkeypatch):
    with db_session_factory() as db:
        user = db.query(User).filter_by(line_user_id="test-user").one()
        job = SearchJob(
            id=str(uuid.uuid4()),
            user_id=user.id,
            job_type="nearby_places",
            status="pending",
            request_payload={"trace_id": "trace-bg-failure", "query": "taipei 101"},
        )
        db.add(job)
        db.commit()

    def boom(_payload):
        raise RuntimeError("places lookup exploded")

    monkeypatch.setattr("app.services.background_jobs._run_nearby_places_job", boom)
    process_search_jobs_once(limit=1)

    with db_session_factory() as db:
        task_run = db.query(TaskRun).filter_by(trace_id="trace-bg-failure").one()
        assert task_run.status == "fallback"

        error = db.query(ErrorEvent).filter_by(trace_id="trace-bg-failure").one()
        assert error.component == "background_worker"
        assert error.error_code == "job_retry_pending"
        assert error.retry_count == 1
