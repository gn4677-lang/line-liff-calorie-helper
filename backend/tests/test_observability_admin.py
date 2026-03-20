from __future__ import annotations

from datetime import date, datetime, timezone
import uuid

from app.models import ActivityAdjustment, BodyGoal, MealEvent, Notification, RecommendationProfile, RecommendationSession, User
from app.services.observability import (
    create_conversation_trace,
    finish_task_run,
    record_error_event,
    record_feedback_event,
    record_outcome_event,
    record_uncertainty_event,
    record_unknown_case_event,
    start_task_run,
)


def _get_user(db):
    return db.query(User).filter_by(line_user_id="test-user").one()


def test_admin_auth_requires_session(client):
    response = client.get("/api/observability/dashboard")
    assert response.status_code == 401


def test_admin_login_me_and_logout(client):
    login_response = client.post("/api/admin/login", json={"passcode": "test-admin-passcode", "label": "ops"})
    assert login_response.status_code == 200
    token = login_response.json()["payload"]["session"]["token"]
    headers = {"X-Admin-Session": token}

    me_response = client.get("/api/admin/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["payload"]["session"]["label"] == "ops"

    logout_response = client.post("/api/admin/logout", headers=headers)
    assert logout_response.status_code == 200

    after_logout = client.get("/api/admin/me", headers=headers)
    assert after_logout.status_code == 401


def test_trace_list_and_detail(client, db_session_factory, admin_headers):
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
            source_mode="text",
            input_text="雞腿便當半碗飯",
        )
        task_run_id = start_task_run(
            db,
            trace_id=trace_id,
            user_id=user.id,
            task_family="meal_log_now",
            route_layer_1="logging",
            route_layer_2="meal_log_now",
            provider_name="BuilderSpaceProvider",
            model_name="gpt-5",
        )
        record_uncertainty_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            task_family="meal_log_now",
            estimation_confidence=0.62,
            confirmation_calibration=0.68,
            primary_uncertainties=["rice_portion"],
            missing_slots=["rice_portion"],
            clarification_budget=2,
            clarification_used=1,
        )
        record_error_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            component="knowledge",
            operation="grounding",
            severity="error",
            error_code="local_grounding_low_confidence",
            message="low confidence grounding",
            fallback_used=True,
            user_visible_impact="degraded",
        )
        record_feedback_event(
            db,
            trace_id=trace_id,
            user_id=user.id,
            target_trace_id=trace_id,
            feedback_type="explicit_negative",
            feedback_label="wrong_answer",
            free_text="熱量怪怪的",
            severity="high",
        )
        record_unknown_case_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=user.id,
            task_family="meal_log_now",
            unknown_type="unknown_food_variant",
            raw_query="便當特殊配菜",
            current_answer="generic estimate used",
            suggested_research_area="brand_card",
        )
        record_outcome_event(
            db,
            trace_id=trace_id,
            user_id=user.id,
            task_family="meal_log_now",
            outcome_type="meal_logged",
            target_id="123",
            payload={"estimate_kcal": 620},
        )
        finish_task_run(db, task_run_id, status="partial", fallback_reason="generic portion fallback")

    list_response = client.get("/api/observability/traces?task_family=meal_log_now&has_error=true", headers=admin_headers)
    assert list_response.status_code == 200
    payload = list_response.json()["payload"]
    assert payload["items"]
    item = next(row for row in payload["items"] if row["trace_id"] == trace_id)
    assert item["has_error"] is True
    assert item["has_feedback"] is True
    assert item["has_unknown_case"] is True

    detail_response = client.get(f"/api/observability/traces/{trace_id}", headers=admin_headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()["payload"]["trace_detail"]
    assert detail["trace"]["id"] == trace_id
    assert detail["task_runs"]
    assert detail["uncertainty_events"]
    assert detail["error_events"]
    assert detail["feedback_events"]
    assert detail["unknown_case_events"]
    assert detail["outcome_events"]


def test_dashboard_includes_product_health_panels(client, db_session_factory, admin_headers):
    with db_session_factory() as db:
        user = _get_user(db)
        db.add(
            BodyGoal(
                user_id=user.id,
                target_weight_kg=65.0,
                estimated_tdee_kcal=2200,
                default_daily_deficit_kcal=400,
                calibration_confidence=0.62,
            )
        )
        db.add(
            ActivityAdjustment(
                user_id=user.id,
                date=date.today(),
                label="快走",
                estimated_burn_kcal=180,
            )
        )
        db.add(
            RecommendationProfile(
                user_id=user.id,
                sample_size=4,
                favorite_bias_strength=0.68,
            )
        )
        db.add(
            RecommendationSession(
                id=str(uuid.uuid4()),
                user_id=user.id,
                surface="eat",
                meal_type="lunch",
                shown_top_pick={"title": "Subway 雞胸潛艇堡", "source_type": "golden_order"},
                status="accepted",
                accepted_event_type="accepted_top_pick",
                accepted_candidate={"title": "Subway 雞胸潛艇堡"},
                accepted_at=datetime.now(timezone.utc),
            )
        )
        db.add(
            Notification(
                id=str(uuid.uuid4()),
                user_id=user.id,
                type="daily_nudge",
                title="今天還沒記錄",
                body="今天好像還沒記錄。",
                payload={"date": date.today().isoformat()},
            )
        )
        db.add(
            MealEvent(
                user_id=user.id,
                event_date=date.today(),
                meal_type="dinner",
                title="週五晚餐聚餐",
                expected_kcal=950,
                status="planned",
                source="manual",
            )
        )
        db.commit()

    response = client.get("/api/observability/dashboard?window_hours=168&trend_days=7", headers=admin_headers)
    assert response.status_code == 200
    dashboard = response.json()["payload"]["dashboard"]
    product = dashboard["product_panels"]
    assert product["recommendation_summary"]["sessions"] >= 1
    assert product["recommendation_summary"]["accepted_top_pick"] >= 1
    assert product["body_goal_summary"]["target_weight_users"] >= 1
    assert product["body_goal_summary"]["activity_adjustment_events"] >= 1
    assert product["proactive_summary"]["daily_nudges"] >= 1
    assert product["proactive_summary"]["meal_events_created"] >= 1
    assert product["knowledge_summary"]["pack_count"] >= 1
    assert product["knowledge_summary"]["structured_item_count"] >= 1


def test_admin_can_refresh_knowledge_layer(client, admin_headers):
    response = client.post("/api/observability/knowledge/refresh", headers=admin_headers)
    assert response.status_code == 200
    knowledge = response.json()["payload"]["knowledge"]
    assert knowledge["pack_count"] >= 1
    assert knowledge["doc_count"] >= 1
    assert knowledge["version"]
