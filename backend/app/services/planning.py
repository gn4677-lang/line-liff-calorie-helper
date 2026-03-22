from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..models import Preference
from ..schemas import CompensationResponse, DayPlanResponse
from .llm_support import (
    compose_compensation_copy_sync,
    compose_day_plan_copy_sync,
    personalize_compensation_sync,
    personalize_day_plan_sync,
)


def build_day_plan(
    target_kcal: int,
    preference: Preference | None = None,
    overlay: dict | None = None,
    *,
    provider: Any | None = None,
    planning_packet: dict[str, Any] | None = None,
    communication_profile: dict[str, Any] | None = None,
) -> DayPlanResponse:
    communication_profile = communication_profile or ((planning_packet or {}).get("communication_profile") or {})
    effective_target = overlay.get("overlay_allocations", {}).get("today_target", target_kcal) if overlay else target_kcal
    breakfast_ratio = 0.2
    lunch_ratio = 0.35
    dinner_ratio = 0.35
    flex_ratio = 0.1
    reason_factors: list[str] = []

    if preference and preference.breakfast_habit == "rare":
        breakfast_ratio = 0.1
        lunch_ratio = 0.38
        dinner_ratio = 0.37
        flex_ratio = 0.15
        reason_factors.append("Breakfast is often skipped, so more budget stays later in the day.")

    if preference and preference.dinner_style == "indulgent":
        dinner_ratio += 0.05
        lunch_ratio -= 0.03
        flex_ratio -= 0.02
        reason_factors.append("Dinner usually carries more psychological weight, so the split leaves extra room there.")
    elif preference and preference.dinner_style == "high_protein":
        reason_factors.append("Dinner preference is more protein-forward than average.")

    if overlay:
        reason_factors.append(overlay.get("overlay_reason", "A temporary recovery overlay is active."))

    allocations = {
        "breakfast": round(effective_target * breakfast_ratio),
        "lunch": round(effective_target * lunch_ratio),
        "dinner": round(effective_target * dinner_ratio),
        "flex": round(effective_target * flex_ratio),
    }
    plan = DayPlanResponse(
        target_kcal=effective_target,
        allocations=allocations,
        coach_message="This is the steady split for today.",
        reason_factors=reason_factors[:4],
        metadata={},
    )
    if provider is not None and planning_packet is not None:
        personalization = personalize_day_plan_sync(
            provider,
            target_kcal=effective_target,
            allocations=plan.allocations,
            overlay=overlay,
            planning_packet=planning_packet,
            communication_profile=communication_profile,
        )
        plan.allocations = personalization["allocations"]
        llm_usage_parts: list[dict[str, Any]] = []
        if personalization.get("provider_usage"):
            llm_usage_parts.append(personalization["provider_usage"])
        copy_payload = compose_day_plan_copy_sync(
            provider,
            target_kcal=effective_target,
            allocations=plan.allocations,
            overlay=overlay,
            planning_packet=planning_packet,
            communication_profile=communication_profile,
            base_reason_factors=plan.reason_factors,
        )
        if copy_payload["coach_message"]:
            plan.coach_message = copy_payload["coach_message"]
        if copy_payload["reason_factors"]:
            plan.reason_factors = copy_payload["reason_factors"]
        if copy_payload.get("provider_usage"):
            llm_usage_parts.append(copy_payload["provider_usage"])
        if llm_usage_parts:
            plan.metadata["llm_usage"] = _merge_usage(*llm_usage_parts)
    return plan


def build_compensation_plan(
    extra_kcal: int,
    compensation_style: str = "gentle",
    *,
    base_target: int = 1800,
    provider: Any | None = None,
    planning_packet: dict[str, Any] | None = None,
    communication_profile: dict[str, Any] | None = None,
) -> CompensationResponse:
    communication_profile = communication_profile or ((planning_packet or {}).get("communication_profile") or {})
    gentle = max(round(extra_kcal / 2), 0)
    spread = max(round(extra_kcal / 3), 0)
    reason_factors: list[str] = []

    if compensation_style == "normal_return":
        preferred_label = "Return to baseline"
        reason_factors.append("Preference says not to stretch compensation unless needed.")
    elif compensation_style == "distributed_2_3d":
        preferred_label = "Spread over 2-3 days"
        reason_factors.append("Preference leans toward smoother recovery over several days.")
    elif compensation_style == "let_system_decide":
        preferred_label = "System pick"
        reason_factors.append("System can choose the lowest-friction option from the current context.")
    else:
        preferred_label = "Light 1-day recovery"
        reason_factors.append("A light single-day correction keeps the next day usable.")

    options = [
        {
            "label": "Return to baseline",
            "daily_adjustment": 0,
            "days": 0,
            "note": "Do not apply a recovery overlay. Just resume the normal target.",
            "overlay": None,
        },
        {
            "label": "Light 1-day recovery",
            "daily_adjustment": gentle,
            "days": 1,
            "note": "Use one lighter day to absorb part of the excess.",
            "overlay": build_recovery_overlay(base_target, gentle, 1, "One-day recovery overlay"),
        },
        {
            "label": "Spread over 2-3 days",
            "daily_adjustment": spread,
            "days": 3,
            "note": "Lower the daily target modestly over several days.",
            "overlay": build_recovery_overlay(base_target, spread, 3, "Multi-day recovery overlay"),
        },
        {
            "label": "System pick",
            "daily_adjustment": spread,
            "days": 2,
            "note": "A middle-ground recovery when context is mixed.",
            "overlay": build_recovery_overlay(base_target, spread, 2, "System-selected recovery overlay"),
        },
    ]

    compensation = CompensationResponse(
        options=options,
        coach_message=f"If you want a nudge, I would start from '{preferred_label}'.",
        reason_factors=reason_factors[:4],
        metadata={},
    )
    if provider is not None and planning_packet is not None:
        personalization = personalize_compensation_sync(
            provider,
            extra_kcal=extra_kcal,
            planning_packet=planning_packet,
            communication_profile=communication_profile,
            options=compensation.options,
        )
        llm_usage_parts: list[dict[str, Any]] = []
        if personalization.get("provider_usage"):
            llm_usage_parts.append(personalization["provider_usage"])
        recommended_label = personalization["recommended_label"]
        if recommended_label:
            compensation.options = sorted(
                compensation.options,
                key=lambda item: 0 if item.get("label") == recommended_label else 1,
            )
        for option in compensation.options:
            override = personalization["option_notes"].get(option.get("label", ""))
            if override:
                option["note"] = override
        copy_payload = compose_compensation_copy_sync(
            provider,
            extra_kcal=extra_kcal,
            planning_packet=planning_packet,
            communication_profile=communication_profile,
            options=compensation.options,
            recommended_label=recommended_label,
            base_reason_factors=compensation.reason_factors,
        )
        if copy_payload["coach_message"]:
            compensation.coach_message = copy_payload["coach_message"]
        if copy_payload["reason_factors"]:
            compensation.reason_factors = copy_payload["reason_factors"]
        if copy_payload.get("provider_usage"):
            llm_usage_parts.append(copy_payload["provider_usage"])
        if llm_usage_parts:
            compensation.metadata["llm_usage"] = _merge_usage(*llm_usage_parts)
    return compensation


def build_recovery_overlay(base_target: int, daily_adjustment: int, days: int, reason: str, *, start_date: date | None = None) -> dict:
    start = start_date or date.today()
    overlay_allocations = {}
    for offset in range(days):
        current = start + timedelta(days=offset)
        overlay_allocations[current.isoformat()] = max(base_target - daily_adjustment, 1200)
    today_target = overlay_allocations.get(start.isoformat(), base_target)
    return {
        "overlay_days": days,
        "overlay_allocations": {"today_target": today_target, "by_date": overlay_allocations},
        "overlay_reason": reason,
        "overlay_active_until": (start + timedelta(days=max(days - 1, 0))).isoformat(),
    }


def _merge_usage(*parts: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "request_count": 0,
        "estimated_cost_usd": 0.0,
        "model_names": [],
        "model_hints": [],
    }
    seen_models: set[str] = set()
    seen_hints: set[str] = set()
    last_non_null: dict[str, Any] = {}
    for part in parts:
        if not isinstance(part, dict):
            continue
        merged["prompt_tokens"] += int(part.get("prompt_tokens") or 0)
        merged["completion_tokens"] += int(part.get("completion_tokens") or 0)
        merged["total_tokens"] += int(part.get("total_tokens") or 0)
        merged["request_count"] += int(part.get("request_count") or 0)
        merged["estimated_cost_usd"] = round(float(merged["estimated_cost_usd"]) + float(part.get("estimated_cost_usd") or 0.0), 6)
        model_name = str(part.get("model_name") or "").strip()
        if model_name and model_name not in seen_models:
            seen_models.add(model_name)
            merged["model_names"].append(model_name)
        model_hint = str(part.get("model_hint") or "").strip()
        if model_hint and model_hint not in seen_hints:
            seen_hints.add(model_hint)
            merged["model_hints"].append(model_hint)
        for key in (
            "provider_name",
            "rate_limit_remaining_requests",
            "rate_limit_remaining_tokens",
            "rate_limit_reset_requests_s",
            "rate_limit_reset_tokens_s",
            "request_budget_per_hour",
            "token_budget_per_hour",
            "cost_budget_usd_per_day",
        ):
            if part.get(key) is not None:
                last_non_null[key] = part.get(key)
    if not merged["total_tokens"]:
        merged["total_tokens"] = merged["prompt_tokens"] + merged["completion_tokens"]
    merged.update(last_non_null)
    return merged
