from __future__ import annotations

import asyncio
from datetime import date

import pytest

from app.models import Food, MemoryHypothesis, User
from app.providers.base import EstimateResult
from app.providers.builderspace import BuilderSpaceProvider
from app.providers.factory import get_ai_provider
from app.schemas import EatFeedRequest
from app.services.confirmation import decide_confirmation
from app.services.eat_feed import _choose_chip_ids
from app.services.llm_support import complete_structured_sync
from app.services.memory import synthesize_hypotheses
from app.services import video_intake
from app.config import settings

pytestmark = pytest.mark.agentic


def _test_user(db):
    return db.query(User).filter_by(line_user_id="test-user").one()


def _basic_estimate(*, source_mode: str = "text") -> EstimateResult:
    return EstimateResult(
        parsed_items=[{"name": "test meal", "kcal": 480}],
        estimate_kcal=480,
        kcal_low=420,
        kcal_high=560,
        confidence=0.7,
        missing_slots=[],
        followup_question=None,
        uncertainty_note="",
        status="ready_to_confirm",
        evidence_slots={
            "source_mode": source_mode,
            "identified_items": True,
            "portion_signal": True,
            "high_calorie_modifiers": True,
        },
        comparison_candidates=[],
        ambiguity_flags=[],
    )


def test_intake_route_passes_memory_packet_and_communication_profile(client, monkeypatch):
    provider = get_ai_provider()
    captured = {}

    async def fake_estimate_meal(**kwargs):
        captured.update(kwargs)
        return _basic_estimate()

    monkeypatch.setattr(provider, "estimate_meal", fake_estimate_meal)

    response = client.post(
        "/api/intake",
        json={"text": "chicken rice box", "meal_type": "lunch", "mode": "standard"},
    )

    assert response.status_code == 200
    assert captured["memory_packet"]["reporting_bias"]["log_confidence_score"] == 1.0
    assert captured["communication_profile"]["confirmation_style"] == "auto_record_high_confidence"


def test_recommendations_route_uses_llm_rerank_and_memory_packet(client, db_session_factory, monkeypatch):
    with db_session_factory() as db:
        user = _test_user(db)
        first = Food(user_id=user.id, name="Alpha Bowl", meal_types=["lunch"], kcal_low=430, kcal_high=520, is_favorite=True)
        second = Food(user_id=user.id, name="Bravo Bowl", meal_types=["lunch"], kcal_low=440, kcal_high=510, is_favorite=True)
        db.add_all([first, second])
        db.commit()
        db.refresh(first)
        db.refresh(second)
        bravo_key = f"food:{second.id}"

    provider = get_ai_provider()
    captured = {}

    async def fake_complete_structured(*, system_prompt, user_payload, **kwargs):
        if "Rerank a bounded shortlist of meal candidates" in system_prompt:
            captured["recommendations"] = user_payload
            return {
                "ordered_keys": [bravo_key],
                "reason_factors": {bravo_key: ["LLM reranked this option first."]},
                "hero_reason": "LLM hero recommendation",
                "coach_message": "LLM says this is the best lunch fit right now.",
                "strategy_label": "protein_anchor",
            }
        return {}

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(provider, "complete_structured", fake_complete_structured)

    response = client.get("/api/recommendations", params={"meal_type": "lunch"})

    assert response.status_code == 200
    body = response.json()["recommendations"]
    assert body["items"][0]["name"] == "Bravo Bowl"
    assert body["hero_reason"] == "LLM hero recommendation"
    assert body["coach_message"] == "LLM says this is the best lunch fit right now."
    assert body["strategy_label"] == "protein_anchor"
    assert body["policy_contract"]["strategy_label"] == "protein_anchor"
    assert body["policy_contract"]["ordered_keys"] == [bravo_key]
    assert response.json()["coach_message"] == "LLM says this is the best lunch fit right now."
    assert captured["recommendations"]["memory_packet"]["communication_profile"]["detail_level"] == "compact"


def test_day_plan_route_uses_llm_personalization(client, monkeypatch):
    provider = get_ai_provider()
    captured = {}

    async def fake_complete_structured(*, system_prompt, user_payload, **kwargs):
        if "Adjust a day meal-allocation plan" in system_prompt:
            captured["day_plan_allocations"] = user_payload
            return {
                "allocations": {"breakfast": 250, "lunch": 620, "dinner": 690, "flex": 240},
            }
        if "Write the final coaching copy for one day meal-allocation plan" in system_prompt:
            captured["day_plan_copy"] = user_payload
            return {
                "coach_message": "LLM day plan message",
                "reason_factors": ["Shifted more room to dinner."],
            }
        return {}

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(provider, "complete_structured", fake_complete_structured)

    response = client.post("/api/plans/day", json={"apply_overlay": False})

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["allocations"] == {"breakfast": 250, "lunch": 620, "dinner": 690, "flex": 240}
    assert plan["coach_message"] == "LLM day plan message"
    assert captured["day_plan_allocations"]["communication_profile"]["planning_proactivity"] == "ask_first"
    assert captured["day_plan_copy"]["final_allocations"] == {"breakfast": 250, "lunch": 620, "dinner": 690, "flex": 240}


def test_compensation_plan_route_uses_llm_personalization(client, monkeypatch):
    provider = get_ai_provider()
    captured = {}

    async def fake_complete_structured(*, system_prompt, user_payload, **kwargs):
        if "Select a compensation-plan option" in system_prompt:
            captured["compensation_selection"] = user_payload
            return {
                "recommended_label": "Spread over 2-3 days",
                "option_notes": {"Spread over 2-3 days": "LLM prefers a slower recovery here."},
            }
        if "Write the final coaching copy for one compensation-plan decision" in system_prompt:
            captured["compensation_copy"] = user_payload
            return {
                "coach_message": "LLM compensation message",
                "reason_factors": ["A smoother reset keeps adherence higher."],
            }
        return {}

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(provider, "complete_structured", fake_complete_structured)

    response = client.post("/api/plans/compensation", json={"expected_extra_kcal": 600, "apply_overlay": False})

    assert response.status_code == 200
    compensation = response.json()["compensation"]
    assert compensation["coach_message"] == "LLM compensation message"
    assert compensation["options"][0]["label"] == "Spread over 2-3 days"
    assert compensation["options"][0]["note"] == "LLM prefers a slower recovery here."
    assert captured["compensation_selection"]["communication_profile"]["planning_proactivity"] == "ask_first"
    assert captured["compensation_copy"]["recommended_label"] == "Spread over 2-3 days"


def test_eat_feed_route_and_chip_picker_use_llm(client, db_session_factory, monkeypatch):
    with db_session_factory() as db:
        user = _test_user(db)
        foods = [
            Food(user_id=user.id, name="Alpha Bento", meal_types=["dinner"], kcal_low=430, kcal_high=520, is_favorite=True),
            Food(user_id=user.id, name="Bravo Soup", meal_types=["dinner"], kcal_low=380, kcal_high=470, is_favorite=True),
            Food(user_id=user.id, name="Charlie Noodles", meal_types=["dinner"], kcal_low=510, kcal_high=620, is_favorite=True),
            Food(user_id=user.id, name="Delta Bowl", meal_types=["dinner"], kcal_low=450, kcal_high=560, is_favorite=True),
        ]
        db.add_all(foods)
        db.commit()
        for item in foods:
            db.refresh(item)
        bravo_key = f"food:{foods[1].id}"

    provider = get_ai_provider()
    captured = {"chip_prompts": 0, "rerank_prompts": 0}

    async def fake_complete_structured(*, system_prompt, user_payload, **kwargs):
        if "session-only meal intent chips" in system_prompt:
            captured["chip_prompts"] += 1
            return {"ids": ["light", "comfort", "repeat_safe"]}
        if "Rerank a bounded shortlist of meal candidates" in system_prompt:
            captured["rerank_prompts"] += 1
            return {
                "ordered_keys": [bravo_key],
                "reason_factors": {bravo_key: ["LLM says the soup is the easiest fit tonight."]},
                "hero_reason": "LLM hero reason",
                "coach_message": "LLM says the nearby soup is still the cleanest fit tonight.",
            }
        return {}

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(provider, "complete_structured", fake_complete_structured)

    response = client.post(
        "/api/eat-feed",
        json={"meal_type": "dinner", "time_context": "now", "location_mode": "none"},
    )

    assert response.status_code == 200
    feed = response.json()["payload"]["eat_feed"]
    assert feed["top_pick"]["title"] == "Bravo Soup"
    assert feed["hero_reason"] == "LLM hero reason"
    assert captured["rerank_prompts"] >= 1

    # _choose_chip_ids now returns (selected_ids, provider_usage)
    selected_ids, chip_usage = _choose_chip_ids(
        [
            {"id": "light", "label": "Light", "intent_kind": "nutrition"},
            {"id": "comfort", "label": "Comfort", "intent_kind": "mood"},
            {"id": "repeat_safe", "label": "Safe", "intent_kind": "safety"},
            {"id": "nearby", "label": "Nearby", "intent_kind": "distance"},
        ],
        request=EatFeedRequest(meal_type="dinner", time_context="now", location_mode="none"),
        memory_packet={"remaining_kcal": 500, "preferences": {}, "recent_acceptance": [], "store_context_memory": []},
        provider=provider,
    )
    assert selected_ids == ["light", "comfort", "repeat_safe"]
    assert captured["chip_prompts"] >= 1
    # Verify provider_usage is now returned (was previously discarded)
    assert isinstance(chip_usage, dict), "chip_usage should be a dict with provider usage"


def test_nearby_route_uses_llm_explanation(client, monkeypatch):
    provider = get_ai_provider()

    async def fake_complete_structured(*, system_prompt, user_payload, **kwargs):
        if "Rerank a bounded shortlist of meal candidates" in system_prompt:
            return {
                "ordered_keys": [],
                "reason_factors": {},
                "hero_reason": "LLM nearby hero reason",
                "coach_message": "LLM nearby explanation",
            }
        return {}

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(provider, "complete_structured", fake_complete_structured)

    response = client.post(
        "/api/recommendations/nearby",
        json={"meal_type": "dinner", "lat": 25.03, "lng": 121.56, "query": "noodles"},
    )

    assert response.status_code == 200
    assert response.json()["coach_message"] == "LLM nearby explanation"


def test_video_refinement_wires_memory_packet_into_provider(monkeypatch):
    provider = get_ai_provider()
    captured = {}

    async def fake_estimate_meal(**kwargs):
        captured["estimate_kwargs"] = kwargs
        return _basic_estimate(source_mode="video")

    async def fake_complete_structured(*, system_prompt, user_payload, **kwargs):
        if "Review one meal-estimation result" in system_prompt:
            return {
                "confidence_delta": 0.04,
                "suggested_missing_slots": ["portion"],
                "primary_uncertainties": ["portion"],
                "suggested_question_slot": "portion",
                "suggested_followup_question": "How much of it did you finish?",
                "auto_record_ok": False,
            }
        return {}

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(provider, "estimate_meal", fake_estimate_meal)
    monkeypatch.setattr(provider, "complete_structured", fake_complete_structured)
    monkeypatch.setattr(video_intake, "extract_video_keyframes", lambda *args, **kwargs: [])
    monkeypatch.setattr(video_intake, "extract_video_transcript_sync", lambda attachment: "video transcript")
    monkeypatch.setattr(video_intake, "extract_video_ocr_hits", lambda keyframes, hint_text="": [])

    result_payload, _ = video_intake.build_video_refinement_result(
        {
            "text": "rice bowl",
            "meal_type": "lunch",
            "attachments": [{"type": "video", "mime_type": "video/mp4"}],
            "intake_memory_packet": {
                "user_stated_constraints": {
                    "communication_profile": {"detail_level": "compact", "confirmation_style": "auto_record_high_confidence"}
                },
                "reporting_bias": {"log_confidence_score": 1.0},
            },
            "communication_profile": {"detail_level": "compact", "confirmation_style": "auto_record_high_confidence"},
        }
    )

    assert captured["estimate_kwargs"]["memory_packet"]["reporting_bias"]["log_confidence_score"] == 1.0
    assert captured["estimate_kwargs"]["communication_profile"]["detail_level"] == "compact"
    assert "portion" in result_payload["missing_slots"]


def test_video_refinement_payload_includes_memory_packet(db_session_factory):
    with db_session_factory() as db:
        user = _test_user(db)
        payload = video_intake.build_video_refinement_payload(
            db=db,
            user=user,
            trace_id="trace-1",
            text="video meal",
            meal_type="dinner",
            attachments=[{"type": "video", "mime_type": "video/mp4"}],
            metadata={},
            notify_on_complete=False,
        )

    assert payload["intake_memory_packet"]["reporting_bias"]["log_confidence_score"] == 1.0
    assert payload["communication_profile"]["confirmation_style"] == "auto_record_high_confidence"


def test_memory_synthesis_adds_model_hypothesis(db_session_factory, monkeypatch):
    provider = get_ai_provider()

    async def fake_complete_structured(*, system_prompt, user_payload, **kwargs):
        if "Synthesize up to 3 cautious food-behavior hypotheses" in system_prompt:
            return {
                "hypotheses": [
                    {
                        "dimension": "meal_structure",
                        "label": "prefers_warm_food",
                        "statement": "Warm meals seem easier to sustain than cold ones.",
                        "confidence": 0.71,
                        "status": "tentative",
                        "supporting_signals": [],
                    }
                ]
            }
        return {}

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(provider, "complete_structured", fake_complete_structured)

    with db_session_factory() as db:
        user = _test_user(db)
        synthesize_hypotheses(db, user)
        row = db.query(MemoryHypothesis).filter_by(user_id=user.id, label="prefers_warm_food").one()

    assert row.source == "model_hypothesis"
    assert row.statement == "Warm meals seem easier to sustain than cold ones."


def test_confirmation_uses_llm_review_signal(db_session_factory):
    with db_session_factory() as db:
        user = _test_user(db)
        estimate = EstimateResult(
            parsed_items=[{"name": "meal", "kcal": 320}],
            estimate_kcal=320,
            kcal_low=280,
            kcal_high=360,
            confidence=0.6,
            missing_slots=[],
            followup_question=None,
            uncertainty_note="",
            status="ready_to_confirm",
            evidence_slots={
                "source_mode": "image",
                "identified_items": True,
                "llm_confidence_delta": 0.09,
                "llm_auto_record_ok": True,
            },
            comparison_candidates=[],
            ambiguity_flags=[],
        )

        decision = decide_confirmation(
            db,
            user,
            estimate=estimate,
            mode="standard",
            target_date=date.today(),
            clarification_used=0,
        )

    assert decision.confirmation_mode == "auto_recordable"
    assert decision.stop_reason == "llm_review_greenlight"


def test_intake_route_uses_llm_clarification_mode_for_comparison(client, monkeypatch):
    provider = get_ai_provider()

    async def fake_estimate_meal(**kwargs):
        return EstimateResult(
            parsed_items=[{"name": "rice bowl", "kcal": 520}],
            estimate_kcal=520,
            kcal_low=460,
            kcal_high=620,
            confidence=0.62,
            missing_slots=["portion"],
            followup_question=None,
            uncertainty_note="portion unclear",
            status="awaiting_clarification",
            evidence_slots={"source_mode": "text", "identified_items": True},
            comparison_candidates=[],
            ambiguity_flags=["portion_vague"],
        )

    async def fake_complete_structured(*, system_prompt, user_payload, **kwargs):
        if "Review one meal-estimation result" in system_prompt:
            return {
                "confidence_delta": 0.02,
                "suggested_missing_slots": ["portion"],
                "primary_uncertainties": ["portion"],
                "suggested_question_slot": "portion",
                "suggested_followup_question": "Was it about your usual size or a bit more?",
                "clarification_mode": "comparison_mode",
                "auto_record_ok": False,
                "generic_estimate_ok": False,
            }
        return {}

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(provider, "estimate_meal", fake_estimate_meal)
    monkeypatch.setattr(provider, "complete_structured", fake_complete_structured)

    response = client.post("/api/intake", json={"text": "rice bowl", "meal_type": "lunch", "mode": "standard"})

    assert response.status_code == 200
    draft = response.json()["draft"]
    assert draft["confirmation_mode"] == "needs_clarification"
    assert draft["answer_mode"] == "chips_first_with_text_fallback"
    assert draft["clarification_kind"] == "portion"
    assert draft["answer_options"]


def test_day_summary_route_uses_weekly_coaching_when_enabled(client, monkeypatch):
    provider = get_ai_provider()

    async def fake_complete_structured(*, system_prompt, user_payload, **kwargs):
        if "Interpret one deterministic weekly-calorie envelope" in system_prompt:
            return {
                "intervention_importance": "high",
                "urgency": "medium",
                "coach_message": "This week is drifting up, but a light reset over the next two days is enough.",
                "strategy_label": "gentle_reset",
                "reason_factors": ["Weekly drift is manageable if you act now."],
                "trigger_type": "weekly_drift_probe",
            }
        return {}

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(provider, "complete_structured", fake_complete_structured)

    response = client.get("/api/day-summary")

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["weekly_coach_message"] == "This week is drifting up, but a light reset over the next two days is enough."
    assert summary["weekly_strategy_label"] == "gentle_reset"
    assert summary["weekly_reason_factors"] == ["Weekly drift is manageable if you act now."]


def test_complete_structured_sync_forwards_request_options():
    captured = {}

    class FakeProvider:
        async def complete_structured(self, **kwargs):
            captured.update(kwargs)
            return {"ok": True}

    result = complete_structured_sync(
        FakeProvider(),
        system_prompt="system",
        user_payload={"hello": "world"},
        max_tokens=123,
        temperature=0.2,
        model_hint="frontier",
        request_options={"response_format": {"type": "json_object"}, "reasoning_effort": "minimal"},
    )

    assert result == {"ok": True}
    assert captured["request_options"] == {"response_format": {"type": "json_object"}, "reasoning_effort": "minimal"}
    assert captured["max_tokens"] == 123
    assert captured["model_hint"] == "frontier"


def test_builderspace_complete_structured_applies_gpt5_request_shape(monkeypatch):
    provider = BuilderSpaceProvider()
    captured = {}

    async def fake_post_json(path, *, timeout, payload=None, data=None, files=None):
        captured["path"] = path
        captured["timeout"] = timeout
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "{\"result\": \"ok\"}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(settings, "builderspace_frontier_model", "gpt-5", raising=False)
    monkeypatch.setattr(provider, "_post_json", fake_post_json)

    result = asyncio.run(
        provider.complete_structured(
            system_prompt="system",
            user_payload={"hello": "world"},
            max_tokens=140,
            temperature=0.0,
            model_hint="frontier",
            request_options={"response_format": {"type": "json_object"}, "reasoning_effort": "minimal"},
        )
    )

    assert result["result"] == "ok"
    assert captured["path"] == "/chat/completions"
    assert captured["payload"]["model"] == "gpt-5"
    assert captured["payload"]["temperature"] == 1.0
    assert captured["payload"]["max_tokens"] >= 1000
    assert captured["payload"]["max_completion_tokens"] == captured["payload"]["max_tokens"]
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["reasoning_effort"] == "minimal"
