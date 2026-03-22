from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.services.inbound_events import enqueue_line_event
from backend.app.services.line import verify_line_signature

from .cohort import CohortDecision, decide_agentic_cohort
from .config import get_settings
from .contracts import (
    AgentAction,
    AgentActionKind,
    AgentInput,
    AgentInputSource,
    AgentTurnResult,
    DecisionHome,
    DecisionMutation,
    HomePayload,
    OnboardingMutation,
    PostbackPayload,
    PreferencesMutation,
    SourceMetadata,
)
from .database import get_db
from .identity import resolve_request_user
from .runtime import agent_loop, build_home_payload, state_assembler, store


router = APIRouter()
settings = get_settings()


def _cohort_for_user(user) -> CohortDecision:
    return decide_agentic_cohort(user_id=user.id, line_user_id=user.line_user_id)


def _require_agentic(user) -> CohortDecision:
    decision = _cohort_for_user(user)
    if not decision.enabled:
        raise HTTPException(status_code=409, detail={"status": "legacy_default", "reason": decision.reason})
    return decision


def _persist_processed_turn(db: Session, result: AgentTurnResult, decision: CohortDecision) -> AgentTurnResult:
    for effect in result.turn.persisted_effects:
        if not effect.before_ref:
            effect.before_ref = f"user:{result.state.identity.user_id}"
    trace_id = store.persist_turn(db, result, cohort=decision.cohort, core_version=decision.core_version)
    result.telemetry["trace_id"] = trace_id
    return result


def _goal_snapshot_payload(base_state: HomePayload | None, updates: dict[str, Any]) -> dict[str, Any]:
    goal_state = (base_state.state.goal_state.model_dump(mode="json") if base_state is not None else {})
    if updates.get("primary_goal"):
        goal_state["primary_goal"] = str(updates["primary_goal"])
    if "goal_target" in updates and isinstance(updates["goal_target"], dict):
        goal_state["goal_target"] = updates["goal_target"]
    if updates.get("goal_horizon"):
        goal_state["goal_horizon"] = str(updates["goal_horizon"])
    if isinstance(updates.get("constraints"), list):
        goal_state["constraints"] = [str(item) for item in updates["constraints"] if str(item).strip()]
    if isinstance(updates.get("strategic_context"), list):
        goal_state["strategic_context"] = [str(item) for item in updates["strategic_context"] if str(item).strip()]
    if isinstance(updates.get("priority_signals"), list):
        goal_state["priority_signals"] = [str(item) for item in updates["priority_signals"] if str(item).strip()]
    return goal_state


def _normalize_preference_updates(updates: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    preference_payload = dict(updates)
    goal_updates: dict[str, Any] = {}
    if "constraints" in preference_payload and "hard_dislikes" not in preference_payload:
        preference_payload["hard_dislikes"] = preference_payload.pop("constraints")
    for key in ("primary_goal", "goal_target", "goal_horizon", "constraints", "strategic_context", "priority_signals"):
        if key in preference_payload:
            goal_updates[key] = preference_payload.pop(key)
    return preference_payload, goal_updates


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "agentic-api"}


@router.get("/api/client-config")
def client_config() -> dict[str, Any]:
    return {
        "liff_id": settings.liff_channel_id,
        "auth_required": not settings.allow_demo_headers,
        "agentic_enabled": settings.agentic_enabled,
    }


@router.get("/api/me")
async def current_user(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> dict[str, Any]:
    decision = _cohort_for_user(user)
    return {
        "user_id": user.id,
        "line_user_id": user.line_user_id,
        "display_name": user.display_name,
        "cohort": decision.cohort,
        "core_version": decision.core_version,
        "auth_mode": getattr(request.state, "agentic_auth_mode", "unknown"),
    }


@router.post("/api/agent/turn", response_model=AgentTurnResult)
async def agent_turn(
    request: Request,
    agent_input: AgentInput,
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> AgentTurnResult:
    decision = _require_agentic(user)
    agent_input.source_metadata = agent_input.source_metadata.model_copy(
        update={
            "trace_id": getattr(request.state, "trace_id", None) or agent_input.source_metadata.trace_id,
            "auth_mode": getattr(request.state, "agentic_auth_mode", None),
        }
    )
    result = agent_loop.process(db, user, agent_input, cohort=decision.cohort, core_version=decision.core_version)
    return _persist_processed_turn(db, result, decision)


def _home(
    request: Request,
    title: str,
    home: DecisionHome,
    db: Session,
    user,
) -> HomePayload:
    decision = _require_agentic(user)
    payload = build_home_payload(db, user, title=title, home=home, cohort=decision.cohort, core_version=decision.core_version)
    payload.metadata["trace_id"] = getattr(request.state, "trace_id", None)
    payload.metadata["cohort_reason"] = decision.reason
    return payload


@router.get("/api/home/today", response_model=HomePayload)
async def today_home(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> HomePayload:
    return _home(request, "Today", DecisionHome.today, db, user)


@router.get("/api/home/eat", response_model=HomePayload)
async def eat_home(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> HomePayload:
    return _home(request, "Eat", DecisionHome.eat, db, user)


@router.get("/api/home/progress", response_model=HomePayload)
async def progress_home(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> HomePayload:
    return _home(request, "Progress", DecisionHome.progress, db, user)


@router.get("/api/home/settings", response_model=HomePayload)
async def settings_home(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> HomePayload:
    return _home(request, "Settings", DecisionHome.settings, db, user)


@router.get("/api/inbox/opportunities", response_model=list[dict[str, Any]])
async def inbox_opportunities(
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> list[dict[str, Any]]:
    _require_agentic(user)
    state = state_assembler.build(db, user)
    opportunities = state_assembler.opportunities_for(db, state)
    return [item.model_dump(mode="json") for item in opportunities]


@router.get("/api/observability/turns", response_model=list[dict[str, Any]])
async def observability_turns(
    limit: int = 20,
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> list[dict[str, Any]]:
    _require_agentic(user)
    return store.list_turns(db, user_id=user.id, limit=max(1, min(limit, 100)))


def _structured_turn_result(
    request: Request,
    user,
    db: Session,
    postback_payload: PostbackPayload,
) -> AgentTurnResult:
    decision = _require_agentic(user)
    agent_input = AgentInput(
        source=AgentInputSource.liff_structured_action,
        modalities=[],
        postback_payload=postback_payload,
        source_metadata=SourceMetadata(
            trace_id=getattr(request.state, "trace_id", None),
            auth_mode=getattr(request.state, "agentic_auth_mode", None),
        ),
    )
    result = agent_loop.process(db, user, agent_input, cohort=decision.cohort, core_version=decision.core_version)
    return _persist_processed_turn(db, result, decision)


@router.post("/api/decisions/apply")
async def apply_decision(
    request: Request,
    mutation: DecisionMutation,
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> dict[str, Any]:
    result = _structured_turn_result(
        request,
        user,
        db,
        PostbackPayload(
            action="apply_update",
            entity_ref=mutation.entity_ref,
            option_key=mutation.option_key,
            decision_context_ref=mutation.decision_context_ref,
            payload={"confirmed": mutation.confirmed},
        ),
    )
    executed = result.turn.executed_actions[0] if result.turn.executed_actions else None
    return {
        "status": "applied",
        "guardrail_policy": executed.guardrail_policy.value if executed else "allow_without_confirmation",
        "turn": result.turn.model_dump(mode="json"),
    }


@router.post("/api/decisions/dismiss")
async def dismiss_decision(
    request: Request,
    mutation: DecisionMutation,
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> dict[str, Any]:
    result = _structured_turn_result(
        request,
        user,
        db,
        PostbackPayload(
            action="dismiss_update",
            entity_ref=mutation.entity_ref,
            option_key=mutation.option_key,
            decision_context_ref=mutation.decision_context_ref,
            payload={"confirmed": mutation.confirmed},
        ),
    )
    executed = result.turn.executed_actions[0] if result.turn.executed_actions else None
    return {
        "status": "dismissed",
        "guardrail_policy": executed.guardrail_policy.value if executed else "allow_without_confirmation",
        "turn": result.turn.model_dump(mode="json"),
    }


@router.post("/api/settings/preferences")
async def update_preferences(
    request: Request,
    mutation: PreferencesMutation,
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> dict[str, Any]:
    decision = _require_agentic(user)
    preference_updates, goal_updates = _normalize_preference_updates(mutation.updates)
    result = _structured_turn_result(
        request,
        user,
        db,
        PostbackPayload(
            action="save_preferences",
            payload={"preference_correction": preference_updates, **preference_updates, "confirmed": mutation.confirmed},
        ),
    )
    if goal_updates:
        base = build_home_payload(db, user, title="Settings", home=DecisionHome.settings, cohort=decision.cohort, core_version=decision.core_version)
        store.persist_snapshot(
            db,
            user_id=user.id,
            snapshot_type="goal_state",
            payload=_goal_snapshot_payload(base, goal_updates),
            trace_id=result.turn.input.source_metadata.trace_id,
        )
        db.commit()
    executed = result.turn.executed_actions[0] if result.turn.executed_actions else None
    return {
        "status": "accepted" if mutation.confirmed else "pending_confirmation",
        "guardrail_policy": executed.guardrail_policy.value if executed else "require_confirmation",
        "turn": result.turn.model_dump(mode="json"),
    }


@router.post("/api/onboarding/complete")
async def complete_onboarding(
    request: Request,
    mutation: OnboardingMutation,
    db: Session = Depends(get_db),
    user=Depends(resolve_request_user),
) -> dict[str, Any]:
    decision = _require_agentic(user)
    result = _structured_turn_result(
        request,
        user,
        db,
        PostbackPayload(
            action="complete_onboarding",
            payload={
                "primary_goal": mutation.primary_goal.value,
                "constraints": mutation.constraints,
                "confirmed": mutation.confirmed,
            },
        ),
    )
    base = build_home_payload(db, user, title="Settings", home=DecisionHome.settings, cohort=decision.cohort, core_version=decision.core_version)
    store.persist_snapshot(
        db,
        user_id=user.id,
        snapshot_type="goal_state",
        payload=_goal_snapshot_payload(
            base,
            {
                "primary_goal": mutation.primary_goal.value,
                "constraints": mutation.constraints,
            },
        ),
        trace_id=result.turn.input.source_metadata.trace_id,
    )
    db.commit()
    executed = result.turn.executed_actions[0] if result.turn.executed_actions else None
    return {
        "status": "completed" if mutation.confirmed else "pending_confirmation",
        "guardrail_policy": executed.guardrail_policy.value if executed else "allow_without_confirmation",
        "turn": result.turn.model_dump(mode="json"),
    }


@router.post("/webhooks/line")
async def line_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    body = await request.body()
    signature = request.headers.get("x-line-signature")
    if not verify_line_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid LINE signature")
    payload = json.loads(body.decode("utf-8") or "{}")
    events = payload.get("events", [])
    accepted = 0
    duplicate = 0
    trace_id = getattr(request.state, "trace_id", None)
    for event in events:
        if not isinstance(event, dict):
            continue
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        line_user_id = str(source.get("userId") or "")
        reply_token = event.get("replyToken")
        if not line_user_id:
            continue
        _, created = enqueue_line_event(
            db,
            event=event,
            line_user_id=line_user_id,
            reply_token=str(reply_token) if reply_token else None,
            trace_id=trace_id,
        )
        if created:
            accepted += 1
        else:
            duplicate += 1
    return {"ok": True, "accepted": accepted, "duplicate": duplicate, "ingress_mode": "ack_fast"}
