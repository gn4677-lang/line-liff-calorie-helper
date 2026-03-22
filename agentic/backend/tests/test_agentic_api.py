from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import importlib
import uuid

import pytest

from backend.app.models import MealDraft, MealLog, User


pytestmark = pytest.mark.agentic


def _headers() -> dict[str, str]:
    return {"x-line-user-id": "agentic-demo-user", "x-display-name": "Agentic Demo"}


def test_me_bootstrap_and_home_payload(client, db_session, agentic_env) -> None:
    me = client.get("/api/me", headers=_headers())
    assert me.status_code == 200
    me_payload = me.json()
    assert me_payload["cohort"] == "canary"
    assert me_payload["core_version"] == "agentic"

    home = client.get("/api/home/today", headers=_headers())
    assert home.status_code == 200
    payload = home.json()
    assert payload["persona"] == "calm_coach_partner"
    assert payload["state"]["goal_state"]["primary_goal"] is not None
    assert "conversation_state" in payload["state"]

    user_id = me_payload["user_id"]
    snapshots = agentic_env["store"].AgenticStore().latest_state_snapshot(db_session, user_id)
    assert snapshots is not None


def test_agent_turn_heuristic_fallback_and_observability(client) -> None:
    response = client.post(
        "/api/agent/turn",
        headers=_headers(),
        json={
            "source": "liff_turn",
            "modalities": ["text"],
            "text": "我昨天吃太多了，今晚想清淡一點",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    primary_intent = payload["turn"]["understanding"]["primary_intent"]
    assert "dinner" in primary_intent or "guidance" in primary_intent or primary_intent == "recommend_food"
    assert payload["turn"]["response"]["message_text"]
    chain = payload["telemetry"]["provider_fallback_chain"]
    assert chain[0] == "builderspace"
    assert "heuristic" in chain

    traces = client.get("/api/observability/turns", headers=_headers())
    assert traces.status_code == 200
    trace_payload = traces.json()[0]
    assert trace_payload["telemetry"]["trace_id"]
    assert "provider_fallback_chain" in trace_payload["telemetry"]


def test_structured_provider_path_overrides_heuristic(client, agentic_env, monkeypatch) -> None:
    contracts = agentic_env["contracts"]
    providers = importlib.import_module("agentic.backend.app.providers")

    def fake_complete(model, **_: object):
        if model is contracts.AgentIntent:
            return providers.StructuredCallResult(
                payload=contracts.AgentIntent(
                    primary_intent="future_event",
                    secondary_intents=["support"],
                    subtext=[],
                    entities={"meal_type": "dinner"},
                    urgency=0.88,
                    confidence=0.91,
                    needs_followup=True,
                    suggested_surface=contracts.DeliverySurface.liff,
                ),
                provider_name="builderspace",
                model_name="router",
                prompt_version="test",
                usage={},
            )
        return providers.StructuredCallResult(
            payload=None,
            provider_name="builderspace",
            model_name="router",
            prompt_version="test",
            usage={},
            fallback_reason="no_stub",
        )

    monkeypatch.setattr(agentic_env["runtime"].agent_loop.provider, "complete_structured", fake_complete)
    response = client.post(
        "/api/agent/turn",
        headers=_headers(),
        json={
            "source": "liff_turn",
            "modalities": ["text"],
            "text": "下週五晚上我要聚餐",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["turn"]["understanding"]["primary_intent"] == "future_event"


def test_plan_respond_delivery_use_stable_builderspace_request_shape(client, agentic_env, monkeypatch) -> None:
    contracts = agentic_env["contracts"]
    providers = importlib.import_module("agentic.backend.app.providers")
    captured: list[tuple[str, dict[str, object]]] = []

    def fake_complete(model, **kwargs: object):
        captured.append((model.__name__, dict(kwargs)))
        if model is contracts.AgentIntent:
            return providers.StructuredCallResult(
                payload=contracts.AgentIntent(
                    primary_intent="seek_guidance",
                    secondary_intents=["support"],
                    subtext=[contracts.SubtextCategory.uncertainty],
                    entities={},
                    urgency=0.72,
                    confidence=0.91,
                    needs_followup=False,
                    suggested_surface=contracts.DeliverySurface.liff,
                ),
                provider_name="builderspace",
                model_name="gpt-5",
                prompt_version="test-understand",
                usage={},
            )
        if model is contracts.AgentPlan:
            return providers.StructuredCallResult(
                payload=contracts.AgentPlan(
                    actions=[contracts.AgentAction(kind=contracts.AgentActionKind.propose_recovery)],
                    requires_confirmation=False,
                    decision_home=contracts.DecisionHome.progress,
                    delivery_surface=contracts.DeliverySurface.liff,
                    context_used=["goal_state"],
                    goal_alignment={"primary_goal": 0.81},
                    policy_reasons=["test-plan"],
                ),
                provider_name="builderspace",
                model_name="deepseek",
                prompt_version="test-plan",
                usage={},
            )
        if model is contracts.AgentResponse:
            return providers.StructuredCallResult(
                payload=contracts.AgentResponse(
                    message_text="先把今天收穩就好。",
                    followup_question="要我幫你看晚餐還是恢復方案？",
                    quick_replies=["晚餐", "恢復方案"],
                    deep_link="/progress",
                    tone_profile=contracts.ToneProfile.calm_coach_partner,
                ),
                provider_name="builderspace",
                model_name="supermind-agent-v1",
                prompt_version="test-respond",
                usage={},
            )
        if model is contracts.DeliveryDecision:
            return providers.StructuredCallResult(
                payload=contracts.DeliveryDecision(
                    importance=0.3,
                    urgency=0.2,
                    why_now="No proactive delivery is needed for this test turn.",
                    should_send=False,
                    suppress_reason="test",
                    delivery_surface=contracts.DeliverySurface.none,
                    decision_home=contracts.DecisionHome.none,
                    delivery_action=contracts.DeliveryAction.suppress,
                ),
                provider_name="builderspace",
                model_name="deepseek",
                prompt_version="test-delivery",
                usage={},
            )
        return providers.StructuredCallResult(
            payload=None,
            provider_name="builderspace",
            model_name="unknown",
            prompt_version="test",
            usage={},
            fallback_reason="no_stub",
        )

    monkeypatch.setattr(agentic_env["runtime"].agent_loop.provider, "complete_structured", fake_complete)
    response = client.post(
        "/api/agent/turn",
        headers=_headers(),
        json={
            "source": "liff_turn",
            "modalities": ["text"],
            "text": "我昨天吃太多了，今天怎麼收比較好？",
        },
    )
    assert response.status_code == 200

    by_model = {name: kwargs for name, kwargs in captured}
    plan_call = by_model["AgentPlan"]
    respond_call = by_model["AgentResponse"]
    delivery_call = by_model["DeliveryDecision"]

    assert plan_call["model_hint"] == "router"
    assert respond_call["model_hint"] == "chat"
    assert delivery_call["model_hint"] == "router"

    for stage_name, call in {
        "plan": plan_call,
        "respond": respond_call,
        "delivery": delivery_call,
    }.items():
        request_options = call["request_options"]
        assert request_options["response_format"] == {"type": "json_object"}
        assert request_options["tool_choice"] == "none"
        assert request_options["metadata"]["agentic_stage"] == stage_name
        assert request_options["metadata"]["prompt_version"]


def test_understand_empty_response_retries_router_before_heuristic(client, agentic_env, monkeypatch) -> None:
    contracts = agentic_env["contracts"]
    providers = importlib.import_module("agentic.backend.app.providers")
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_complete(model, **kwargs: object):
        calls.append((model.__name__, dict(kwargs)))
        if model is contracts.AgentIntent and kwargs.get("model_hint") == "frontier":
            return providers.StructuredCallResult(
                payload=None,
                provider_name="builderspace",
                model_name="gpt-5",
                prompt_version="test-understand",
                usage={},
                fallback_reason="empty_response",
            )
        if model is contracts.AgentIntent and kwargs.get("model_hint") == "router":
            return providers.StructuredCallResult(
                payload=contracts.AgentIntent(
                    primary_intent="seek_guidance",
                    secondary_intents=["support"],
                    subtext=[contracts.SubtextCategory.uncertainty],
                    entities={},
                    urgency=0.66,
                    confidence=0.88,
                    needs_followup=False,
                    suggested_surface=contracts.DeliverySurface.liff,
                ),
                provider_name="builderspace",
                model_name="deepseek",
                prompt_version="test-understand-retry",
                usage={},
            )
        return providers.StructuredCallResult(
            payload=None,
            provider_name="builderspace",
            model_name="unknown",
            prompt_version="test",
            usage={},
            fallback_reason="no_stub",
        )

    monkeypatch.setattr(agentic_env["runtime"].agent_loop.provider, "complete_structured", fake_complete)
    response = client.post(
        "/api/agent/turn",
        headers=_headers(),
        json={
            "source": "liff_turn",
            "modalities": ["text"],
            "text": "我昨天吃太多了，今天怎麼收比較好？",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["turn"]["understanding"]["primary_intent"] == "seek_guidance"
    assert payload["telemetry"]["provider_fallback_chain"][:3] == ["builderspace", "builderspace-retry", "heuristic"][: len(payload["telemetry"]["provider_fallback_chain"])]
    intent_calls = [item for item in calls if item[0] == "AgentIntent"]
    assert len(intent_calls) == 2
    assert intent_calls[0][1]["model_hint"] == "frontier"
    assert intent_calls[1][1]["model_hint"] == "router"


def test_settings_onboarding_and_decision_mutations_share_guardrails(client) -> None:
    settings_response = client.post(
        "/api/settings/preferences",
        headers=_headers(),
        json={"updates": {"constraints": ["avoid_coriander"]}, "confirmed": True},
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["guardrail_policy"] == "require_confirmation"

    onboarding_response = client.post(
        "/api/onboarding/complete",
        headers=_headers(),
        json={"primary_goal": "weight_loss", "constraints": ["avoid_coriander"], "confirmed": True},
    )
    assert onboarding_response.status_code == 200
    assert onboarding_response.json()["guardrail_policy"] == "allow_without_confirmation"

    apply_response = client.post(
        "/api/decisions/apply",
        headers=_headers(),
        json={"action": "apply", "entity_ref": "job-1", "option_key": "confirm", "confirmed": True},
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "applied"

    dismiss_response = client.post(
        "/api/decisions/dismiss",
        headers=_headers(),
        json={"action": "dismiss", "entity_ref": "job-1", "option_key": "skip", "confirmed": True},
    )
    assert dismiss_response.status_code == 200
    assert dismiss_response.json()["status"] == "dismissed"


def test_webhook_ack_fast_and_worker_processes_canary_event(agentic_env, client, db_session, monkeypatch) -> None:
    sent: list[dict[str, object]] = []
    routes = importlib.import_module("agentic.backend.app.routes")

    async def fake_send_line_response(**kwargs):
        sent.append(kwargs)
        return "reply"

    monkeypatch.setattr(agentic_env["worker"], "send_line_response", fake_send_line_response)
    monkeypatch.setattr(routes, "verify_line_signature", lambda body, signature: True)
    response = client.post(
        "/webhooks/line",
        json={
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-1",
                    "message": {"id": "m1", "type": "text", "text": "我今天晚餐要吃什麼？"},
                    "source": {"userId": "agentic-demo-user"},
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["ingress_mode"] == "ack_fast"
    assert response.json()["accepted"] == 1

    agentic_env["worker"].process_inbound_events_once(limit=1)
    assert sent
    assert "line_user_id" in sent[0]


def test_scheduled_scan_persists_and_delivers_proactive(agentic_env, client, db_session, monkeypatch) -> None:
    client.get("/api/me", headers=_headers())
    agent_models = importlib.import_module("agentic.backend.app.models")
    agentic_env["worker"]._processed_scan_keys.clear()
    user = db_session.query(User).filter(User.line_user_id == "agentic-demo-user").one()
    db_session.query(agent_models.AgentDeliveryRecord).filter(agent_models.AgentDeliveryRecord.user_id == user.id).delete()
    db_session.query(agent_models.AgentTurnRecord).filter(agent_models.AgentTurnRecord.user_id == user.id).delete()
    db_session.commit()
    draft = MealDraft(
        id=str(uuid.uuid4()),
        user_id=user.id,
        meal_session_id=str(uuid.uuid4()),
        date=date.today(),
        event_at=datetime.now(timezone.utc),
        meal_type="dinner",
        status="ready_to_confirm",
        raw_input_text="雞肉沙拉",
        source_mode="text",
    )
    db_session.add(draft)
    db_session.commit()

    sent: list[dict[str, object]] = []

    async def fake_send_line_response(**kwargs):
        sent.append(kwargs)
        return "push"

    monkeypatch.setattr(agentic_env["worker"], "send_line_response", fake_send_line_response)
    first = agentic_env["worker"].process_scheduled_scans_once(
        now=agentic_env["contracts"].utc_now().replace(hour=17, minute=30),
        limit_users=4,
    )
    second = agentic_env["worker"].process_scheduled_scans_once(
        now=agentic_env["contracts"].utc_now().replace(hour=17, minute=30),
        limit_users=4,
    )

    assert first >= 1
    assert second == 0
    assert sent
    traces = client.get("/api/observability/turns", headers=_headers())
    assert traces.status_code == 200
    payloads = traces.json()
    assert any(item["turn"]["input"]["source"] == "system_trigger" for item in payloads)


def test_provider_failure_chain_records_safe_fallback(client, agentic_env, monkeypatch) -> None:
    providers = importlib.import_module("agentic.backend.app.providers")

    def fail_complete(*args, **kwargs):
        return providers.StructuredCallResult(
            payload=None,
            provider_name="builderspace",
            model_name="frontier",
            prompt_version="test",
            usage={},
            fallback_reason="timeout",
        )

    monkeypatch.setattr(agentic_env["runtime"].agent_loop.provider, "complete_structured", fail_complete)
    response = client.post(
        "/api/agent/turn",
        headers=_headers(),
        json={"source": "liff_turn", "modalities": ["text"], "text": "今天剩多少熱量？"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["telemetry"]["provider_fallback_chain"][:2] == ["builderspace", "heuristic"]


def test_cohort_gate_and_rollback_path(agentic_env) -> None:
    cohort = agentic_env["cohort"]
    settings = importlib.import_module("agentic.backend.app.config").get_settings()
    settings.canary_allowlist = "42"
    assert cohort.decide_agentic_cohort(user_id=42).enabled is True
    settings.canary_allowlist = ""
    settings.rollout_pct = 0
    assert cohort.decide_agentic_cohort(user_id=42).enabled is False


def test_concurrent_requests_do_not_break_turn_persistence(client) -> None:
    def send_turn(text: str) -> int:
        response = client.post(
            "/api/agent/turn",
            headers=_headers(),
            json={"source": "liff_turn", "modalities": ["text"], "text": text},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(send_turn, ["幫我推薦晚餐", "我昨天吃太多了"]))
    assert statuses == [200, 200]


def test_worker_due_windows_match_spec(agentic_env) -> None:
    worker = agentic_env["worker"].AgenticWorker()
    due = worker.due_windows(agentic_env["contracts"].utc_now().replace(hour=17, minute=30))
    assert [item.label for item in due] == ["dinner_window"]


def test_memory_refresh_promotes_behavior_family_to_stable(client, db_session) -> None:
    client.get("/api/me", headers=_headers())
    user = db_session.query(User).filter(User.line_user_id == "agentic-demo-user").one()
    today = date.today()
    for index in range(5):
        db_session.add(
            MealLog(
                user_id=user.id,
                meal_session_id=f"session-{index if index < 3 else index - 2}",
                date=today if index < 3 else today - timedelta(days=8),
                event_at=datetime.now(timezone.utc) - timedelta(days=0 if index < 3 else 8),
                meal_type="dinner",
                description_raw="Chicken salad",
                parsed_items=[{"name": "Chicken Salad"}],
                kcal_estimate=520,
                kcal_low=480,
                kcal_high=560,
            )
        )
    db_session.commit()

    response = client.post(
        "/api/agent/turn",
        headers=_headers(),
        json={"source": "liff_turn", "modalities": ["text"], "text": "Recommend dinner"},
    )
    assert response.status_code == 200

    agent_models = importlib.import_module("agentic.backend.app.models")
    family = (
        db_session.query(agent_models.AgentMemoryFamilyRecord)
        .filter(
            agent_models.AgentMemoryFamilyRecord.user_id == user.id,
            agent_models.AgentMemoryFamilyRecord.dimension == "meal_history",
            agent_models.AgentMemoryFamilyRecord.label == "Chicken Salad",
        )
        .one()
    )
    evidence_rows = (
        db_session.query(agent_models.AgentMemoryEvidenceRecord)
        .filter(
            agent_models.AgentMemoryEvidenceRecord.user_id == user.id,
            agent_models.AgentMemoryEvidenceRecord.family_id == family.id,
        )
        .all()
    )
    assert family.promotion_score >= 0.9
    assert family.status == "stable"
    assert family.evidence_count == 5
    assert len(evidence_rows) == 5
    assert all(row.source_ref for row in evidence_rows)


def test_memory_refresh_decays_and_archives_stale_behavior_family(client, db_session) -> None:
    client.get("/api/me", headers=_headers())
    user = db_session.query(User).filter(User.line_user_id == "agentic-demo-user").one()
    agent_models = importlib.import_module("agentic.backend.app.models")
    db_session.add(
        agent_models.AgentMemoryFamilyRecord(
            user_id=user.id,
            dimension="meal_history",
            label="Old Favorite",
            source="behavior_inferred",
            status="stable",
            weight=0.09,
            promotion_score=0.9,
            evidence_count=4,
            counter_evidence_count=0,
            first_evidence_at=datetime.now(timezone.utc) - timedelta(days=140),
            last_evidence_at=datetime.now(timezone.utc) - timedelta(days=100),
            payload={"supporting_logs": 4},
        )
    )
    db_session.commit()

    response = client.post(
        "/api/agent/turn",
        headers=_headers(),
        json={"source": "liff_turn", "modalities": ["text"], "text": "How many kcal are left today?"},
    )
    assert response.status_code == 200

    archived = (
        db_session.query(agent_models.AgentMemoryFamilyRecord)
        .filter(
            agent_models.AgentMemoryFamilyRecord.user_id == user.id,
            agent_models.AgentMemoryFamilyRecord.dimension == "meal_history",
            agent_models.AgentMemoryFamilyRecord.label == "Old Favorite",
        )
        .one()
    )
    assert archived.status == "archived"
    assert archived.weight < 0.1
