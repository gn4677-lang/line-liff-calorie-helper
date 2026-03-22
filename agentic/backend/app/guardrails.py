from __future__ import annotations

from dataclasses import dataclass

from .contracts import AgentAction, AgentActionKind, GuardrailPolicy


@dataclass(slots=True)
class GuardrailDecision:
    policy: GuardrailPolicy
    reason: str


class DeterministicGuardrails:
    """Non-LLM authority over writes, filters, and delivery permissions."""

    def policy_for(self, action: AgentAction) -> GuardrailDecision:
        if action.kind is AgentActionKind.mutate_meal_log and action.op in {"create", "correct", "delete"}:
            return GuardrailDecision(
                policy=GuardrailPolicy.require_confirmation,
                reason="Meal writes require deterministic confirmation.",
            )
        if action.kind is AgentActionKind.mutate_preference:
            return GuardrailDecision(
                policy=GuardrailPolicy.require_confirmation,
                reason="Preference mutations must be explicitly confirmed.",
            )
        if action.kind is AgentActionKind.mutate_future_event:
            return GuardrailDecision(
                policy=GuardrailPolicy.require_confirmation,
                reason="Future events need deterministic validation and confirmation.",
            )
        if action.kind in {
            AgentActionKind.recommend_food,
            AgentActionKind.answer_grounded_qa,
            AgentActionKind.propose_recovery,
            AgentActionKind.dismiss_suggested_update,
        }:
            return GuardrailDecision(
                policy=GuardrailPolicy.allow_without_confirmation,
                reason="Read-only or guidance actions may execute immediately.",
            )
        if action.kind in {
            AgentActionKind.complete_onboarding,
            AgentActionKind.record_weight,
            AgentActionKind.record_activity,
            AgentActionKind.apply_suggested_update,
        }:
            return GuardrailDecision(
                policy=GuardrailPolicy.allow_without_confirmation,
                reason="Structured user actions may execute immediately.",
            )
        return GuardrailDecision(
            policy=GuardrailPolicy.forbid,
            reason="Unknown or unsupported action was rejected by guardrails.",
        )
