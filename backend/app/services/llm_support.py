from __future__ import annotations

import asyncio
import copy
import threading
from typing import Any

from ..config import settings
from ..providers.base import EstimateResult
from ..schemas import (
    ClarificationDecision,
    CoachingDecision,
    RecommendationPolicyDecision,
    RelevantMemorySlice,
    StructuredIntentRoute,
)


ALLOWED_SLOT_NAMES = {
    "main_items",
    "portion",
    "rice_portion",
    "high_calorie_items",
    "fried_or_sauce",
    "sharing_ratio",
    "leftover_ratio",
    "drink",
    "secondary_sides",
    "dessert_presence",
    "soup",
    "combo_items",
    "broth_style",
    "extra_toppings",
    "main_components",
}
ALLOWED_TASK_LABELS = {
    "meal_log_now",
    "meal_log_correction",
    "remaining_or_recommendation",
    "future_event_probe",
    "weekly_drift_probe",
    "weight_log",
    "nutrition_or_food_qa",
    "preference_or_memory_correction",
    "meta_help",
    "fallback_ambiguous",
}


def llm_available(provider: Any) -> bool:
    return bool(settings.ai_builder_token) and provider is not None and hasattr(provider, "complete_structured")


async def complete_structured_safe(
    provider: Any,
    *,
    system_prompt: str,
    user_payload: dict[str, Any],
    max_tokens: int = 220,
    temperature: float = 0.1,
    model_hint: str = "chat",
    request_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not llm_available(provider):
        return {}
    try:
        result = await provider.complete_structured(
            system_prompt=system_prompt,
            user_payload=user_payload,
            max_tokens=max_tokens,
            temperature=temperature,
            model_hint=model_hint,
            request_options=request_options,
        )
    except Exception:
        return {}
    return result if isinstance(result, dict) else {}


def complete_structured_sync(
    provider: Any,
    *,
    system_prompt: str,
    user_payload: dict[str, Any],
    max_tokens: int = 220,
    temperature: float = 0.1,
    model_hint: str = "chat",
    request_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        return asyncio.run(
            complete_structured_safe(
                provider,
                system_prompt=system_prompt,
                user_payload=user_payload,
                max_tokens=max_tokens,
                temperature=temperature,
                model_hint=model_hint,
                request_options=request_options,
            )
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run()

    result: dict[str, Any] = {}
    error: list[BaseException] = []

    def _runner() -> None:
        try:
            result.update(_run())
        except BaseException as exc:  # pragma: no cover
            error.append(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result


def _extract_provider_usage(payload: dict[str, Any]) -> dict[str, Any]:
    usage = payload.pop("_provider_usage", None)
    return usage if isinstance(usage, dict) else {}


async def review_estimate_with_llm(
    provider: Any,
    *,
    text: str,
    meal_type: str | None,
    mode: str,
    source_mode: str,
    estimate: EstimateResult,
    knowledge_packet: dict[str, Any] | None,
    memory_packet: dict[str, Any] | None,
    communication_profile: dict[str, Any] | None,
) -> EstimateResult:
    payload = {
        "text": text,
        "meal_type": meal_type,
        "mode": mode,
        "source_mode": source_mode,
        "estimate": {
            "parsed_items": estimate.parsed_items,
            "estimate_kcal": estimate.estimate_kcal,
            "kcal_low": estimate.kcal_low,
            "kcal_high": estimate.kcal_high,
            "confidence": estimate.confidence,
            "missing_slots": estimate.missing_slots,
            "followup_question": estimate.followup_question,
            "uncertainty_note": estimate.uncertainty_note,
            "comparison_candidates": estimate.comparison_candidates,
            "ambiguity_flags": estimate.ambiguity_flags,
            "evidence_slots": estimate.evidence_slots,
        },
        "knowledge_packet": knowledge_packet or {},
        "memory_packet": memory_packet or {},
        "communication_profile": communication_profile or {},
    }
    review = await complete_structured_safe(
        provider,
        system_prompt=(
            "Review one meal-estimation result for confidence gating and clarification strategy. "
            "Reply with JSON only using this schema: "
            "{\"confidence_delta\":0.0,\"suggested_missing_slots\":[],\"primary_uncertainties\":[],"
            "\"suggested_question_slot\":null,\"suggested_followup_question\":null,"
            "\"clarification_mode\":\"none\",\"auto_record_ok\":null,\"generic_estimate_ok\":null}."
        ),
        user_payload=payload,
        max_tokens=220,
        temperature=0.0,
        model_hint="frontier",
    )
    if not review:
        return estimate
    usage = _extract_provider_usage(review)

    updated = copy.deepcopy(estimate)
    delta = float(review.get("confidence_delta") or 0.0)
    delta = max(-0.18, min(0.18, round(delta, 3)))
    suggested_slots = [
        slot
        for slot in review.get("suggested_missing_slots", [])
        if isinstance(slot, str) and slot in ALLOWED_SLOT_NAMES
    ]
    if suggested_slots:
        updated.missing_slots = list(dict.fromkeys([*updated.missing_slots, *suggested_slots]))

    primary_uncertainties = [
        str(item).strip()
        for item in review.get("primary_uncertainties", [])
        if str(item).strip()
    ][:3]
    suggested_slot = review.get("suggested_question_slot")
    if suggested_slot not in updated.missing_slots:
        suggested_slot = None
    suggested_question = str(review.get("suggested_followup_question") or "").strip() or None
    if suggested_question and (updated.followup_question is None or len(updated.followup_question) < 12):
        updated.followup_question = suggested_question
    raw_mode = str(review.get("clarification_mode") or "").strip()
    if raw_mode not in {"direct_clarification", "comparison_mode", "generic_estimate_fallback", "ask_first_handoff", "none"}:
        raw_mode = "comparison_mode" if suggested_slot in {"portion", "rice_portion"} else "direct_clarification"
    contract = ClarificationDecision(
        mode=raw_mode or "none",
        suggested_slot=suggested_slot,
        followup_question=suggested_question,
        primary_uncertainties=primary_uncertainties,
        auto_record_ok=bool(review.get("auto_record_ok")) if review.get("auto_record_ok") is not None else None,
        generic_estimate_ok=bool(review.get("generic_estimate_ok")) if review.get("generic_estimate_ok") is not None else None,
    )

    evidence_slots = dict(updated.evidence_slots or {})
    evidence_slots["llm_confidence_delta"] = delta
    evidence_slots["llm_primary_uncertainties"] = primary_uncertainties
    evidence_slots["llm_suggested_slot"] = suggested_slot
    evidence_slots["llm_clarification_mode"] = contract.mode
    if suggested_question:
        evidence_slots["llm_followup_question"] = suggested_question
    if review.get("auto_record_ok") is not None:
        evidence_slots["llm_auto_record_ok"] = bool(review.get("auto_record_ok"))
    if review.get("generic_estimate_ok") is not None:
        evidence_slots["llm_generic_estimate_ok"] = bool(review.get("generic_estimate_ok"))
    evidence_slots["clarification_decision_contract"] = contract.model_dump()
    if usage:
        evidence_slots["llm_review_usage"] = usage
    updated.evidence_slots = evidence_slots
    return updated


async def classify_intent_with_llm(
    provider: Any,
    *,
    text: str,
    open_draft_present: bool,
) -> dict[str, Any]:
    response = await complete_structured_safe(
        provider,
        system_prompt=(
            "Classify one LINE chat turn into exactly one task label for a calorie-tracking assistant. "
            "Reply with JSON only using this schema: "
            "{\"task\":\"fallback_ambiguous\",\"confidence\":0.0,\"handoff_hint\":\"\"}."
        ),
        user_payload={
            "text": text,
            "open_draft_present": open_draft_present,
            "allowed_tasks": sorted(ALLOWED_TASK_LABELS),
        },
        max_tokens=120,
        temperature=0.0,
        model_hint="router",
    )
    usage = _extract_provider_usage(response)
    task = str(response.get("task") or "fallback_ambiguous").strip()
    if task not in ALLOWED_TASK_LABELS:
        task = "fallback_ambiguous"
    try:
        confidence = float(response.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    contract = StructuredIntentRoute(
        task=task,
        confidence=max(0.0, min(confidence, 1.0)),
        handoff_hint=str(response.get("handoff_hint") or "").strip()[:120],
        route_policy="llm_first",
        route_source="llm",
        fast_path=False,
    )
    payload = contract.model_dump()
    payload["provider_usage"] = usage
    payload["contract"] = contract.model_dump()
    return payload


def rerank_candidates_sync(
    provider: Any,
    *,
    task_label: str,
    meal_type: str | None,
    remaining_kcal: int | None,
    memory_packet: dict[str, Any] | None,
    communication_profile: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    response = complete_structured_sync(
        provider,
        system_prompt=(
            "Rerank a bounded shortlist of meal candidates for one user. "
            "Respect kcal limits and stated preferences. "
            "Reply with JSON only using this schema: "
            "{\"ordered_keys\":[],\"reason_factors\":{},\"hero_reason\":\"\",\"coach_message\":\"\",\"strategy_label\":\"\"}."
        ),
        user_payload={
            "task_label": task_label,
            "meal_type": meal_type,
            "remaining_kcal": remaining_kcal,
            "memory_packet": memory_packet or {},
            "communication_profile": communication_profile or {},
            "candidates": candidates,
        },
        max_tokens=260,
        temperature=0.1,
        model_hint="chat",
    )
    usage = _extract_provider_usage(response)
    allowed_keys = {str(item.get("key")) for item in candidates if item.get("key")}
    ordered_keys: list[str] = []
    for item in response.get("ordered_keys", []):
        key = str(item)
        if key in allowed_keys and key not in ordered_keys:
            ordered_keys.append(key)

    reason_factors: dict[str, list[str]] = {}
    raw_factors = response.get("reason_factors") or {}
    if isinstance(raw_factors, dict):
        for key, values in raw_factors.items():
            if key not in allowed_keys or not isinstance(values, list):
                continue
            filtered = [str(value).strip() for value in values if str(value).strip()]
            if filtered:
                reason_factors[key] = filtered[:4]

    hero_reason = str(response.get("hero_reason") or "").strip()
    coach_message = str(response.get("coach_message") or "").strip()
    strategy_label = str(response.get("strategy_label") or "").strip()
    hero_key = ordered_keys[0] if ordered_keys else None
    contract = RecommendationPolicyDecision(
        ordered_keys=ordered_keys,
        hero_key=hero_key,
        hero_reason=hero_reason[:180],
        coach_message=coach_message[:220],
        strategy_label=strategy_label[:80],
        reason_factors=reason_factors,
        stage="refined_hero_choice" if response else "deterministic_fallback",
    )
    return {
        "ordered_keys": ordered_keys,
        "reason_factors": reason_factors,
        "hero_reason": contract.hero_reason,
        "coach_message": contract.coach_message,
        "strategy_label": contract.strategy_label,
        "policy_contract": contract.model_dump(),
        "provider_usage": usage,
    }


def select_relevant_memory_slice_sync(
    provider: Any,
    *,
    task_label: str,
    text: str,
    meal_type: str | None,
    memory_packet: dict[str, Any] | None,
) -> dict[str, Any]:
    packet = memory_packet or {}
    response = complete_structured_sync(
        provider,
        system_prompt=(
            "Select the most relevant memory evidence for one bounded task. "
            "Do not invent new memory. "
            "Reply with JSON only using this schema: "
            "{\"signal_labels\":[],\"hypothesis_labels\":[],\"recent_example_ids\":[]}."
        ),
        user_payload={
            "task_label": task_label,
            "text": text,
            "meal_type": meal_type,
            "memory_packet": packet,
        },
        max_tokens=180,
        temperature=0.0,
        model_hint="chat",
    )
    usage = _extract_provider_usage(response)
    signal_labels = {str(item).strip() for item in response.get("signal_labels", []) if str(item).strip()}
    hypothesis_labels = {str(item).strip() for item in response.get("hypothesis_labels", []) if str(item).strip()}
    recent_example_ids = {str(item).strip() for item in response.get("recent_example_ids", []) if str(item).strip()}

    compact = dict(packet)
    if packet.get("relevant_signals"):
        compact["relevant_signals"] = [
            item for item in packet.get("relevant_signals", [])
            if str(item.get("canonical_label") or "") in signal_labels
        ] or packet.get("relevant_signals", [])[:4]
    if packet.get("active_hypotheses"):
        compact["active_hypotheses"] = [
            item for item in packet.get("active_hypotheses", [])
            if str(item.get("label") or "") in hypothesis_labels
        ] or packet.get("active_hypotheses", [])[:4]
    if packet.get("recent_evidence"):
        compact["recent_evidence"] = [
            item for item in packet.get("recent_evidence", [])
            if str(item.get("log_id") or item.get("event_at") or "") in recent_example_ids
        ] or packet.get("recent_evidence", [])[:2]
    if packet.get("recent_acceptance"):
        compact["recent_acceptance"] = [
            item for item in packet.get("recent_acceptance", [])
            if str(item.get("event_at") or item.get("description") or "") in recent_example_ids
        ] or packet.get("recent_acceptance", [])[:4]
    contract = RelevantMemorySlice(
        task_label=task_label,
        signal_labels=sorted(signal_labels),
        hypothesis_labels=sorted(hypothesis_labels),
        recent_example_ids=sorted(recent_example_ids),
        selected_signal_count=len(compact.get("relevant_signals", []) or []),
        selected_hypothesis_count=len(compact.get("active_hypotheses", []) or []),
        selected_recent_example_count=len(compact.get("recent_evidence", []) or []) + len(compact.get("recent_acceptance", []) or []),
        relevance_selected_by_llm=bool(response),
    )
    compact["relevance_selected_by_llm"] = contract.relevance_selected_by_llm
    compact["_relevant_memory_slice_contract"] = contract.model_dump()
    if usage:
        compact["_relevant_memory_slice_usage"] = usage
    return compact


def compose_weekly_coaching_sync(
    provider: Any,
    *,
    weekly_envelope: dict[str, Any],
    planning_packet: dict[str, Any] | None,
    communication_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    response = complete_structured_sync(
        provider,
        system_prompt=(
            "Interpret one deterministic weekly-calorie envelope for a coaching assistant. "
            "Do not invent new numeric conclusions, metabolic claims, or safety labels outside the envelope. "
            "Reply with JSON only using this schema: "
            "{\"intervention_importance\":\"low\",\"urgency\":\"low\",\"coach_message\":\"\","
            "\"strategy_label\":\"\",\"reason_factors\":[],\"trigger_type\":null}."
        ),
        user_payload={
            "weekly_envelope": weekly_envelope,
            "planning_packet": planning_packet or {},
            "communication_profile": communication_profile or {},
        },
        max_tokens=260,
        temperature=0.1,
        model_hint="chat",
    )
    usage = _extract_provider_usage(response)
    contract = CoachingDecision(
        intervention_importance=str(response.get("intervention_importance") or "low").strip()[:40] or "low",
        urgency=str(response.get("urgency") or "low").strip()[:40] or "low",
        coach_message=str(response.get("coach_message") or "").strip()[:220],
        strategy_label=str(response.get("strategy_label") or "").strip()[:80],
        reason_factors=[str(item).strip() for item in response.get("reason_factors", []) if str(item).strip()][:4],
        trigger_type=str(response.get("trigger_type") or "").strip()[:80] or None,
        envelope_summary=weekly_envelope,
    )
    payload = contract.model_dump()
    payload["provider_usage"] = usage
    payload["contract"] = contract.model_dump()
    return payload


def personalize_day_plan_sync(
    provider: Any,
    *,
    target_kcal: int,
    allocations: dict[str, int],
    overlay: dict[str, Any] | None,
    planning_packet: dict[str, Any],
    communication_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    response = complete_structured_sync(
        provider,
        system_prompt=(
            "Adjust a day meal-allocation plan for one user. "
            "Keep the allocation structure realistic and bounded. "
            "Reply with JSON only using this schema: "
            "{\"allocations\":{\"breakfast\":0,\"lunch\":0,\"dinner\":0,\"flex\":0}}."
        ),
        user_payload={
            "target_kcal": target_kcal,
            "baseline_allocations": allocations,
            "overlay": overlay or {},
            "planning_packet": planning_packet,
            "communication_profile": communication_profile or {},
        },
        max_tokens=240,
        temperature=0.1,
        model_hint="chat",
    )
    usage = _extract_provider_usage(response)
    result: dict[str, Any] = {
        "allocations": allocations,
        "provider_usage": usage,
    }
    candidate_allocations = response.get("allocations") or {}
    if isinstance(candidate_allocations, dict):
        normalized = {}
        for key in ("breakfast", "lunch", "dinner", "flex"):
            value = candidate_allocations.get(key)
            if value is None:
                normalized = {}
                break
            normalized[key] = max(int(value), 0)
        if normalized and abs(sum(normalized.values()) - target_kcal) <= 40:
            result["allocations"] = normalized
    return result


def personalize_compensation_sync(
    provider: Any,
    *,
    extra_kcal: int,
    planning_packet: dict[str, Any],
    communication_profile: dict[str, Any] | None,
    options: list[dict[str, Any]],
) -> dict[str, Any]:
    response = complete_structured_sync(
        provider,
        system_prompt=(
            "Select a compensation-plan option for one user. "
            "Reply with JSON only using this schema: "
            "{\"recommended_label\":\"\",\"option_notes\":{}}."
        ),
        user_payload={
            "extra_kcal": extra_kcal,
            "planning_packet": planning_packet,
            "communication_profile": communication_profile or {},
            "options": options,
        },
        max_tokens=220,
        temperature=0.1,
        model_hint="chat",
    )
    usage = _extract_provider_usage(response)
    recommended_label = str(response.get("recommended_label") or "").strip()
    option_notes = response.get("option_notes") if isinstance(response.get("option_notes"), dict) else {}
    return {
        "recommended_label": recommended_label,
        "option_notes": {str(key): str(value).strip()[:220] for key, value in option_notes.items()},
        "provider_usage": usage,
    }


def compose_day_plan_copy_sync(
    provider: Any,
    *,
    target_kcal: int,
    allocations: dict[str, int],
    overlay: dict[str, Any] | None,
    planning_packet: dict[str, Any],
    communication_profile: dict[str, Any] | None,
    base_reason_factors: list[str],
) -> dict[str, Any]:
    response = complete_structured_sync(
        provider,
        system_prompt=(
            "Write the final coaching copy for one day meal-allocation plan. "
            "Do not change the allocations. "
            "Reply with JSON only using this schema: "
            "{\"coach_message\":\"\",\"reason_factors\":[]}."
        ),
        user_payload={
            "target_kcal": target_kcal,
            "final_allocations": allocations,
            "overlay": overlay or {},
            "planning_packet": planning_packet,
            "communication_profile": communication_profile or {},
            "base_reason_factors": base_reason_factors,
        },
        max_tokens=220,
        temperature=0.15,
        model_hint="chat",
    )
    usage = _extract_provider_usage(response)
    coach_message = str(response.get("coach_message") or "").strip()
    reason_factors = [str(item).strip() for item in response.get("reason_factors", []) if str(item).strip()][:4]
    return {
        "coach_message": coach_message[:220],
        "reason_factors": reason_factors,
        "copy_applied": bool(response),
        "provider_usage": usage,
    }


def compose_compensation_copy_sync(
    provider: Any,
    *,
    extra_kcal: int,
    planning_packet: dict[str, Any],
    communication_profile: dict[str, Any] | None,
    options: list[dict[str, Any]],
    recommended_label: str,
    base_reason_factors: list[str],
) -> dict[str, Any]:
    response = complete_structured_sync(
        provider,
        system_prompt=(
            "Write the final coaching copy for one compensation-plan decision. "
            "Do not invent new options. "
            "Reply with JSON only using this schema: "
            "{\"coach_message\":\"\",\"reason_factors\":[]}."
        ),
        user_payload={
            "extra_kcal": extra_kcal,
            "planning_packet": planning_packet,
            "communication_profile": communication_profile or {},
            "options": options,
            "recommended_label": recommended_label,
            "base_reason_factors": base_reason_factors,
        },
        max_tokens=220,
        temperature=0.15,
        model_hint="chat",
    )
    usage = _extract_provider_usage(response)
    coach_message = str(response.get("coach_message") or "").strip()
    reason_factors = [str(item).strip() for item in response.get("reason_factors", []) if str(item).strip()][:4]
    return {
        "coach_message": coach_message[:220],
        "reason_factors": reason_factors,
        "copy_applied": bool(response),
        "provider_usage": usage,
    }


def synthesize_memory_hypotheses_sync(
    provider: Any,
    *,
    user_preferences: dict[str, Any],
    reporting_bias: dict[str, Any],
    signals: list[dict[str, Any]],
    recent_logs: list[dict[str, Any]],
    existing_hypotheses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    response = complete_structured_sync(
        provider,
        system_prompt=(
            "Synthesize up to 3 cautious food-behavior hypotheses from bounded user evidence. "
            "Do not invent certainty. "
            "Reply with JSON only using this schema: "
            "{\"hypotheses\":[{\"dimension\":\"\",\"label\":\"\",\"statement\":\"\","
            "\"confidence\":0.0,\"status\":\"tentative\",\"supporting_signals\":[]}]}."
        ),
        user_payload={
            "user_preferences": user_preferences,
            "reporting_bias": reporting_bias,
            "signals": signals,
            "recent_logs": recent_logs,
            "existing_hypotheses": existing_hypotheses,
        },
        max_tokens=320,
        temperature=0.1,
        model_hint="frontier",
    )
    hypotheses: list[dict[str, Any]] = []
    for item in response.get("hypotheses", []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()[:120]
        statement = str(item.get("statement") or "").strip()[:400]
        dimension = str(item.get("dimension") or "").strip()[:60]
        if not label or not statement or not dimension:
            continue
        status = str(item.get("status") or "tentative").strip().lower()
        if status not in {"tentative", "active"}:
            status = "tentative"
        supporting_signals = [
            str(signal).strip()
            for signal in item.get("supporting_signals", [])
            if str(signal).strip()
        ][:4]
        hypotheses.append(
            {
                "dimension": dimension,
                "label": label,
                "statement": statement,
                "confidence": max(0.45, min(float(item.get("confidence") or 0.6), 0.92)),
                "status": status,
                "supporting_signals": supporting_signals,
            }
        )
    return hypotheses[:3]
