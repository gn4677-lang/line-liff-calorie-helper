from __future__ import annotations

import asyncio
import copy
import re
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.api import routes as legacy_routes
from backend.app.models import MealDraft, MealEvent, MealLog, SearchJob, User, WeightLog
from backend.app.providers.factory import get_ai_provider
from backend.app.schemas import (
    ActivityAdjustmentRequest,
    IntakeRequest,
    MealEditRequest,
    MealEventRequest,
    OnboardingPreferencesRequest,
    PreferenceCorrectionRequest,
)
from backend.app.services.body_metrics import (
    create_activity_adjustment,
    get_or_create_body_goal,
    refresh_body_goal_calibration,
)
from backend.app.services.energy_qa import answer_calorie_question, build_energy_context
from backend.app.services.intake import (
    confirm_draft,
    create_correction_preview,
    create_or_update_draft,
    delete_log,
    draft_to_response,
    edit_log_manual,
    infer_meal_type,
    log_to_response,
    update_draft_with_clarification,
)
from backend.app.services.meal_events import create_meal_event, parse_future_meal_event_text
from backend.app.services.memory import (
    apply_onboarding_preferences,
    apply_preference_correction,
    detect_chat_correction,
    get_or_create_preferences,
)
from backend.app.services.planning import build_compensation_plan
from backend.app.services.proactive import apply_search_job, dismiss_search_job, mark_notification_read
from backend.app.services.recommendations import get_recommendations
from backend.app.services.video_intake import (
    enrich_video_intake_request,
    maybe_queue_video_refinement_job,
    request_has_video,
)

from .contracts import (
    AgentAction,
    AgentActionKind,
    AgentInput,
    AgentInputSource,
    AgentIntent,
    AgentPlan,
    AgentResponse,
    AgentState,
    AgentTurnResult,
    ConversationTurn,
    DecisionHome,
    DeliveryAction,
    DeliveryDecision,
    DeliverySurface,
    ExecutionRecord,
    GuardrailPolicy,
    HeroCard,
    InputModality,
    InteractionTurn,
    PersistedEffect,
    ProactiveOpportunity,
    SourceMetadata,
    SubtextCategory,
    ToneProfile,
    utc_now,
)
from .guardrails import DeterministicGuardrails
from .prompts import (
    DELIVERY_PROMPT,
    DELIVERY_PROMPT_VERSION,
    FUTURE_EVENT_HINT_PROMPT,
    FUTURE_EVENT_HINT_PROMPT_VERSION,
    PLAN_PROMPT,
    PLAN_PROMPT_VERSION,
    RESPONSE_PROMPT,
    RESPONSE_PROMPT_VERSION,
    UNDERSTAND_PROMPT,
    UNDERSTAND_PROMPT_VERSION,
)
from .providers import StructuredCallResult, StructuredOutputProvider
from .state import AgentStateAssembler


class FutureEventHint(BaseModel):
    event_date: str | None = None
    meal_type: str | None = None
    title: str | None = None
    expected_kcal: int | None = None
    confidence: float = 0.0


class AgentLoop:
    _user_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)

    def __init__(
        self,
        state_assembler: AgentStateAssembler,
        guardrails: DeterministicGuardrails,
        provider: StructuredOutputProvider,
    ) -> None:
        self.state_assembler = state_assembler
        self.guardrails = guardrails
        self.provider = provider
        self.legacy_provider = get_ai_provider()

    def process(
        self,
        db: Session,
        user: User,
        agent_input: AgentInput,
        *,
        cohort: str = "canary",
        core_version: str = "agentic",
    ) -> AgentTurnResult:
        started = time.monotonic()
        deadline = started + self.provider.settings.turn_timeout_s
        trace_id = agent_input.source_metadata.trace_id or str(uuid.uuid4())
        telemetry: dict[str, Any] = {
            "trace_id": trace_id,
            "cohort": cohort,
            "core_version": core_version,
            "provider_name": "deterministic",
            "model_name": "",
            "prompt_version": "",
            "provider_fallback_chain": [],
            "fallback_reason": None,
            "deterministic_safe_mode_used": False,
            "stage_usage": {},
        }
        agent_input.source_metadata.trace_id = trace_id
        agent_input.source_metadata.user_id = str(user.id)
        agent_input.source_metadata.line_user_id = user.line_user_id
        agent_input.source_metadata.cohort = cohort
        agent_input.source_metadata.core_version = core_version

        state = self.state_assembler.build(db, user, agent_input)
        understanding = self.understand(agent_input, state, telemetry, deadline)
        plan = self.plan(understanding, state, telemetry, deadline)
        executed_actions, persisted_effects = self.execute_with_guardrails(
            db,
            user,
            plan,
            state,
            agent_input,
            telemetry,
            deadline,
        )
        self.state_assembler.refresh_memory_records(db, user)
        updated_state = self.state_assembler.build(db, user)
        opportunities = self.state_assembler.opportunities_for(db, updated_state)
        delivery = self.delivery_decision(updated_state, opportunities, telemetry, deadline)
        response = self.respond(understanding, plan, executed_actions, updated_state, delivery, telemetry, deadline)
        updated_state.conversation_state.active_turns.append(
            ConversationTurn(role="assistant", text=response.message_text, created_at=datetime.now(timezone.utc))
        )
        updated_state.conversation_state.active_turns = updated_state.conversation_state.active_turns[-20:]
        telemetry["latency_ms"] = int((time.monotonic() - started) * 1000)
        telemetry["task_outcome"] = {
            "action_count": len(executed_actions),
            "persisted_effect_count": len(persisted_effects),
            "delivery_action": delivery.delivery_action.value if delivery else "suppress",
        }

        return AgentTurnResult(
            state=updated_state,
            turn=InteractionTurn(
                input=agent_input,
                understanding=understanding,
                plan=plan,
                executed_actions=executed_actions,
                response=response,
                persisted_effects=persisted_effects,
            ),
            opportunities=opportunities,
            delivery=delivery,
            telemetry=telemetry,
        )

    def process_proactive(
        self,
        db: Session,
        user: User,
        *,
        scheduled_window: str | None = None,
        cohort: str = "canary",
        core_version: str = "agentic",
    ) -> AgentTurnResult | None:
        started = time.monotonic()
        deadline = started + self.provider.settings.turn_timeout_s
        trace_id = str(uuid.uuid4())
        telemetry: dict[str, Any] = {
            "trace_id": trace_id,
            "cohort": cohort,
            "core_version": core_version,
            "provider_name": "deterministic",
            "model_name": "",
            "prompt_version": "",
            "provider_fallback_chain": [],
            "fallback_reason": None,
            "deterministic_safe_mode_used": False,
            "stage_usage": {},
            "scheduled_window": scheduled_window,
        }
        agent_input = AgentInput(
            source=AgentInputSource.system_trigger,
            modalities=[InputModality.system],
            text=scheduled_window or "scheduled_scan",
            source_metadata=SourceMetadata(
                user_id=str(user.id),
                line_user_id=user.line_user_id,
                trace_id=trace_id,
                auth_mode="worker_scan",
                cohort=cohort,
                core_version=core_version,
            ),
        )
        state = self.state_assembler.build(db, user)
        opportunities = self.state_assembler.opportunities_for(db, state)
        if not opportunities:
            return None
        delivery = self.delivery_decision(state, opportunities, telemetry, deadline)
        top = opportunities[0]
        understanding = AgentIntent(
            primary_intent="proactive_outreach",
            secondary_intents=[top.opportunity_type],
            subtext=[],
            entities={"opportunity_type": top.opportunity_type},
            urgency=delivery.urgency,
            confidence=max(min(delivery.importance, 0.95), 0.55),
            needs_followup=delivery.should_send,
            suggested_surface=delivery.delivery_surface if delivery.delivery_surface is not DeliverySurface.none else DeliverySurface.liff,
        )
        plan = self._plan_from_opportunity(top, delivery)
        executed_actions, persisted_effects = self.execute_with_guardrails(
            db,
            user,
            plan,
            state,
            agent_input,
            telemetry,
            deadline,
        )
        self.state_assembler.refresh_memory_records(db, user)
        updated_state = self.state_assembler.build(db, user)
        response = self.respond(understanding, plan, executed_actions, updated_state, delivery, telemetry, deadline)
        updated_state.conversation_state.active_turns.append(
            ConversationTurn(role="assistant", text=response.message_text, created_at=datetime.now(timezone.utc))
        )
        updated_state.conversation_state.active_turns = updated_state.conversation_state.active_turns[-20:]
        telemetry["latency_ms"] = int((time.monotonic() - started) * 1000)
        telemetry["task_outcome"] = {
            "action_count": len(executed_actions),
            "persisted_effect_count": len(persisted_effects),
            "delivery_action": delivery.delivery_action.value if delivery else "suppress",
        }
        return AgentTurnResult(
            state=updated_state,
            turn=InteractionTurn(
                input=agent_input,
                understanding=understanding,
                plan=plan,
                executed_actions=executed_actions,
                response=response,
                persisted_effects=persisted_effects,
            ),
            opportunities=opportunities,
            delivery=delivery,
            telemetry=telemetry,
        )

    def understand(
        self,
        agent_input: AgentInput,
        state: AgentState,
        telemetry: dict[str, Any],
        deadline: float,
    ) -> AgentIntent:
        postback_intent = self._intent_from_postback(agent_input)
        if postback_intent is not None:
            return postback_intent

        if correction := self._preference_correction_from_text(agent_input.text):
            return AgentIntent(
                primary_intent="mutate_preference",
                secondary_intents=["correction"],
                subtext=[],
                entities={"preference_correction": correction.model_dump(mode="json")},
                urgency=0.7,
                confidence=0.9,
                needs_followup=False,
                suggested_surface=DeliverySurface.liff,
            )

        structured = self._structured_call(
            AgentIntent,
            system_prompt=UNDERSTAND_PROMPT,
            prompt_version=UNDERSTAND_PROMPT_VERSION,
            user_payload={
                "input": self._compact_input_for_understanding(agent_input),
                "context": self.state_assembler.prune_for_understanding(state),
                "allowed_subtext": [item.value for item in SubtextCategory],
                "allowed_surfaces": [surface.value for surface in DeliverySurface],
                "persona": ToneProfile.calm_coach_partner.value,
            },
            timeout_s=self.provider.settings.understand_timeout_s,
            model_hint="frontier",
            max_tokens=140,
            temperature=0.0,
            request_options={"reasoning_effort": "minimal", "response_format": {"type": "json_object"}},
            telemetry=telemetry,
            deadline=deadline,
            stage="understand",
        )
        if structured is not None:
            structured.subtext = structured.subtext[:2]
            return structured
        return self._heuristic_understand_clean(agent_input)

    def plan(
        self,
        understanding: AgentIntent,
        state: AgentState,
        telemetry: dict[str, Any],
        deadline: float,
    ) -> AgentPlan:
        fast_path = self.fast_path(understanding)
        if fast_path is not None:
            telemetry["fast_path"] = True
            return fast_path
        if telemetry.get("deterministic_safe_mode_used"):
            return self._heuristic_plan(understanding, state)

        domain = "today"
        if understanding.primary_intent == "recommend_food":
            domain = "eat"
        elif understanding.primary_intent in {"seek_guidance", "record_weight", "record_activity", "future_event"}:
            domain = "progress"

        structured = self._structured_call(
            AgentPlan,
            system_prompt=PLAN_PROMPT,
            prompt_version=PLAN_PROMPT_VERSION,
            user_payload={
                "intent": understanding.model_dump(mode="json"),
                "context": self.state_assembler.prune_for_context(state, domain),
                "allowed_actions": self._allowed_action_examples(),
                "guardrail_policies": {
                    "allow_without_confirmation": self._allow_actions(),
                    "require_confirmation": self._confirmation_actions(),
                    "forbid": ["override_math", "override_filters", "write_without_confirmation"],
                },
            },
            timeout_s=self.provider.settings.plan_timeout_s,
            model_hint="router",
            max_tokens=260,
            request_options={"response_format": {"type": "json_object"}},
            telemetry=telemetry,
            deadline=deadline,
            stage="plan",
        )
        if structured is not None:
            structured.actions = self._sanitize_actions(structured.actions)
            structured.requires_confirmation = any(
                self.guardrails.policy_for(action).policy is GuardrailPolicy.require_confirmation
                for action in structured.actions
            )
            return structured
        return self._heuristic_plan(understanding, state)

    def fast_path(self, understanding: AgentIntent) -> AgentPlan | None:
        if understanding.primary_intent == "answer_grounded_qa":
            return AgentPlan(
                actions=[AgentAction(kind=AgentActionKind.answer_grounded_qa)],
                requires_confirmation=False,
                decision_home=DecisionHome.today,
                delivery_surface=DeliverySurface.line,
                context_used=["today_state.remaining_kcal"],
                goal_alignment={"primary_goal": 0.55},
                policy_reasons=["fast_path:grounded_qa"],
            )
        if understanding.primary_intent == "record_weight":
            return AgentPlan(
                actions=[AgentAction(kind=AgentActionKind.record_weight, payload=understanding.entities)],
                requires_confirmation=False,
                decision_home=DecisionHome.progress,
                delivery_surface=DeliverySurface.liff,
                context_used=["goal_state.primary_goal"],
                goal_alignment={"primary_goal": 0.8},
                policy_reasons=["fast_path:record_weight"],
            )
        if understanding.primary_intent in {"apply_suggested_update", "dismiss_suggested_update"}:
            return AgentPlan(
                actions=[
                    AgentAction(
                        kind=AgentActionKind.apply_suggested_update
                        if understanding.primary_intent == "apply_suggested_update"
                        else AgentActionKind.dismiss_suggested_update,
                        entity_ref=str(understanding.entities.get("job_id") or understanding.entities.get("entity_ref") or ""),
                    )
                ],
                requires_confirmation=False,
                decision_home=DecisionHome.today,
                delivery_surface=DeliverySurface.liff,
                context_used=["today_state.pending_updates"],
                goal_alignment={"primary_goal": 0.6},
                policy_reasons=["fast_path:suggested_update"],
            )
        return None

    def execute_with_guardrails(
        self,
        db: Session,
        user: User,
        plan: AgentPlan,
        state: AgentState,
        agent_input: AgentInput,
        telemetry: dict[str, Any],
        deadline: float,
    ) -> tuple[list[ExecutionRecord], list[PersistedEffect]]:
        executed: list[ExecutionRecord] = []
        persisted: list[PersistedEffect] = []
        explicitly_confirmed = agent_input.source in {
            AgentInputSource.liff_structured_action,
            AgentInputSource.line_postback,
        }

        for action in plan.actions:
            decision = self.guardrails.policy_for(action)
            if decision.policy is GuardrailPolicy.forbid:
                executed.append(
                    ExecutionRecord(
                        action=action,
                        guardrail_policy=decision.policy,
                        status="blocked",
                        summary=decision.reason,
                    )
                )
                continue

            try:
                record, effects = self._execute_action(
                    db,
                    user,
                    action,
                    state,
                    agent_input,
                    explicitly_confirmed=explicitly_confirmed or bool(action.payload.get("confirmed")),
                    guardrail_policy=decision.policy,
                    telemetry=telemetry,
                    deadline=deadline,
                )
            except Exception as exc:  # pragma: no cover
                telemetry["fallback_reason"] = telemetry.get("fallback_reason") or f"action_error:{action.kind.value}"
                executed.append(
                    ExecutionRecord(
                        action=action,
                        guardrail_policy=decision.policy,
                        status="blocked",
                        summary=f"Action failed safely: {type(exc).__name__}",
                    )
                )
                continue

            executed.append(record)
            persisted.extend(effects)
        return executed, persisted

    def respond(
        self,
        understanding: AgentIntent,
        plan: AgentPlan,
        executed: list[ExecutionRecord],
        state: AgentState,
        delivery: DeliveryDecision,
        telemetry: dict[str, Any],
        deadline: float,
    ) -> AgentResponse:
        if telemetry.get("deterministic_safe_mode_used"):
            return self._heuristic_respond_clean(understanding, plan, executed, state)
        structured = self._structured_call(
            AgentResponse,
            system_prompt=RESPONSE_PROMPT,
            prompt_version=RESPONSE_PROMPT_VERSION,
            user_payload={
                "intent": understanding.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "executed_actions": self._compact_execution_records(executed),
                "delivery": delivery.model_dump(mode="json"),
                "state": self.state_assembler.prune_for_context(state, plan.decision_home.value),
                "persona": ToneProfile.calm_coach_partner.value,
            },
            timeout_s=self.provider.settings.respond_timeout_s,
            model_hint="chat",
            max_tokens=260,
            request_options={"response_format": {"type": "json_object"}},
            telemetry=telemetry,
            deadline=deadline,
            stage="respond",
        )
        if structured is not None:
            structured.quick_replies = structured.quick_replies[:3]
            structured.tone_profile = ToneProfile.calm_coach_partner
            return structured
        return self._heuristic_respond_clean(understanding, plan, executed, state)

    def delivery_decision(
        self,
        state: AgentState,
        opportunities: list[ProactiveOpportunity],
        telemetry: dict[str, Any],
        deadline: float,
    ) -> DeliveryDecision:
        if not opportunities:
            return DeliveryDecision(
                importance=0.2,
                urgency=0.1,
                why_now="No interruption is necessary.",
                should_send=False,
                suppress_reason="no_opportunity",
                delivery_surface=DeliverySurface.none,
                decision_home=DecisionHome.none,
                delivery_action=DeliveryAction.suppress,
            )
        if telemetry.get("deterministic_safe_mode_used"):
            return self._apply_delivery_bounds(state, opportunities, self._heuristic_delivery(state, opportunities))

        structured = self._structured_call(
            DeliveryDecision,
            system_prompt=DELIVERY_PROMPT,
            prompt_version=DELIVERY_PROMPT_VERSION,
            user_payload={
                "goal_state": state.goal_state.model_dump(mode="json"),
                "delivery_state": state.delivery_state.model_dump(mode="json"),
                "opportunities": self._compact_opportunities(opportunities),
                "anti_spam_policy": {
                    "max_unsolicited_per_day": self.provider.settings.line_daily_unsolicited_cap,
                    "min_gap_hours": self.provider.settings.line_min_gap_hours,
                    "same_topic_cooldown_hours": self.provider.settings.same_topic_cooldown_hours,
                },
            },
            timeout_s=self.provider.settings.delivery_timeout_s,
            model_hint="router",
            max_tokens=180,
            request_options={"response_format": {"type": "json_object"}},
            telemetry=telemetry,
            deadline=deadline,
            stage="delivery",
        )
        decision = structured or self._heuristic_delivery(state, opportunities)
        return self._apply_delivery_bounds(state, opportunities, decision)

    def _execute_action(
        self,
        db: Session,
        user: User,
        action: AgentAction,
        state: AgentState,
        agent_input: AgentInput,
        *,
        explicitly_confirmed: bool,
        guardrail_policy: GuardrailPolicy,
        telemetry: dict[str, Any],
        deadline: float,
    ) -> tuple[list[ExecutionRecord], list[PersistedEffect]] | tuple[ExecutionRecord, list[PersistedEffect]]:
        if action.kind is AgentActionKind.recommend_food:
            try:
                recommendation_provider = None
                if not telemetry.get("deterministic_safe_mode_used") and self._remaining_budget(deadline) > 6.0:
                    recommendation_provider = self.legacy_provider
                recs = get_recommendations(
                    db,
                    user,
                    meal_type=str(action.payload.get("meal_type") or action.payload.get("meal") or "dinner"),
                    remaining_kcal=max(state.today_state.remaining_kcal, 0),
                    provider=recommendation_provider,
                    memory_packet=None,
                    communication_profile=None,
                )
                hero = recs.items[0] if recs.items else None
                artifact = {
                    "hero_candidate_key": hero.name if hero else None,
                    "coach_message": recs.coach_message,
                    "strategy_label": recs.strategy_label,
                    "items": [item.model_dump(mode="json") for item in recs.items[:6]],
                }
            except Exception:
                db.rollback()
                artifact = {
                    "hero_candidate_key": "bounded-light-dinner",
                    "coach_message": "我先用保守模式幫你收斂到輕盈一點的晚餐選項。",
                    "strategy_label": "deterministic_safe_fallback",
                    "items": [
                        {
                            "name": "Light Dinner",
                            "reason": "Fallback shortlist inside the remaining budget.",
                            "kcal_low": max(min(state.today_state.remaining_kcal, 520), 420),
                            "kcal_high": max(min(state.today_state.remaining_kcal, 620), 480),
                        }
                    ],
                }
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="executed",
                    summary="Bounded recommendation produced.",
                    artifact=artifact,
                ),
                [],
            )

        if action.kind is AgentActionKind.answer_grounded_qa:
            answer = answer_calorie_question(
                agent_input.text or "",
                allow_search=True,
                source_hint=None,
                context=build_energy_context(db, user),
            )
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="executed",
                    summary="Grounded QA answered deterministically.",
                    artifact={"answer": answer.answer, "sources": answer.sources, "packet": answer.packet},
                ),
                [],
            )

        if action.kind is AgentActionKind.propose_recovery:
            try:
                preference = get_or_create_preferences(db, user)
                goal = get_or_create_body_goal(db, user)
                planning_provider = None
                if not telemetry.get("deterministic_safe_mode_used") and self._remaining_budget(deadline) > 6.0:
                    planning_provider = self.legacy_provider
                compensation = build_compensation_plan(
                    max(state.weekly_state.drift_kcal, 0),
                    compensation_style=preference.compensation_style,
                    base_target=goal.estimated_tdee_kcal - goal.default_daily_deficit_kcal,
                    provider=planning_provider,
                    planning_packet=None,
                    communication_profile=None,
                )
                artifact = compensation.model_dump(mode="json")
            except Exception:
                db.rollback()
                artifact = {
                    "recovery_style": "steady",
                    "coach_message": "我先給你保守版的恢復建議：接下來幾餐先收斂、不要急著極端補償。",
                    "daily_allocations": [],
                }
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="executed",
                    summary="Recovery options prepared inside bounded policy.",
                    artifact=artifact,
                ),
                [],
            )

        with self._user_lock(user.id):
            if action.kind is AgentActionKind.mutate_meal_log:
                return self._execute_meal_mutation(
                    db,
                    user,
                    action,
                    agent_input,
                    explicitly_confirmed,
                    guardrail_policy,
                    telemetry,
                    deadline,
                )
            if action.kind is AgentActionKind.mutate_preference:
                return self._execute_preference_mutation(
                    db,
                    user,
                    action,
                    agent_input,
                    explicitly_confirmed,
                    guardrail_policy,
                )
            if action.kind is AgentActionKind.mutate_future_event:
                return self._execute_future_event_mutation(
                    db,
                    user,
                    action,
                    agent_input,
                    explicitly_confirmed,
                    guardrail_policy,
                    telemetry,
                    deadline,
                )
            if action.kind is AgentActionKind.record_weight:
                return self._execute_weight_record(db, user, action, guardrail_policy, agent_input)
            if action.kind is AgentActionKind.record_activity:
                return self._execute_activity_record(db, user, action, guardrail_policy, agent_input)
            if action.kind is AgentActionKind.complete_onboarding:
                return self._execute_complete_onboarding(db, user, action, guardrail_policy)
            if action.kind in {AgentActionKind.apply_suggested_update, AgentActionKind.dismiss_suggested_update}:
                return self._execute_suggested_update(db, user, action, guardrail_policy)

        return (
            ExecutionRecord(
                action=action,
                guardrail_policy=guardrail_policy,
                status="blocked",
                summary="Action kind is not supported by the current executor.",
            ),
            [],
        )

    def _execute_meal_mutation(
        self,
        db: Session,
        user: User,
        action: AgentAction,
        agent_input: AgentInput,
        explicitly_confirmed: bool,
        guardrail_policy: GuardrailPolicy,
        telemetry: dict[str, Any],
        deadline: float,
    ) -> tuple[ExecutionRecord, list[PersistedEffect]]:
        latest_draft = self._latest_open_draft(db, user)
        text = agent_input.text or ""

        if action.op == "delete":
            target = self._resolve_log(db, user, action.entity_ref)
            if target is None:
                return (
                    ExecutionRecord(action=action, guardrail_policy=guardrail_policy, status="blocked", summary="No target meal log found."),
                    [],
                )
            if not explicitly_confirmed:
                return (
                    ExecutionRecord(
                        action=action,
                        guardrail_policy=guardrail_policy,
                        status="pending_confirmation",
                        summary="Meal delete needs confirmation.",
                        artifact=log_to_response(target).model_dump(mode="json"),
                    ),
                    [],
                )
            target_id = target.id
            delete_log(db, target)
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="executed",
                    summary="Meal log deleted.",
                    artifact={"log_id": target_id},
                ),
                [
                    PersistedEffect(
                        entity_type="meal_log",
                        entity_id=str(target_id),
                        op="delete",
                        guardrail_source=guardrail_policy,
                        source_action=action.kind,
                        before_ref=f"meal_log:{target_id}",
                        confirmed_by_user=True,
                    )
                ],
            )

        if action.op == "edit":
            target = self._resolve_log(db, user, action.entity_ref)
            if target is None:
                return (
                    ExecutionRecord(action=action, guardrail_policy=guardrail_policy, status="blocked", summary="No target meal log found."),
                    [],
                )
            if not explicitly_confirmed:
                return (
                    ExecutionRecord(
                        action=action,
                        guardrail_policy=guardrail_policy,
                        status="pending_confirmation",
                        summary="Meal edit needs confirmation.",
                        artifact=log_to_response(target).model_dump(mode="json"),
                    ),
                    [],
                )
            request = MealEditRequest(
                description_raw=str(action.payload.get("description_raw") or text or target.description_raw),
                kcal_estimate=int(action.payload.get("kcal_estimate") or target.kcal_estimate),
                meal_type=str(action.payload.get("meal_type") or target.meal_type),
                event_at=self._coerce_datetime(action.payload.get("event_at")) or target.event_at,
            )
            edited = edit_log_manual(db, target, request)
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="executed",
                    summary="Meal log edited.",
                    artifact=log_to_response(edited).model_dump(mode="json"),
                ),
                [
                    PersistedEffect(
                        entity_type="meal_log",
                        entity_id=str(edited.id),
                        op="edit",
                        guardrail_source=guardrail_policy,
                        source_action=action.kind,
                        before_ref=f"meal_log:{edited.id}",
                        after_ref=f"meal_log:{edited.id}",
                        confirmed_by_user=True,
                    )
                ],
            )

        if action.op == "correct":
            target = self._resolve_log(db, user, action.entity_ref)
            if target is None:
                return (
                    ExecutionRecord(action=action, guardrail_policy=guardrail_policy, status="blocked", summary="No recent meal is available for correction."),
                    [],
                )
            estimate = self._estimate_intake(db, user, agent_input, telemetry, deadline, target.meal_type)
            correction_draft = create_correction_preview(db, user, target, correction_text=text, estimate=estimate)
            if request_has_video(self._intake_request_from_input(agent_input, action.payload)):
                maybe_queue_video_refinement_job(
                    db,
                    user,
                    trace_id=agent_input.source_metadata.trace_id,
                    text=text,
                    meal_type=target.meal_type,
                    attachments=[item.model_dump(mode="json") for item in agent_input.attachments],
                    metadata={"video_source_label": "agentic_correction"},
                    draft=correction_draft,
                    notify_on_complete=True,
                )
            if not explicitly_confirmed:
                return (
                    ExecutionRecord(
                        action=action,
                        guardrail_policy=guardrail_policy,
                        status="pending_confirmation",
                        summary="Meal correction draft is waiting for confirmation.",
                        artifact=draft_to_response(correction_draft).model_dump(mode="json"),
                    ),
                    [],
                )
            corrected = confirm_draft(db, user, correction_draft)
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="executed",
                    summary="Meal correction applied.",
                    artifact=log_to_response(corrected).model_dump(mode="json"),
                ),
                [
                    PersistedEffect(
                        entity_type="meal_log",
                        entity_id=str(corrected.id),
                        op="correct",
                        guardrail_source=guardrail_policy,
                        source_action=action.kind,
                        after_ref=f"meal_log:{corrected.id}",
                        confirmed_by_user=True,
                    )
                ],
            )

        if latest_draft is not None and latest_draft.status == "awaiting_clarification" and text and not agent_input.attachments:
            estimate = self._estimate_intake(db, user, agent_input, telemetry, deadline, latest_draft.meal_type)
            updated = update_draft_with_clarification(db, latest_draft, text, estimate)
            if explicitly_confirmed and updated.status != "awaiting_clarification":
                logged = confirm_draft(db, user, updated)
                return (
                    ExecutionRecord(
                        action=action,
                        guardrail_policy=guardrail_policy,
                        status="executed",
                        summary="Clarified meal was logged.",
                        artifact=log_to_response(logged).model_dump(mode="json"),
                    ),
                    [
                        PersistedEffect(
                            entity_type="meal_log",
                            entity_id=str(logged.id),
                            op="create",
                            guardrail_source=guardrail_policy,
                            source_action=action.kind,
                            after_ref=f"meal_log:{logged.id}",
                            confirmed_by_user=True,
                        )
                    ],
                )
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="pending_confirmation",
                    summary="Draft updated with clarification.",
                    artifact=draft_to_response(updated).model_dump(mode="json"),
                ),
                [],
            )

        intake_request = self._intake_request_from_input(agent_input, action.payload)
        estimate = self._estimate_intake(db, user, agent_input, telemetry, deadline, intake_request.meal_type)
        draft = create_or_update_draft(db, user, intake_request, estimate)
        if request_has_video(intake_request):
            maybe_queue_video_refinement_job(
                db,
                user,
                trace_id=agent_input.source_metadata.trace_id,
                text=intake_request.text,
                meal_type=intake_request.meal_type,
                attachments=intake_request.attachments,
                metadata=intake_request.metadata,
                draft=draft,
                notify_on_complete=True,
            )
        if explicitly_confirmed and draft.status != "awaiting_clarification":
            logged = confirm_draft(db, user, draft)
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="executed",
                    summary="Meal logged.",
                    artifact=log_to_response(logged).model_dump(mode="json"),
                ),
                [
                    PersistedEffect(
                        entity_type="meal_log",
                        entity_id=str(logged.id),
                        op="create",
                        guardrail_source=guardrail_policy,
                        source_action=action.kind,
                        after_ref=f"meal_log:{logged.id}",
                        confirmed_by_user=True,
                    )
                ],
            )
        return (
            ExecutionRecord(
                action=action,
                guardrail_policy=guardrail_policy,
                status="pending_confirmation",
                summary="Meal draft created and waiting for confirmation.",
                artifact=draft_to_response(draft).model_dump(mode="json"),
            ),
            [],
        )

    def _execute_preference_mutation(
        self,
        db: Session,
        user: User,
        action: AgentAction,
        agent_input: AgentInput,
        explicitly_confirmed: bool,
        guardrail_policy: GuardrailPolicy,
    ) -> tuple[ExecutionRecord, list[PersistedEffect]]:
        correction = PreferenceCorrectionRequest(**dict(action.payload))
        if not explicitly_confirmed:
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="pending_confirmation",
                    summary="Preference change is waiting for confirmation.",
                    artifact=correction.model_dump(mode="json"),
                ),
                [],
            )
        updated = apply_preference_correction(db, user, correction)
        return (
            ExecutionRecord(
                action=action,
                guardrail_policy=guardrail_policy,
                status="executed",
                summary="Preference updated.",
                artifact={"hard_dislikes": updated.hard_dislikes, "dinner_style": updated.dinner_style},
            ),
            [
                PersistedEffect(
                    entity_type="preference",
                    entity_id=str(user.id),
                    op="mutate",
                    guardrail_source=guardrail_policy,
                    source_action=action.kind,
                    after_ref=f"user:{user.id}:preference",
                    confirmed_by_user=True,
                    payload=correction.model_dump(mode="json"),
                )
            ],
        )

    def _execute_future_event_mutation(
        self,
        db: Session,
        user: User,
        action: AgentAction,
        agent_input: AgentInput,
        explicitly_confirmed: bool,
        guardrail_policy: GuardrailPolicy,
        telemetry: dict[str, Any],
        deadline: float,
    ) -> tuple[ExecutionRecord, list[PersistedEffect]]:
        payload = dict(action.payload)
        if action.op == "delete":
            target = self._resolve_event(db, user, action.entity_ref)
            if target is None:
                return (
                    ExecutionRecord(action=action, guardrail_policy=guardrail_policy, status="blocked", summary="Future event not found."),
                    [],
                )
            if not explicitly_confirmed:
                return (
                    ExecutionRecord(
                        action=action,
                        guardrail_policy=guardrail_policy,
                        status="pending_confirmation",
                        summary="Future event delete needs confirmation.",
                        artifact={"event_id": target.id, "title": target.title, "event_date": target.event_date.isoformat()},
                    ),
                    [],
                )
            target_id = target.id
            db.delete(target)
            db.commit()
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="executed",
                    summary="Future meal event deleted.",
                    artifact={"event_id": target_id},
                ),
                [
                    PersistedEffect(
                        entity_type="meal_event",
                        entity_id=str(target_id),
                        op="delete",
                        guardrail_source=guardrail_policy,
                        source_action=action.kind,
                        before_ref=f"meal_event:{target_id}",
                        confirmed_by_user=True,
                    )
                ],
            )

        if action.op == "edit":
            target = self._resolve_event(db, user, action.entity_ref)
            if target is None:
                return (
                    ExecutionRecord(action=action, guardrail_policy=guardrail_policy, status="blocked", summary="Future event not found."),
                    [],
                )
            if not explicitly_confirmed:
                return (
                    ExecutionRecord(
                        action=action,
                        guardrail_policy=guardrail_policy,
                        status="pending_confirmation",
                        summary="Future event edit needs confirmation.",
                        artifact={"event_id": target.id, "title": target.title, "event_date": target.event_date.isoformat()},
                    ),
                    [],
                )
            target.event_date = self._parse_date(payload.get("event_date")) or target.event_date
            target.meal_type = str(payload.get("meal_type") or target.meal_type)
            target.title = str(payload.get("title") or target.title)
            if payload.get("expected_kcal") is not None:
                target.expected_kcal = int(payload["expected_kcal"])
            db.add(target)
            db.commit()
            db.refresh(target)
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="executed",
                    summary="Future meal event edited.",
                    artifact={"event_id": target.id, "title": target.title, "event_date": target.event_date.isoformat()},
                ),
                [
                    PersistedEffect(
                        entity_type="meal_event",
                        entity_id=str(target.id),
                        op="edit",
                        guardrail_source=guardrail_policy,
                        source_action=action.kind,
                        after_ref=f"meal_event:{target.id}",
                        confirmed_by_user=True,
                    )
                ],
            )

        candidate = self._future_event_candidate(agent_input.text or "", telemetry=telemetry, deadline=deadline)
        if candidate is None:
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="blocked",
                    summary="Future event still needs clarification before creation.",
                    artifact={"clarification": "Please tell me the date and meal more clearly."},
                ),
                [],
            )
        if not explicitly_confirmed:
            return (
                ExecutionRecord(
                    action=action,
                    guardrail_policy=guardrail_policy,
                    status="pending_confirmation",
                    summary="Future event preview created and waiting for confirmation.",
                    artifact={"event_candidate": candidate.model_dump(mode="json")},
                ),
                [],
            )
        request = MealEventRequest(
            event_date=self._parse_date(candidate.event_date) or date.today(),
            meal_type=str(candidate.meal_type or "dinner"),
            title=str(candidate.title or "Future meal"),
            expected_kcal=candidate.expected_kcal,
            notes="created_by_agentic",
            source="agentic",
        )
        created = create_meal_event(db, user, request)
        return (
            ExecutionRecord(
                action=action,
                guardrail_policy=guardrail_policy,
                status="executed",
                summary="Future meal event created.",
                artifact={"event_id": created.id, "title": created.title, "event_date": created.event_date.isoformat()},
            ),
            [
                PersistedEffect(
                    entity_type="meal_event",
                    entity_id=str(created.id),
                    op="create",
                    guardrail_source=guardrail_policy,
                    source_action=action.kind,
                    after_ref=f"meal_event:{created.id}",
                    confirmed_by_user=True,
                )
            ],
        )

    def _execute_weight_record(
        self,
        db: Session,
        user: User,
        action: AgentAction,
        guardrail_policy: GuardrailPolicy,
        agent_input: AgentInput,
    ) -> tuple[ExecutionRecord, list[PersistedEffect]]:
        value = self._extract_weight_clean(agent_input.text or "", action.payload)
        if value is None:
            return (
                ExecutionRecord(action=action, guardrail_policy=guardrail_policy, status="blocked", summary="Weight value was missing."),
                [],
            )
        target_date = self._parse_date(action.payload.get("date")) or date.today()
        entry = db.scalar(select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.date == target_date))
        if entry is None:
            entry = WeightLog(user_id=user.id, date=target_date, weight=value)
        else:
            entry.weight = value
        db.add(entry)
        db.commit()
        db.refresh(entry)
        refresh_body_goal_calibration(db, user)
        return (
            ExecutionRecord(
                action=action,
                guardrail_policy=guardrail_policy,
                status="executed",
                summary="Weight recorded.",
                artifact={"weight": entry.weight, "date": entry.date.isoformat()},
            ),
            [
                PersistedEffect(
                    entity_type="weight_log",
                    entity_id=str(entry.id),
                    op="upsert",
                    guardrail_source=guardrail_policy,
                    source_action=action.kind,
                    after_ref=f"weight_log:{entry.id}",
                    confirmed_by_user=True,
                )
            ],
        )

    def _execute_activity_record(
        self,
        db: Session,
        user: User,
        action: AgentAction,
        guardrail_policy: GuardrailPolicy,
        agent_input: AgentInput,
    ) -> tuple[ExecutionRecord, list[PersistedEffect]]:
        request = self._activity_request(agent_input.text or "", action.payload)
        row = create_activity_adjustment(db, user, request)
        return (
            ExecutionRecord(
                action=action,
                guardrail_policy=guardrail_policy,
                status="executed",
                summary="Activity adjustment recorded.",
                artifact={"id": row.id, "label": row.label, "estimated_burn_kcal": row.estimated_burn_kcal, "date": row.date.isoformat()},
            ),
            [
                PersistedEffect(
                    entity_type="activity_adjustment",
                    entity_id=str(row.id),
                    op="create",
                    guardrail_source=guardrail_policy,
                    source_action=action.kind,
                    after_ref=f"activity_adjustment:{row.id}",
                    confirmed_by_user=True,
                )
            ],
        )

    def _execute_complete_onboarding(
        self,
        db: Session,
        user: User,
        action: AgentAction,
        guardrail_policy: GuardrailPolicy,
    ) -> tuple[ExecutionRecord, list[PersistedEffect]]:
        request = OnboardingPreferencesRequest(
            breakfast_habit=str(action.payload.get("breakfast_habit") or "unknown"),
            carb_need=str(action.payload.get("carb_need") or "flexible"),
            dinner_style=str(action.payload.get("dinner_style") or "normal"),
            hard_dislikes=list(action.payload.get("constraints") or []),
            compensation_style=str(action.payload.get("compensation_style") or "gentle"),
        )
        pref = apply_onboarding_preferences(db, user, request)
        return (
            ExecutionRecord(
                action=action,
                guardrail_policy=guardrail_policy,
                status="executed",
                summary="Onboarding state completed.",
                artifact={"preferences": pref.hard_dislikes, "primary_goal": action.payload.get("primary_goal")},
            ),
            [
                PersistedEffect(
                    entity_type="onboarding",
                    entity_id=str(user.id),
                    op="complete",
                    guardrail_source=guardrail_policy,
                    source_action=action.kind,
                    after_ref=f"user:{user.id}:onboarding",
                    confirmed_by_user=True,
                    payload={"primary_goal": action.payload.get("primary_goal")},
                )
            ],
        )

    def _execute_suggested_update(
        self,
        db: Session,
        user: User,
        action: AgentAction,
        guardrail_policy: GuardrailPolicy,
    ) -> tuple[ExecutionRecord, list[PersistedEffect]]:
        job_id = action.entity_ref or str(action.payload.get("job_id") or "")
        job = db.get(SearchJob, job_id)
        if job is None or job.user_id != user.id:
            notification_id = action.payload.get("notification_id")
            if notification_id:
                mark_notification_read(db, user, str(notification_id))
            return (
                ExecutionRecord(action=action, guardrail_policy=guardrail_policy, status="blocked", summary="Suggested update not found."),
                [],
            )
        response = apply_search_job(db, user, job) if action.kind is AgentActionKind.apply_suggested_update else dismiss_search_job(db, user, job)
        return (
            ExecutionRecord(
                action=action,
                guardrail_policy=guardrail_policy,
                status="executed",
                summary=f"Suggested update {response.status}.",
                artifact=response.model_dump(mode="json"),
            ),
            [
                PersistedEffect(
                    entity_type="search_job",
                    entity_id=job.id,
                    op=response.status,
                    guardrail_source=guardrail_policy,
                    source_action=action.kind,
                    after_ref=f"search_job:{job.id}",
                    confirmed_by_user=True,
                )
            ],
        )

    def _structured_call(
        self,
        model: type[BaseModel],
        *,
        system_prompt: str,
        prompt_version: str,
        user_payload: dict[str, Any],
        timeout_s: float,
        model_hint: str,
        telemetry: dict[str, Any],
        deadline: float,
        stage: str,
        max_tokens: int = 320,
        temperature: float = 0.1,
        request_options: dict[str, Any] | None = None,
    ):
        telemetry.setdefault("stage_usage", {})
        telemetry.setdefault("provider_fallback_chain", [])
        remaining = self._remaining_budget(deadline)
        stage_budget = min(timeout_s, remaining)
        if stage_budget <= 0.2:
            telemetry["fallback_reason"] = telemetry.get("fallback_reason") or f"{stage}_budget_exhausted"
            telemetry["deterministic_safe_mode_used"] = True
            self._append_fallback_step(telemetry, "deterministic-safe")
            return None
        effective_request_options = self._stage_request_options(
            stage=stage,
            prompt_version=prompt_version,
            model_hint=model_hint,
            telemetry=telemetry,
            request_options=request_options,
        )
        result = self.provider.complete_structured(
            model,
            system_prompt=system_prompt,
            user_payload=user_payload,
            prompt_version=prompt_version,
            timeout_s=stage_budget,
            model_hint=model_hint,
            max_tokens=max_tokens,
            temperature=temperature,
            request_options=effective_request_options,
        )
        telemetry["prompt_version"] = prompt_version
        stage_usage: dict[str, Any] = {
            "provider_name": result.provider_name,
            "model_name": result.model_name,
            "prompt_version": result.prompt_version,
            "fallback_reason": result.fallback_reason,
            "usage": result.usage,
        }
        retry_result = self._retry_understand_with_router(
            model=model,
            stage=stage,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
            user_payload=user_payload,
            telemetry=telemetry,
            deadline=deadline,
            max_tokens=max_tokens,
            primary_result=result,
        )
        if retry_result is not None:
            stage_usage["retry"] = {
                "provider_name": retry_result.provider_name,
                "model_name": retry_result.model_name,
                "prompt_version": retry_result.prompt_version,
                "fallback_reason": retry_result.fallback_reason,
                "usage": retry_result.usage,
            }
            telemetry["stage_usage"][stage] = stage_usage
            self._append_fallback_step(telemetry, "builderspace")
            self._append_fallback_step(telemetry, "builderspace-retry")
            if retry_result.payload is not None:
                telemetry["provider_name"] = retry_result.provider_name
                telemetry["model_name"] = retry_result.model_name
                return retry_result.payload
        telemetry["stage_usage"][stage] = stage_usage
        self._append_fallback_step(telemetry, "builderspace")
        if result.payload is not None:
            telemetry["provider_name"] = result.provider_name
            telemetry["model_name"] = result.model_name
            return result.payload
        self._append_fallback_step(telemetry, "heuristic")
        telemetry["deterministic_safe_mode_used"] = True
        if result.fallback_reason:
            telemetry["fallback_reason"] = telemetry.get("fallback_reason") or f"{stage}:{result.fallback_reason}"
        return None

    def _retry_understand_with_router(
        self,
        *,
        model: type[BaseModel],
        stage: str,
        system_prompt: str,
        prompt_version: str,
        user_payload: dict[str, Any],
        telemetry: dict[str, Any],
        deadline: float,
        max_tokens: int,
        primary_result: StructuredCallResult,
    ) -> StructuredCallResult | None:
        if stage != "understand" or model is not AgentIntent:
            return None
        if primary_result.payload is not None or primary_result.fallback_reason not in {"empty_response", "invalid_schema"}:
            return None
        retry_budget = min(self._remaining_budget(deadline), 3.0)
        if retry_budget <= 0.4:
            return None
        return self.provider.complete_structured(
            model,
            system_prompt=system_prompt,
            user_payload=user_payload,
            prompt_version=prompt_version,
            timeout_s=retry_budget,
            model_hint="router",
            max_tokens=min(max(max_tokens, 180), 260),
            temperature=0.0,
            request_options=self._stage_request_options(
                stage=stage,
                prompt_version=prompt_version,
                model_hint="router",
                telemetry=telemetry,
                request_options={"response_format": {"type": "json_object"}},
            ),
        )

    def _stage_request_options(
        self,
        *,
        stage: str,
        prompt_version: str,
        model_hint: str,
        telemetry: dict[str, Any],
        request_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        options = copy.deepcopy(request_options) if isinstance(request_options, dict) else {}
        options.setdefault("response_format", {"type": "json_object"})
        options.setdefault("tool_choice", "none")
        metadata = options.get("metadata")
        metadata_payload = metadata if isinstance(metadata, dict) else {}
        metadata_payload.setdefault("agentic_stage", stage)
        metadata_payload.setdefault("prompt_version", prompt_version)
        if telemetry.get("trace_id"):
            metadata_payload.setdefault("trace_id", telemetry["trace_id"])
        if telemetry.get("cohort"):
            metadata_payload.setdefault("cohort", telemetry["cohort"])
        options["metadata"] = metadata_payload
        if model_hint == "frontier":
            options.setdefault("reasoning_effort", "minimal")
        return options

    def _compact_input_for_understanding(self, agent_input: AgentInput) -> dict[str, Any]:
        return {
            "source": agent_input.source.value,
            "modalities": [item.value for item in agent_input.modalities],
            "text": (agent_input.text or "")[:220],
            "attachment_types": [item.modality for item in agent_input.attachments[:3]],
            "location_label": agent_input.location.label if agent_input.location else None,
            "has_location": agent_input.location is not None,
            "postback_action": agent_input.postback_payload.action if agent_input.postback_payload else None,
        }

    def _compact_execution_records(self, executed: list[ExecutionRecord]) -> list[dict[str, Any]]:
        compact: list[dict[str, Any]] = []
        for item in executed[:3]:
            artifact = item.artifact or {}
            compact.append(
                {
                    "kind": item.action.kind.value,
                    "op": item.action.op,
                    "status": item.status,
                    "summary": item.summary,
                    "artifact_summary": {
                        "keys": list(artifact.keys())[:6],
                        "hero_candidate_key": artifact.get("hero_candidate_key"),
                        "coach_message": artifact.get("coach_message"),
                        "weight": artifact.get("weight"),
                        "estimated_burn_kcal": artifact.get("estimated_burn_kcal"),
                    },
                }
            )
        return compact

    def _compact_opportunities(self, opportunities: list[ProactiveOpportunity]) -> list[dict[str, Any]]:
        compact: list[dict[str, Any]] = []
        for item in opportunities[:4]:
            compact.append(
                {
                    "opportunity_type": item.opportunity_type,
                    "eligible_surfaces": [surface.value for surface in item.eligible_surfaces],
                    "importance_factors": [
                        {"factor": factor.factor, "weight": factor.weight}
                        for factor in item.importance_factors[:4]
                    ],
                    "recommended_business_action": item.recommended_business_action.model_dump(mode="json")
                    if item.recommended_business_action
                    else None,
                }
            )
        return compact

    def _plan_from_opportunity(self, opportunity: ProactiveOpportunity, delivery: DeliveryDecision) -> AgentPlan:
        actions: list[AgentAction] = []
        if opportunity.opportunity_type == "weekly_drift":
            actions.append(AgentAction(kind=AgentActionKind.propose_recovery))
        elif opportunity.opportunity_type == "remaining_kcal_decision_window":
            actions.append(
                AgentAction(
                    kind=AgentActionKind.recommend_food,
                    payload={"meal_type": "dinner"},
                )
            )
        elif opportunity.recommended_business_action is not None and opportunity.recommended_business_action.kind in {
            AgentActionKind.recommend_food,
            AgentActionKind.propose_recovery,
        }:
            actions.append(opportunity.recommended_business_action)
        decision_home = delivery.decision_home if delivery.decision_home is not DecisionHome.none else DecisionHome.today
        if opportunity.opportunity_type == "goal_capture":
            decision_home = DecisionHome.settings
        elif opportunity.opportunity_type in {"future_meal_event", "weekly_drift"}:
            decision_home = DecisionHome.progress
        elif opportunity.opportunity_type == "remaining_kcal_decision_window":
            decision_home = DecisionHome.eat
        policy_reasons = [f"proactive:{opportunity.opportunity_type}", f"scheduled_delivery:{delivery.delivery_action.value}"]
        return AgentPlan(
            actions=actions,
            requires_confirmation=False,
            decision_home=decision_home,
            delivery_surface=delivery.delivery_surface if delivery.delivery_surface is not DeliverySurface.none else DeliverySurface.liff,
            context_used=["goal_state", "today_state", "weekly_state", "delivery_state"],
            goal_alignment={"primary_goal": max(delivery.importance, 0.55)},
            policy_reasons=policy_reasons,
        )

    def _heuristic_respond_clean(
        self,
        understanding: AgentIntent,
        plan: AgentPlan,
        executed: list[ExecutionRecord],
        state: AgentState,
    ) -> AgentResponse:
        pending = next((item for item in executed if item.status == "pending_confirmation"), None)
        if pending and pending.artifact.get("event_candidate"):
            candidate = pending.artifact["event_candidate"]
            return AgentResponse(
                message_text=f"我先幫你整理出一筆未來餐點：{candidate['event_date']} 的 {candidate['meal_type']}。",
                followup_question="要我現在先幫你存起來嗎？",
                quick_replies=["確認", "稍後"],
                deep_link="/progress",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if pending and pending.action.kind is AgentActionKind.mutate_meal_log:
            draft = pending.artifact
            kcal = draft.get("estimate_kcal") or draft.get("kcal_estimate") or 0
            return AgentResponse(
                message_text=f"我先幫你整理成一筆餐點草稿，約 {kcal} kcal。",
                followup_question=draft.get("followup_question") or "要我現在記下來嗎？",
                quick_replies=["確認", "補充一下", "稍後"],
                deep_link="/today",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if understanding.primary_intent == "proactive_outreach":
            return self._heuristic_proactive_response(plan, executed)
        if understanding.primary_intent == "recommend_food":
            hero = state.recommendation_state.shortlist[0] if state.recommendation_state.shortlist else None
            message = "我先幫你收斂成一組比較穩的用餐方向。"
            if hero is not None:
                message = f"先看 {hero.title}，比較貼近你現在的熱量空間，也比較不會太重。"
            return AgentResponse(
                message_text=message,
                followup_question="如果你想比附近選項，我幫你放在 Eat 裡。",
                hero_card=HeroCard(
                    title=hero.title if hero else "打開 Eat",
                    body=hero.reason if hero else "我先把 bounded shortlist 放在 Eat 給你比較。",
                    cta_label="打開 Eat",
                )
                if hero
                else None,
                quick_replies=["打開 Eat", "清淡一點", "看 Progress"],
                deep_link="/eat",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if understanding.primary_intent == "answer_grounded_qa":
            artifact = next((item.artifact for item in executed if item.action.kind is AgentActionKind.answer_grounded_qa), {})
            return AgentResponse(
                message_text=str(artifact.get("answer") or "我先用目前可用的 grounded context 幫你整理這題。"),
                quick_replies=["看 Today", "推薦晚餐"],
                deep_link="/today",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if understanding.primary_intent == "record_weight":
            artifact = next((item.artifact for item in executed if item.action.kind is AgentActionKind.record_weight), {})
            return AgentResponse(
                message_text=f"已經幫你記下體重 {artifact.get('weight')} kg。",
                followup_question="想看本週趨勢和恢復空間的話，可以到 Progress。",
                quick_replies=["看 Progress", "回 Today"],
                deep_link="/progress",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if understanding.primary_intent == "record_activity":
            artifact = next((item.artifact for item in executed if item.action.kind is AgentActionKind.record_activity), {})
            return AgentResponse(
                message_text=f"已記下活動：{artifact.get('label')}，大約消耗 {artifact.get('estimated_burn_kcal')} kcal。",
                quick_replies=["回 Today", "看 Progress"],
                deep_link="/progress",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if understanding.primary_intent == "mutate_preference":
            return AgentResponse(
                message_text="我有把這次偏好修正記下來。",
                followup_question="如果你想檢查完整設定，可以到 Settings 看一下。",
                quick_replies=["打開 Settings", "推薦晚餐"],
                deep_link="/settings",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if understanding.primary_intent == "seek_guidance" or any(
            item.action.kind is AgentActionKind.propose_recovery for item in executed
        ):
            return AgentResponse(
                message_text="今天不用硬補償，我可以幫你把後面收得順一點。",
                followup_question="要我先給你一個清淡晚餐方向、恢復建議，或兩個一起？",
                quick_replies=["清淡晚餐", "恢復建議", "兩個都要"],
                deep_link="/progress",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        return AgentResponse(
            message_text="我先把現在最重要的脈絡整理好了，接下來可以一起往下走。",
            followup_question="你想先記錄、找晚餐，還是看一下這週進度？",
            quick_replies=["記錄餐點", "找晚餐", "看 Progress"],
            deep_link=f"/{plan.decision_home.value}",
            tone_profile=ToneProfile.calm_coach_partner,
        )

    def _heuristic_proactive_response(
        self,
        plan: AgentPlan,
        executed: list[ExecutionRecord],
    ) -> AgentResponse:
        topic = next(
            (reason.split(":", 1)[1] for reason in plan.policy_reasons if reason.startswith("proactive:")),
            "general",
        )
        if topic == "open_draft_stuck":
            return AgentResponse(
                message_text="你有一筆餐點草稿還沒收尾，我先放在 Today，兩步內就能完成。",
                followup_question="要我帶你直接回去確認嗎？",
                quick_replies=["打開 Today", "稍後再說"],
                deep_link="/today",
            )
        if topic == "weekly_drift":
            artifact = next((item.artifact for item in executed if item.action.kind is AgentActionKind.propose_recovery), {})
            return AgentResponse(
                message_text=str(artifact.get("coach_message") or "這週有點超出，我先幫你準備一個保守的恢復方向。"),
                followup_question="要我把選項放到 Progress 給你看嗎？",
                quick_replies=["打開 Progress", "先看晚餐"],
                deep_link="/progress",
            )
        if topic == "future_meal_event":
            return AgentResponse(
                message_text="你有一個接近的未來餐點事件，我先把影響整理在 Progress。",
                followup_question="要不要現在先看一下怎麼安排比較輕鬆？",
                quick_replies=["打開 Progress", "稍後提醒我"],
                deep_link="/progress",
            )
        if topic == "goal_capture":
            return AgentResponse(
                message_text="我還缺你的目標或飲食限制，先補一下，後面的建議會準很多。",
                followup_question="要我帶你去 Settings 用最短的方式補齊嗎？",
                quick_replies=["打開 Settings", "稍後再說"],
                deep_link="/settings",
            )
        if topic == "async_refinement_ready":
            return AgentResponse(
                message_text="剛才的影片或附件我整理好了，先放在 Today 等你確認。",
                followup_question="要我帶你去看這次更新嗎？",
                quick_replies=["打開 Today", "稍後再看"],
                deep_link="/today",
            )
        if topic == "remaining_kcal_decision_window":
            artifact = next((item.artifact for item in executed if item.action.kind is AgentActionKind.recommend_food), {})
            hero = artifact.get("hero_candidate_key")
            message = "現在還有一段不錯的熱量空間，我先幫你收斂出一個比較穩的晚餐方向。"
            if hero:
                message = f"現在還有不錯的熱量空間，我先幫你挑出 {hero} 這種比較穩的方向。"
            return AgentResponse(
                message_text=message,
                followup_question="要不要直接去 Eat 看附近選項？",
                quick_replies=["打開 Eat", "換一個方向"],
                deep_link="/eat",
            )
        if topic == "no_log_day":
            return AgentResponse(
                message_text="今天還沒看到你的餐點記錄。如果你剛吃完，丟一句話給我就可以。",
                followup_question="要我等你現在記一筆嗎？",
                quick_replies=["現在記錄", "稍後提醒"],
                deep_link="/today",
            )
        return AgentResponse(
            message_text="我先把一個現在值得處理的小步驟放到你的決策首頁。",
            followup_question="要不要現在打開看一下？",
            quick_replies=["打開 Today", "打開 Progress"],
            deep_link=f"/{plan.decision_home.value}",
        )

    def _heuristic_understand(self, agent_input: AgentInput) -> AgentIntent:
        text = (agent_input.text or "").strip()
        lowered = text.lower()
        entities: dict[str, Any] = {}
        primary_intent = "seek_guidance" if text else "conversation"
        suggested_surface = DeliverySurface.line

        if agent_input.attachments:
            primary_intent = "log_meal"
        elif agent_input.location is not None:
            primary_intent = "recommend_food"
            entities["meal_type"] = "dinner"
            suggested_surface = DeliverySurface.liff
        elif detect_chat_correction(text):
            primary_intent = "mutate_preference"
            suggested_surface = DeliverySurface.liff
        elif self._extract_weight(text, {}) is not None or any(token in text for token in ("體重", "体重")) or "kg" in lowered:
            primary_intent = "record_weight"
            suggested_surface = DeliverySurface.liff
        elif self._looks_like_activity(text):
            primary_intent = "record_activity"
            suggested_surface = DeliverySurface.liff
        elif self._looks_like_future_event(text):
            primary_intent = "future_event"
            suggested_surface = DeliverySurface.liff
        elif self._looks_like_recommendation(text):
            primary_intent = "recommend_food"
            entities["meal_type"] = "dinner" if any(token in text for token in ("晚餐", "dinner")) else "meal"
            suggested_surface = DeliverySurface.liff
        elif self._looks_like_qa(text):
            primary_intent = "answer_grounded_qa"
        elif any(token in lowered for token in ("delete", "remove")) or any(token in text for token in ("刪除", "删除")):
            primary_intent = "meal_delete"
        elif any(token in lowered for token in ("correct", "edit")) or any(token in text for token in ("修正", "更正", "改一下")):
            primary_intent = "meal_correct"

        return AgentIntent(
            primary_intent=primary_intent,
            secondary_intents=["capture" if primary_intent == "log_meal" else "support"],
            subtext=self._extract_subtext(lowered)[:2],
            entities=entities,
            urgency=0.68 if primary_intent in {"future_event", "seek_guidance"} else 0.52,
            confidence=0.84 if primary_intent != "seek_guidance" else 0.62,
            needs_followup=primary_intent in {"log_meal", "future_event", "meal_correct"},
            suggested_surface=suggested_surface,
        )

    def _heuristic_plan(self, understanding: AgentIntent, state: AgentState) -> AgentPlan:
        actions: list[AgentAction]
        decision_home = DecisionHome.today
        if understanding.primary_intent == "log_meal":
            actions = [AgentAction(kind=AgentActionKind.mutate_meal_log, op="create")]
        elif understanding.primary_intent == "meal_correct":
            actions = [AgentAction(kind=AgentActionKind.mutate_meal_log, op="correct", entity_ref=str(understanding.entities.get("log_id") or ""))]
        elif understanding.primary_intent == "meal_delete":
            actions = [AgentAction(kind=AgentActionKind.mutate_meal_log, op="delete", entity_ref=str(understanding.entities.get("log_id") or ""))]
        elif understanding.primary_intent == "mutate_preference":
            actions = [AgentAction(kind=AgentActionKind.mutate_preference, payload=understanding.entities.get("preference_correction") or {})]
            decision_home = DecisionHome.settings
        elif understanding.primary_intent == "future_event":
            actions = [AgentAction(kind=AgentActionKind.mutate_future_event, op="create")]
            decision_home = DecisionHome.progress
        elif understanding.primary_intent == "record_weight":
            actions = [AgentAction(kind=AgentActionKind.record_weight, payload=understanding.entities)]
            decision_home = DecisionHome.progress
        elif understanding.primary_intent == "record_activity":
            actions = [AgentAction(kind=AgentActionKind.record_activity, payload=understanding.entities)]
            decision_home = DecisionHome.progress
        elif understanding.primary_intent == "recommend_food":
            actions = [AgentAction(kind=AgentActionKind.recommend_food, payload={"meal_type": understanding.entities.get("meal_type")})]
            decision_home = DecisionHome.eat
        elif understanding.primary_intent == "answer_grounded_qa":
            actions = [AgentAction(kind=AgentActionKind.answer_grounded_qa)]
        elif understanding.primary_intent == "complete_onboarding":
            actions = [AgentAction(kind=AgentActionKind.complete_onboarding, payload=understanding.entities)]
            decision_home = DecisionHome.settings
        else:
            actions = [AgentAction(kind=AgentActionKind.propose_recovery), AgentAction(kind=AgentActionKind.recommend_food, payload={"meal_type": "dinner"})]
            decision_home = DecisionHome.progress if state.weekly_state.drift_pct >= 0.1 else DecisionHome.eat
        return AgentPlan(
            actions=actions,
            requires_confirmation=any(self.guardrails.policy_for(action).policy is GuardrailPolicy.require_confirmation for action in actions),
            decision_home=decision_home,
            delivery_surface=understanding.suggested_surface,
            context_used=["goal_state", "today_state", "memory_state", "conversation_state"],
            goal_alignment={"primary_goal": 0.86},
            policy_reasons=["persona:calm_coach_partner", "line_first_delivery", "liff_first_decision_home"],
        )

    def _heuristic_respond(
        self,
        understanding: AgentIntent,
        plan: AgentPlan,
        executed: list[ExecutionRecord],
        state: AgentState,
    ) -> AgentResponse:
        pending = next((item for item in executed if item.status == "pending_confirmation"), None)
        if pending and pending.artifact.get("event_candidate"):
            candidate = pending.artifact["event_candidate"]
            return AgentResponse(
                message_text=f"我抓到一筆未來餐點事件：{candidate['event_date']} 的 {candidate['meal_type']}。",
                followup_question="要我現在先幫你存起來嗎？",
                quick_replies=["確認", "稍後"],
                deep_link="/progress",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if pending and pending.action.kind is AgentActionKind.mutate_meal_log:
            draft = pending.artifact
            kcal = draft.get("estimate_kcal") or draft.get("kcal_estimate") or 0
            return AgentResponse(
                message_text=f"我先幫你整理成一筆餐點草稿，約 {kcal} kcal。",
                followup_question=draft.get("followup_question") or "要我現在記下來嗎？",
                quick_replies=["確認", "修改", "稍後"],
                deep_link="/today",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if understanding.primary_intent == "recommend_food":
            hero = state.recommendation_state.shortlist[0] if state.recommendation_state.shortlist else None
            message = "我先幫你把這餐縮到一個比較好選的範圍。"
            if hero is not None:
                message = f"今晚先看 {hero.title}，它比較符合你現在的目標和剩餘熱量。"
            return AgentResponse(
                message_text=message,
                followup_question="如果你想比附近選項，我幫你放在 Eat 裡。",
                hero_card=HeroCard(title=hero.title if hero else "打開 Eat", body=hero.reason if hero else "到 Eat 看 bounded shortlist 與附近比較。", cta_label="打開 Eat") if hero else None,
                quick_replies=["打開 Eat", "更清淡", "看 Progress"],
                deep_link="/eat",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if understanding.primary_intent == "answer_grounded_qa":
            artifact = next((item.artifact for item in executed if item.action.kind is AgentActionKind.answer_grounded_qa), {})
            return AgentResponse(
                message_text=str(artifact.get("answer") or "我先用目前可用的 grounded context 幫你整理這題。"),
                quick_replies=["看 Today", "推薦晚餐"],
                deep_link="/today",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if understanding.primary_intent == "record_weight":
            artifact = next((item.artifact for item in executed if item.action.kind is AgentActionKind.record_weight), {})
            return AgentResponse(
                message_text=f"已經幫你記下體重 {artifact.get('weight')} kg。",
                followup_question="想看本週趨勢和恢復空間的話，可以到 Progress。",
                quick_replies=["打開 Progress", "看 Today"],
                deep_link="/progress",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if understanding.primary_intent == "record_activity":
            artifact = next((item.artifact for item in executed if item.action.kind is AgentActionKind.record_activity), {})
            return AgentResponse(
                message_text=f"已記下活動：{artifact.get('label')}，大約消耗 {artifact.get('estimated_burn_kcal')} kcal。",
                quick_replies=["看 Today", "看 Progress"],
                deep_link="/progress",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        if understanding.primary_intent == "mutate_preference":
            return AgentResponse(
                message_text="我有把這次偏好修正記下來。",
                followup_question="如果你想檢查完整設定，可以到 Settings 看一下。",
                quick_replies=["打開 Settings", "推薦晚餐"],
                deep_link="/settings",
                tone_profile=ToneProfile.calm_coach_partner,
            )
        return AgentResponse(
            message_text="今天不用硬補償，我可以幫你把後面收得順一點。",
            followup_question="要我先給你一個清淡晚餐方向、恢復建議，或兩個一起？",
            quick_replies=["清淡晚餐", "恢復建議", "打開 Progress"],
            deep_link=f"/{plan.decision_home.value}",
            tone_profile=ToneProfile.calm_coach_partner,
        )

    def _heuristic_delivery(self, state: AgentState, opportunities: list[ProactiveOpportunity]) -> DeliveryDecision:
        top = opportunities[0]
        importance = 0.0
        if top.importance_factors:
            importance = sum(item.weight for item in top.importance_factors) / len(top.importance_factors)
        should_send = importance >= 0.65
        action = DeliveryAction.line_message
        home = DecisionHome.today
        surface = DeliverySurface.line
        if top.opportunity_type in {"weekly_drift", "future_meal_event", "goal_capture", "async_refinement_ready"}:
            action = DeliveryAction.line_teaser_to_liff if top.opportunity_type != "goal_capture" else DeliveryAction.liff_inbox_only
            home = DecisionHome.progress if top.opportunity_type in {"weekly_drift", "future_meal_event"} else DecisionHome.settings if top.opportunity_type == "goal_capture" else DecisionHome.today
            surface = DeliverySurface.line if action is not DeliveryAction.liff_inbox_only else DeliverySurface.liff
        return DeliveryDecision(
            importance=importance,
            urgency=0.66 if should_send else 0.22,
            why_now="This is actionable now and can reduce friction if surfaced immediately.",
            should_send=should_send,
            suppress_reason=None if should_send else "importance_below_threshold",
            delivery_surface=surface if should_send else DeliverySurface.none,
            decision_home=home if should_send else DecisionHome.none,
            delivery_action=action if should_send else DeliveryAction.suppress,
            hero_candidate_key=top.recommended_business_action.entity_ref if top.recommended_business_action else None,
        )

    def _apply_delivery_bounds(
        self,
        state: AgentState,
        opportunities: list[ProactiveOpportunity],
        decision: DeliveryDecision,
    ) -> DeliveryDecision:
        now = utc_now()
        if not decision.should_send or decision.delivery_action is DeliveryAction.suppress:
            return decision.model_copy(update={"should_send": False, "delivery_surface": DeliverySurface.none, "decision_home": DecisionHome.none, "delivery_action": DeliveryAction.suppress})
        if decision.importance < 0.65:
            return decision.model_copy(update={"should_send": False, "suppress_reason": "importance_below_threshold", "delivery_surface": DeliverySurface.none, "decision_home": DecisionHome.none, "delivery_action": DeliveryAction.suppress})
        if state.delivery_state.proactive_sent_today >= self.provider.settings.line_daily_unsolicited_cap:
            return decision.model_copy(update={"should_send": False, "suppress_reason": "daily_cap_reached", "delivery_surface": DeliverySurface.none, "decision_home": DecisionHome.none, "delivery_action": DeliveryAction.suppress})
        last_interrupt_at = self._coerce_datetime(state.delivery_state.last_interrupt_at)
        if last_interrupt_at is not None:
            min_gap = timedelta(hours=self.provider.settings.line_min_gap_hours)
            if now - last_interrupt_at < min_gap:
                return decision.model_copy(update={"should_send": False, "suppress_reason": "min_gap_active", "delivery_surface": DeliverySurface.none, "decision_home": DecisionHome.none, "delivery_action": DeliveryAction.suppress})
        topic = opportunities[0].opportunity_type if opportunities else ""
        last_topic_at = state.delivery_state.cooldown_topics.get(topic)
        if topic and last_topic_at:
            previous = self._coerce_datetime(last_topic_at)
            if previous is not None:
                cooldown = timedelta(hours=self.provider.settings.same_topic_cooldown_hours)
                if now - previous < cooldown:
                    return decision.model_copy(update={"should_send": False, "suppress_reason": "same_topic_cooldown", "delivery_surface": DeliverySurface.none, "decision_home": DecisionHome.none, "delivery_action": DeliveryAction.suppress})
        return decision

    def _estimate_intake(
        self,
        db: Session,
        user: User,
        agent_input: AgentInput,
        telemetry: dict[str, Any],
        deadline: float,
        meal_type: str | None,
    ):
        request = self._intake_request_from_input(agent_input, {})
        stage_budget = min(self.provider.settings.understand_timeout_s, self._remaining_budget(deadline))
        if stage_budget <= 0.2:
            telemetry["fallback_reason"] = telemetry.get("fallback_reason") or "estimate_budget_exhausted"
            telemetry["deterministic_safe_mode_used"] = True
            return self.legacy_provider.estimate_meal(
                text=request.text,
                meal_type=meal_type or request.meal_type,
                mode=request.mode,
                source_mode=request.source_mode,
                clarification_count=0,
                attachments=request.attachments,
                knowledge_packet={},
                memory_packet={},
                communication_profile={},
            )
        estimate = self._run_coro(
            legacy_routes._estimate_with_knowledge(
                self.legacy_provider,
                db=db,
                user=user,
                text=request.text,
                meal_type=meal_type or request.meal_type,
                mode=request.mode,
                source_mode=request.source_mode,
                clarification_count=0,
                attachments=request.attachments,
                metadata=request.metadata,
            )
        )
        telemetry["stage_usage"]["estimate"] = {"provider_name": getattr(self.legacy_provider, "provider_name", "builderspace"), "model_name": getattr(self.legacy_provider, "default_model", ""), "prompt_version": "legacy_estimate_with_knowledge", "fallback_reason": None}
        return estimate

    def _intake_request_from_input(self, agent_input: AgentInput, payload: dict[str, Any]) -> IntakeRequest:
        attachments = [item.model_dump(mode="json") for item in agent_input.attachments]
        request = IntakeRequest(
            text=agent_input.text or "",
            meal_type=str(payload.get("meal_type") or infer_meal_type(agent_input.text or "")),
            source_mode=self._source_mode_for_input(agent_input),
            mode="standard",
            attachments=attachments,
            event_at=datetime.now(timezone.utc),
            metadata={"trace_id": agent_input.source_metadata.trace_id, "cohort": agent_input.source_metadata.cohort, "core_version": agent_input.source_metadata.core_version},
        )
        if request_has_video(request):
            request = enrich_video_intake_request(request, source_label="agentic_line")
        return request

    def _future_event_candidate(self, text: str, *, telemetry: dict[str, Any], deadline: float) -> FutureEventHint | None:
        parsed = parse_future_meal_event_text(text)
        if parsed is not None:
            return FutureEventHint(event_date=parsed.event_date.isoformat(), meal_type=parsed.meal_type, title=parsed.title, expected_kcal=parsed.expected_kcal, confidence=0.92)
        structured = self._structured_call(
            FutureEventHint,
            system_prompt=FUTURE_EVENT_HINT_PROMPT,
            prompt_version=FUTURE_EVENT_HINT_PROMPT_VERSION,
            user_payload={"text": text, "today": date.today().isoformat(), "allowed_meal_types": ["breakfast", "lunch", "dinner", "snack"]},
            timeout_s=self.provider.settings.plan_timeout_s,
            model_hint="router",
            telemetry=telemetry,
            deadline=deadline,
            stage="future_event_hint",
            max_tokens=180,
        )
        if structured is None or self._parse_date(structured.event_date) is None:
            return None
        if structured.meal_type not in {"breakfast", "lunch", "dinner", "snack"}:
            return None
        if structured.expected_kcal is not None and not 0 < structured.expected_kcal <= 3000:
            return None
        return structured

    def _intent_from_postback(self, agent_input: AgentInput) -> AgentIntent | None:
        payload = agent_input.postback_payload
        if payload is None:
            return None
        entities = {"entity_ref": payload.entity_ref, "option_key": payload.option_key, "decision_context_ref": payload.decision_context_ref, **payload.payload}
        action_map = {
            "apply": "apply_suggested_update",
            "apply_update": "apply_suggested_update",
            "dismiss": "dismiss_suggested_update",
            "dismiss_update": "dismiss_suggested_update",
            "confirm_meal_create": "log_meal",
            "confirm_meal_correction": "meal_correct",
            "delete_meal_log": "meal_delete",
            "confirm_future_event": "future_event",
            "save_preferences": "mutate_preference",
            "complete_onboarding": "complete_onboarding",
        }
        primary_intent = action_map.get(payload.action)
        if primary_intent is None:
            return None
        if primary_intent in {"apply_suggested_update", "dismiss_suggested_update"}:
            entities["job_id"] = payload.entity_ref
        if primary_intent in {"log_meal", "meal_correct", "meal_delete"}:
            entities["log_id"] = payload.entity_ref
        if primary_intent == "future_event":
            entities["event_id"] = payload.entity_ref
        return AgentIntent(primary_intent=primary_intent, secondary_intents=["structured_action"], subtext=[], entities=entities, urgency=0.9, confidence=0.95, needs_followup=False, suggested_surface=DeliverySurface.liff if agent_input.source is AgentInputSource.liff_structured_action else DeliverySurface.line)

    def _preference_correction_from_text(self, text: str | None) -> PreferenceCorrectionRequest | None:
        return detect_chat_correction(text or "") if text else None

    def _extract_subtext_clean(self, lowered: str) -> list[SubtextCategory]:
        categories: list[SubtextCategory] = []
        keyword_map = {
            SubtextCategory.guilt: ("overate", "too much", "guilty", "\u5403\u592a\u591a", "\u7206\u5403", "\u7f6a\u60e1\u611f"),
            SubtextCategory.uncertainty: ("not sure", "maybe", "uncertain", "\u4e0d\u78ba\u5b9a", "\u4e0d\u77e5\u9053", "\u597d\u50cf"),
            SubtextCategory.craving: ("craving", "want", "\u60f3\u5403", "\u5634\u994b", "\u60f3\u8981"),
            SubtextCategory.convenience_seeking: ("quick", "nearby", "\u9644\u8fd1", "\u65b9\u4fbf", "\u5feb\u901f"),
            SubtextCategory.social_pressure: ("team dinner", "party", "\u805a\u9910", "\u61c9\u916c", "\u805a\u6703"),
            SubtextCategory.goal_conflict: ("should not", "goal", "\u7834\u529f", "\u9055\u53cd\u76ee\u6a19", "\u5931\u63a7"),
            SubtextCategory.fatigue: ("tired", "\u7d2f", "\u75b2\u5026", "\u6c92\u529b"),
            SubtextCategory.desire_for_control: ("plan", "arrange", "\u5b89\u6392", "\u898f\u5283", "\u63a7\u5236"),
        }
        for category, keywords in keyword_map.items():
            if any(keyword in lowered for keyword in keywords):
                categories.append(category)
            if len(categories) >= 2:
                break
        return categories

    def _extract_weight_clean(self, text: str, payload: dict[str, Any]) -> float | None:
        if payload.get("weight") is not None:
            try:
                return float(payload["weight"])
            except (TypeError, ValueError):
                return None
        match = re.search(r"(\\d{2,3}(?:\\.\\d)?)\\s*(?:kg|\u516c\u65a4)?", text, re.IGNORECASE)
        if match is None:
            return None
        return float(match.group(1))

    def _activity_label_from_text_clean(self, text: str) -> str:
        lowered = text.lower()
        if "run" in lowered or "\u8dd1\u6b65" in text:
            return "running"
        if "walk" in lowered or "\u8d70\u8def" in text:
            return "walking"
        if "gym" in lowered or "\u5065\u8eab" in text or "\u8a13\u7df4" in text:
            return "strength_training"
        if "swim" in lowered or "\u6e38\u6cf3" in text:
            return "swimming"
        return "activity"

    def _duration_from_text_clean(self, text: str) -> int | None:
        match = re.search(r"(\\d{1,3})\\s*(?:min|mins|minutes|\u5206\u9418|\u5206)", text, re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _looks_like_activity_clean(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in ("run", "walk", "gym", "swim", "exercise")) or any(
            token in text for token in ("\u904b\u52d5", "\u8dd1\u6b65", "\u8d70\u8def", "\u5065\u8eab", "\u6e38\u6cf3", "\u8a13\u7df4")
        )

    def _looks_like_future_event_clean(self, text: str) -> bool:
        lowered = text.lower()
        has_time_signal = any(
            token in lowered for token in ("tomorrow", "next week", "next friday", "this weekend", "friday", "saturday", "sunday")
        ) or any(token in text for token in ("\u660e\u5929", "\u4e0b\u9031", "\u9031\u4e94", "\u79ae\u62dc", "\u9031\u672b"))
        has_meal_signal = any(token in lowered for token in ("dinner", "lunch", "breakfast", "party")) or any(
            token in text for token in ("\u665a\u9910", "\u5348\u9910", "\u65e9\u9910", "\u805a\u9910", "\u5403\u98ef")
        )
        return has_time_signal and has_meal_signal

    def _looks_like_recommendation_clean(self, text: str) -> bool:
        lowered = text.lower()
        return any(
            token in lowered for token in ("recommend", "suggest", "nearby", "what should i eat", "dinner", "lunch", "breakfast")
        ) or any(
            token in text
            for token in ("\u63a8\u85a6", "\u9644\u8fd1", "\u665a\u9910", "\u5348\u9910", "\u65e9\u9910", "\u5403\u4ec0\u9ebc", "\u60f3\u5403", "\u6e05\u6de1")
        )

    def _looks_like_qa_clean(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in ("calorie", "protein", "fat", "carb", "nutrition", "how many kcal")) or any(
            token in text for token in ("\u71b1\u91cf", "\u86cb\u767d\u8cea", "\u8102\u80aa", "\u78b3\u6c34", "\u5361\u8def\u91cc", "\u591a\u5c11\u5361", "\u71df\u990a")
        )

    def _heuristic_understand_clean(self, agent_input: AgentInput) -> AgentIntent:
        text = (agent_input.text or "").strip()
        lowered = text.lower()
        entities: dict[str, Any] = {}
        primary_intent = "seek_guidance" if text else "conversation"
        suggested_surface = DeliverySurface.line

        if agent_input.attachments:
            primary_intent = "log_meal"
        elif agent_input.location is not None:
            primary_intent = "recommend_food"
            entities["meal_type"] = "dinner"
            suggested_surface = DeliverySurface.liff
        elif detect_chat_correction(text):
            primary_intent = "mutate_preference"
            suggested_surface = DeliverySurface.liff
        elif self._extract_weight_clean(text, {}) is not None or any(token in text for token in ("\u9ad4\u91cd", "\u4f53\u91cd")) or "kg" in lowered:
            primary_intent = "record_weight"
            suggested_surface = DeliverySurface.liff
        elif self._looks_like_activity_clean(text):
            primary_intent = "record_activity"
            suggested_surface = DeliverySurface.liff
        elif self._looks_like_future_event_clean(text):
            primary_intent = "future_event"
            suggested_surface = DeliverySurface.liff
        elif self._looks_like_recommendation_clean(text):
            primary_intent = "recommend_food"
            entities["meal_type"] = "dinner" if any(token in text for token in ("\u665a\u9910", "dinner")) else "meal"
            suggested_surface = DeliverySurface.liff
        elif self._looks_like_qa_clean(text):
            primary_intent = "answer_grounded_qa"
        elif any(token in lowered for token in ("delete", "remove")) or any(token in text for token in ("\u522a\u9664", "\u79fb\u9664")):
            primary_intent = "meal_delete"
        elif any(token in lowered for token in ("correct", "edit")) or any(token in text for token in ("\u4fee\u6b63", "\u66f4\u6b63", "\u7de8\u8f2f")):
            primary_intent = "meal_correct"

        return AgentIntent(
            primary_intent=primary_intent,
            secondary_intents=["capture" if primary_intent == "log_meal" else "support"],
            subtext=self._extract_subtext_clean(lowered)[:2],
            entities=entities,
            urgency=0.68 if primary_intent in {"future_event", "seek_guidance"} else 0.52,
            confidence=0.84 if primary_intent != "seek_guidance" else 0.62,
            needs_followup=primary_intent in {"log_meal", "future_event", "meal_correct"},
            suggested_surface=suggested_surface,
        )

    def _extract_subtext(self, lowered: str) -> list[SubtextCategory]:
        categories: list[SubtextCategory] = []
        keyword_map = {
            SubtextCategory.guilt: ("overate", "too much", "吃太多", "爆卡", "guilty"),
            SubtextCategory.uncertainty: ("not sure", "不確定", "maybe", "好像"),
            SubtextCategory.craving: ("craving", "好想吃", "想吃", "want"),
            SubtextCategory.convenience_seeking: ("quick", "nearby", "方便", "附近", "懶得"),
            SubtextCategory.social_pressure: ("team dinner", "party", "聚餐", "應酬"),
            SubtextCategory.goal_conflict: ("should not", "破功", "減脂", "goal"),
            SubtextCategory.fatigue: ("tired", "累", "沒力", "懶"),
            SubtextCategory.desire_for_control: ("plan", "arrange", "幫我安排", "控制"),
        }
        for category, keywords in keyword_map.items():
            if any(keyword in lowered for keyword in keywords):
                categories.append(category)
            if len(categories) >= 2:
                break
        return categories

    def _source_mode_for_input(self, agent_input: AgentInput) -> str:
        if any(item.modality.value == "video" for item in agent_input.attachments):
            return "video"
        if any(item.modality.value == "image" for item in agent_input.attachments):
            return "image"
        if any(item.modality.value == "audio" for item in agent_input.attachments):
            return "audio"
        if agent_input.location is not None:
            return "location"
        return "text"

    def _extract_weight(self, text: str, payload: dict[str, Any]) -> float | None:
        if payload.get("weight") is not None:
            try:
                return float(payload["weight"])
            except (TypeError, ValueError):
                return None
        match = re.search(r"(\\d{2,3}(?:\\.\\d)?)\\s*(?:kg|公斤)?", text, re.IGNORECASE)
        if match is None:
            return None
        return float(match.group(1))

    def _activity_request(self, text: str, payload: dict[str, Any]) -> ActivityAdjustmentRequest:
        return ActivityAdjustmentRequest(date=self._parse_date(payload.get("date")) or date.today(), label=str(payload.get("label") or self._activity_label_from_text_clean(text)), estimated_burn_kcal=int(payload.get("estimated_burn_kcal") or self._activity_kcal_from_text(text)), duration_minutes=self._duration_from_text_clean(text), source="agentic", raw_input_text=text, notes=str(payload.get("notes") or ""))

    def _activity_label_from_text(self, text: str) -> str:
        lowered = text.lower()
        if "run" in lowered or "跑" in text:
            return "running"
        if "walk" in lowered or "走" in text:
            return "walking"
        if "gym" in lowered or "重訓" in text or "健身" in text:
            return "strength_training"
        if "swim" in lowered or "游泳" in text:
            return "swimming"
        return "activity"

    def _activity_kcal_from_text(self, text: str) -> int:
        match = re.search(r"(\\d{2,4})\\s*(?:kcal|cal)", text, re.IGNORECASE)
        if match is not None:
            return int(match.group(1))
        duration = self._duration_from_text_clean(text)
        if duration is not None:
            return max(duration * 6, 80)
        return 180

    def _duration_from_text(self, text: str) -> int | None:
        match = re.search(r"(\\d{1,3})\\s*(?:min|mins|minutes|分鐘)", text, re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _looks_like_activity(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in ("run", "walk", "gym", "swim", "exercise")) or any(token in text for token in ("運動", "跑步", "健身", "游泳", "散步"))

    def _looks_like_future_event(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in ("tomorrow", "next week", "dinner on", "lunch on")) or any(token in text for token in ("明天", "下週", "聚餐", "晚餐", "午餐"))

    def _looks_like_recommendation(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in ("recommend", "suggest", "nearby", "dinner", "lunch")) or any(token in text for token in ("推薦", "附近", "晚餐", "午餐", "吃什麼"))

    def _looks_like_qa(self, text: str) -> bool:
        lowered = text.lower()
        return "?" in text or any(token in lowered for token in ("calorie", "protein", "fat", "carb")) or any(token in text for token in ("熱量", "蛋白質", "脂肪", "碳水"))

    def _resolve_log(self, db: Session, user: User, entity_ref: str | None) -> MealLog | None:
        if entity_ref:
            cleaned = str(entity_ref).split(":")[-1]
            if cleaned.isdigit():
                row = db.get(MealLog, int(cleaned))
                if row is not None and row.user_id == user.id:
                    return row
        return db.scalar(select(MealLog).where(MealLog.user_id == user.id).order_by(desc(MealLog.event_at), desc(MealLog.created_at)))

    def _resolve_event(self, db: Session, user: User, entity_ref: str | None) -> MealEvent | None:
        if entity_ref:
            cleaned = str(entity_ref).split(":")[-1]
            if cleaned.isdigit():
                row = db.get(MealEvent, int(cleaned))
                if row is not None and row.user_id == user.id:
                    return row
        return db.scalar(select(MealEvent).where(MealEvent.user_id == user.id).order_by(desc(MealEvent.event_date), desc(MealEvent.created_at)))

    def _parse_date(self, raw: Any) -> date | None:
        if raw is None:
            return None
        if isinstance(raw, date) and not isinstance(raw, datetime):
            return raw
        if isinstance(raw, datetime):
            return raw.date()
        text = str(raw).strip().lower()
        if not text:
            return None
        if text == "today":
            return date.today()
        if text == "tomorrow":
            return date.today() + timedelta(days=1)
        for pattern in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    def _allowed_action_examples(self) -> list[dict[str, Any]]:
        return [{"kind": AgentActionKind.mutate_meal_log.value, "ops": ["create", "edit", "delete", "correct"]}, {"kind": AgentActionKind.mutate_preference.value}, {"kind": AgentActionKind.mutate_future_event.value, "ops": ["create", "edit", "delete"]}, {"kind": AgentActionKind.complete_onboarding.value}, {"kind": AgentActionKind.record_weight.value}, {"kind": AgentActionKind.record_activity.value}, {"kind": AgentActionKind.recommend_food.value}, {"kind": AgentActionKind.answer_grounded_qa.value}, {"kind": AgentActionKind.propose_recovery.value}, {"kind": AgentActionKind.apply_suggested_update.value}, {"kind": AgentActionKind.dismiss_suggested_update.value}]

    def _allow_actions(self) -> list[str]:
        return [AgentActionKind.record_weight.value, AgentActionKind.record_activity.value, AgentActionKind.complete_onboarding.value, AgentActionKind.recommend_food.value, AgentActionKind.answer_grounded_qa.value, AgentActionKind.propose_recovery.value, AgentActionKind.apply_suggested_update.value, AgentActionKind.dismiss_suggested_update.value]

    def _confirmation_actions(self) -> list[str]:
        return [f"{AgentActionKind.mutate_meal_log.value}:create", f"{AgentActionKind.mutate_meal_log.value}:correct", f"{AgentActionKind.mutate_meal_log.value}:delete", AgentActionKind.mutate_preference.value, f"{AgentActionKind.mutate_future_event.value}:create", f"{AgentActionKind.mutate_future_event.value}:edit", f"{AgentActionKind.mutate_future_event.value}:delete"]

    def _sanitize_actions(self, actions: list[AgentAction]) -> list[AgentAction]:
        allowed_kinds = {item["kind"] for item in self._allowed_action_examples()}
        sanitized: list[AgentAction] = []
        for action in actions:
            if action.kind.value not in allowed_kinds:
                continue
            if action.kind is AgentActionKind.mutate_meal_log and action.op not in {"create", "edit", "delete", "correct"}:
                action = action.model_copy(update={"op": "create"})
            if action.kind is AgentActionKind.mutate_future_event and action.op not in {"create", "edit", "delete"}:
                action = action.model_copy(update={"op": "create"})
            sanitized.append(action)
        return sanitized[:3]

    def _remaining_budget(self, deadline: float) -> float:
        return max(deadline - time.monotonic(), 0.0)

    def _append_fallback_step(self, telemetry: dict[str, Any], step: str) -> None:
        chain = telemetry.setdefault("provider_fallback_chain", [])
        if step not in chain:
            chain.append(step)

    @contextmanager
    def _user_lock(self, user_id: int):
        lock = self._user_locks[user_id]
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def _run_coro(self, coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        result_holder: dict[str, Any] = {}
        error_holder: list[BaseException] = []

        def runner() -> None:
            try:
                result_holder["value"] = asyncio.run(coro)
            except BaseException as exc:  # pragma: no cover
                error_holder.append(exc)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if error_holder:
            raise error_holder[0]
        return result_holder.get("value")

    def _latest_open_draft(self, db: Session, user: User) -> MealDraft | None:
        return db.scalar(select(MealDraft).where(MealDraft.user_id == user.id, MealDraft.status.in_(("awaiting_clarification", "ready_to_confirm"))).order_by(desc(MealDraft.updated_at)))

    def _coerce_datetime(self, raw: Any) -> datetime | None:
        if raw is None:
            return None
        if isinstance(raw, datetime):
            value = raw
        else:
            text = str(raw).strip()
            if not text:
                return None
            try:
                value = datetime.fromisoformat(text)
            except ValueError:
                return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
