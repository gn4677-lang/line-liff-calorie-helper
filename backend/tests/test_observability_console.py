from __future__ import annotations

import uuid

from app.models import MemoryHypothesis, MemorySignal, ReportingBias, ReviewQueueItem, User
from app.services.observability import (
    create_conversation_trace,
    finish_task_run,
    record_error_event,
    record_feedback_event,
    record_unknown_case_event,
    start_task_run,
)


def _get_user(db):
    return db.query(User).filter_by(line_user_id="test-user").one()


def test_unknown_and_error_events_enqueue_review_queue(client, db_session_factory, admin_headers):
    with db_session_factory() as db:
        user = _get_user(db)
        trace_id = str(uuid.uuid4())
        create_conversation_trace(
            db,
            trace_id=trace_id,
            user_id=user.id,
            line_user_id=user.line_user_id,
            surface="chat",
            task_family="nutrition_or_food_qa",
            input_text="mystery alien food",
        )
        task_run_id = start_task_run(db, trace_id=trace_id, user_id=user.id, task_family="nutrition_or_food_qa")
        record_unknown_case_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            task_family="nutrition_or_food_qa",
            unknown_type="unknown_nutrition_fact",
            raw_query="mystery alien food",
            current_answer="I do not know yet.",
            suggested_research_area="nutrition_or_brand_card",
        )
        record_error_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            component="background_worker",
            operation="menu_precision",
            severity="critical",
            error_code="job_retry_exhausted",
            message="retry cap hit",
            retry_count=3,
            fallback_used=False,
            user_visible_impact="silent_background_failure",
        )

    response = client.get("/api/observability/review-queue", headers=admin_headers)
    assert response.status_code == 200
    review_queue = response.json()["payload"]["review_queue"]
    queue_types = {item["queue_type"] for item in review_queue}
    assert "unknown_case" in queue_types
    assert "operational_error" in queue_types


def test_metrics_endpoint_and_alert_evaluation(client, db_session_factory, admin_headers):
    with db_session_factory() as db:
        user = _get_user(db)
        for index in range(5):
            trace_id = str(uuid.uuid4())
            create_conversation_trace(
                db,
                trace_id=trace_id,
                user_id=user.id,
                line_user_id=user.line_user_id,
                surface="chat",
                task_family="meal_log_now",
                input_text=f"meal {index}",
            )
            task_run_id = start_task_run(db, trace_id=trace_id, user_id=user.id, task_family="meal_log_now")
            finish_task_run(db, task_run_id, status="fallback" if index < 3 else "success")

    metrics_response = client.get("/api/observability/metrics?window_hours=168", headers=admin_headers)
    assert metrics_response.status_code == 200
    metrics = metrics_response.json()["payload"]["metrics"]
    fallback_metric = next(item for item in metrics if item["metric_key"] == "task_fallback_rate" and item["task_family"] == "meal_log_now")
    assert fallback_metric["value"] >= 0.6

    alert_response = client.post("/api/observability/alerts/evaluate", headers=admin_headers)
    assert alert_response.status_code == 200
    alerts = alert_response.json()["payload"]["alerts"]
    assert any(alert["metric_key"] == "task_fallback_rate" for alert in alerts)

    review_response = client.get("/api/observability/review-queue?queue_type=alert", headers=admin_headers)
    assert review_response.status_code == 200
    assert review_response.json()["payload"]["review_queue"]


def test_review_queue_status_update(client, db_session_factory, admin_headers):
    with db_session_factory() as db:
        user = _get_user(db)
        trace_id = str(uuid.uuid4())
        create_conversation_trace(
            db,
            trace_id=trace_id,
            user_id=user.id,
            line_user_id=user.line_user_id,
            surface="chat",
            task_family="nutrition_or_food_qa",
            input_text="unknown item",
        )
        task_run_id = start_task_run(db, trace_id=trace_id, user_id=user.id, task_family="nutrition_or_food_qa")
        record_unknown_case_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            task_family="nutrition_or_food_qa",
            unknown_type="unknown_food",
            raw_query="unknown item",
            current_answer="not found",
            suggested_research_area="food_catalog",
        )
        item = db.query(ReviewQueueItem).filter_by(source_table="unknown_case_events").order_by(ReviewQueueItem.id.desc()).first()
        item_id = item.id

    update_response = client.post(
        f"/api/observability/review-queue/{item_id}/status",
        json={"status": "triaged", "notes": "Need food card", "assigned_to": "ops"},
        headers=admin_headers,
    )
    assert update_response.status_code == 200
    review_item = update_response.json()["payload"]["review_item"]
    assert review_item["status"] == "triaged"
    assert review_item["assigned_to"] == "ops"


def test_observability_dashboard_includes_usage_and_memory_panels(client, db_session_factory, admin_headers):
    with db_session_factory() as db:
        user = _get_user(db)
        trace_id = str(uuid.uuid4())
        create_conversation_trace(
            db,
            trace_id=trace_id,
            user_id=user.id,
            line_user_id=user.line_user_id,
            surface="chat",
            task_family="meal_log_now",
            input_text="雞胸便當",
        )
        task_run_id = start_task_run(
            db,
            trace_id=trace_id,
            user_id=user.id,
            task_family="meal_log_now",
            provider_name="BuilderSpaceProvider",
            model_name="gpt-5",
        )
        finish_task_run(db, task_run_id, status="success")
        record_feedback_event(
            db,
            trace_id=trace_id,
            user_id=user.id,
            target_trace_id=trace_id,
            feedback_type="explicit_negative",
            feedback_label="wrong_answer",
            free_text="這次不準",
            severity="high",
        )
        db.add(
            MemorySignal(
                user_id=user.id,
                pattern_type="food_repeat",
                dimension="food",
                canonical_label="雞胸便當",
                source="behavior_inferred",
                evidence_count=4,
                evidence_score=5.5,
                status="stable",
            )
        )
        db.add(
            MemoryHypothesis(
                user_id=user.id,
                dimension="meal_structure",
                label="high_protein_lunch",
                statement="Lunch trends high protein.",
                source="behavior_inferred",
                confidence=0.82,
                evidence_count=4,
                status="active",
            )
        )
        bias = db.query(ReportingBias).filter_by(user_id=user.id).one_or_none()
        if bias is None:
            bias = ReportingBias(user_id=user.id)
            db.add(bias)
        bias.vagueness_score = 0.3
        bias.missing_detail_score = 0.2
        bias.log_confidence_score = 0.85
        db.commit()

    response = client.get("/api/observability/dashboard?window_hours=168&trend_days=7", headers=admin_headers)
    assert response.status_code == 200
    dashboard = response.json()["payload"]["dashboard"]
    assert dashboard["summary_cards"]
    assert "usage_panels" in dashboard
    assert "memory_panels" in dashboard
    assert dashboard["usage_panels"]["provider_request_counts"]
    assert dashboard["memory_panels"]["summary"]["total_signals"] >= 1
    assert dashboard["memory_panels"]["top_hypotheses"]


def test_observability_dashboard_exposes_route_policy_and_cache_breakdowns(client, db_session_factory, admin_headers):
    with db_session_factory() as db:
        user = _get_user(db)
        for index, summary in enumerate(
            [
                {
                    "provider_name": "BuilderSpaceProvider",
                    "model_name": "supermind-agent-v1",
                    "result_summary": {
                        "route_policy": "builderspace_text",
                        "route_target": "builderspace",
                        "llm_cache": "miss",
                    },
                },
                {
                    "provider_name": "BuilderSpaceProvider",
                    "model_name": "supermind-agent-v1",
                    "result_summary": {
                        "route_policy": "builderspace_text",
                        "route_target": "builderspace",
                        "llm_cache": "hit",
                    },
                },
                {
                    "provider_name": "HeuristicProvider",
                    "model_name": "heuristic",
                    "result_summary": {
                        "route_policy": "heuristic_grounded_text",
                        "route_target": "heuristic",
                        "llm_cache": "bypassed",
                    },
                },
            ]
        ):
            trace_id = str(uuid.uuid4())
            create_conversation_trace(
                db,
                trace_id=trace_id,
                user_id=user.id,
                line_user_id=user.line_user_id,
                surface="chat",
                task_family="meal_log_now",
                input_text=f"route sample {index}",
            )
            task_run_id = start_task_run(
                db,
                trace_id=trace_id,
                user_id=user.id,
                task_family="meal_log_now",
                provider_name=summary["provider_name"],
                model_name=summary["model_name"],
            )
            finish_task_run(db, task_run_id, status="success", result_summary=summary["result_summary"])

    response = client.get("/api/observability/dashboard?window_hours=168&trend_days=7", headers=admin_headers)
    assert response.status_code == 200
    usage = response.json()["payload"]["dashboard"]["usage_panels"]
    assert any(row["label"] == "builderspace_text" and row["count"] >= 2 for row in usage["route_policy_breakdown"])
    assert any(row["label"] == "hit" and row["count"] >= 1 for row in usage["llm_cache_breakdown"])
    assert any(row["label"] == "heuristic" and row["count"] >= 1 for row in usage["route_target_breakdown"])
    assert usage["llm_path_summary"]["saved_local_requests"] >= 1
    assert usage["llm_path_summary"]["remote_llm_requests"] >= 2
    assert usage["llm_path_summary"]["cache_hits"] >= 1


def test_observability_trace_list_exposes_route_policy_and_cache_filters(client, db_session_factory, admin_headers):
    with db_session_factory() as db:
        user = _get_user(db)
        trace_id = str(uuid.uuid4())
        create_conversation_trace(
            db,
            trace_id=trace_id,
            user_id=user.id,
            line_user_id=user.line_user_id,
            surface="chat",
            task_family="meal_log_now",
            input_text="trace filter sample",
        )
        task_run_id = start_task_run(
            db,
            trace_id=trace_id,
            user_id=user.id,
            task_family="meal_log_now",
            provider_name="BuilderSpaceProvider",
            model_name="supermind-agent-v1",
        )
        finish_task_run(
            db,
            task_run_id,
            status="success",
            result_summary={
                "route_policy": "builderspace_text",
                "route_target": "builderspace",
                "llm_cache": "hit",
            },
        )

    response = client.get(
        "/api/observability/traces?route_policy=builderspace_text&llm_cache=hit&limit=20",
        headers=admin_headers,
    )
    assert response.status_code == 200
    items = response.json()["payload"]["items"]
    assert items
    assert items[0]["route_policy"] == "builderspace_text"
    assert items[0]["route_target"] == "builderspace"
    assert items[0]["llm_cache"] == "hit"
