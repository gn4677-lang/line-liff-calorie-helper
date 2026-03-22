from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Food, Preference, User
from ..providers.heuristic import CATALOG
from ..schemas import RecommendationItem, RecommendationsResponse
from .llm_support import rerank_candidates_sync
from .memory import DISLIKE_LABELS, build_explainability_factors


KEYWORD_LABELS = {
    "韓": "korean",
    "炸": "fried",
    "沙拉": "cold_food",
    "超商": "convenience_store",
    "便利商店": "convenience_store",
    "雞胸": "high_protein",
    "蛋白": "high_protein",
    "飲料": "sugary_drink",
    "奶茶": "sugary_drink",
}

GROUP_LABELS = {
    "balanced": "balanced",
    "convenient": "convenient",
    "comfort": "comfort",
    "high_protein": "high_protein",
}

GROUP_REASONS = {
    "balanced": "Fits the current calorie budget without being too sparse.",
    "convenient": "Easy to obtain quickly when convenience matters.",
    "comfort": "Leans toward a more satisfying comfort-style pick.",
    "high_protein": "A stronger protein-first option for steadier intake.",
}


def get_recommendations(
    db: Session,
    user: User,
    meal_type: str | None,
    remaining_kcal: int,
    *,
    provider: Any | None = None,
    memory_packet: dict[str, Any] | None = None,
    communication_profile: dict[str, Any] | None = None,
) -> RecommendationsResponse:
    communication_profile = communication_profile or ((memory_packet or {}).get("communication_profile") or {})
    preference = db.scalar(select(Preference).where(Preference.user_id == user.id))
    stored = list(
        db.scalars(
            select(Food)
            .where(Food.user_id == user.id)
            .order_by(desc(Food.is_golden), desc(Food.is_favorite), desc(Food.usage_count), Food.name)
        )
    )

    dislike_labels = {_normalize_dislike(item) for item in (preference.hard_dislikes if preference else [])}
    dislike_names = set(preference.dislikes if preference else [])
    candidates: list[RecommendationItem] = []

    for food in stored:
        if meal_type and food.meal_types and meal_type not in food.meal_types:
            continue
        if food.name in dislike_names:
            continue
        if _food_matches_dislike(food.name, dislike_labels):
            continue
        if food.kcal_high and food.kcal_high > max(remaining_kcal + 150, 250):
            continue

        group = _group_for_food(food.name, food.convenience_level, food.comfort_level)
        candidates.append(
            RecommendationItem(
                food_id=food.id,
                name=food.name,
                meal_types=food.meal_types or ["meal"],
                kcal_low=food.kcal_low,
                kcal_high=food.kcal_high,
                group=group,
                reason=_reason_for_group(group),
                reason_factors=_reason_factors_for_food(db, user, food.name, meal_type),
                external_links=food.external_links,
                is_favorite=food.is_favorite,
                is_golden=food.is_golden,
            )
        )

    if not candidates:
        for item in CATALOG[:8]:
            if meal_type and meal_type not in item["meal_types"]:
                continue
            if _food_matches_dislike(item["name"], dislike_labels):
                continue
            kcal_low = round(item["kcal"] * 0.9)
            kcal_high = round(item["kcal"] * 1.1)
            if kcal_high > max(remaining_kcal + 150, 250):
                continue
            group = GROUP_LABELS["high_protein"] if item["protein"] else GROUP_LABELS["balanced"]
            candidates.append(
                RecommendationItem(
                    name=item["name"],
                    meal_types=item["meal_types"],
                    kcal_low=kcal_low,
                    kcal_high=kcal_high,
                    group=group,
                    reason=_reason_for_group(group),
                    reason_factors=_reason_factors_for_food(db, user, item["name"], meal_type),
                )
            )

    items = candidates[:12]
    hero_reason = ""
    coach_message = ""
    strategy_label = ""
    policy_contract: dict[str, Any] = {}
    if items:
        rerank_payload = _apply_llm_recommendation_rerank(
            items,
            provider=provider if settings.eat_policy_llm_enabled else None,
            meal_type=meal_type,
            remaining_kcal=remaining_kcal,
            memory_packet=memory_packet,
            communication_profile=communication_profile,
        )
        hero_reason = rerank_payload["hero_reason"]
        coach_message = rerank_payload["coach_message"]
        strategy_label = rerank_payload["strategy_label"]
        policy_contract = rerank_payload.get("policy_contract") or {}
        if rerank_payload.get("provider_usage"):
            policy_contract["llm_usage"] = rerank_payload["provider_usage"]
    if not hero_reason and items:
        hero_reason = items[0].reason_factors[0] if items[0].reason_factors else items[0].reason
    if not coach_message and items:
        coach_message = _default_coach_message(items[0], remaining_kcal)
    if not strategy_label and items:
        strategy_label = _default_strategy_label(items[0], remaining_kcal)
    return RecommendationsResponse(
        remaining_kcal=remaining_kcal,
        items=items,
        coach_message=coach_message,
        hero_reason=hero_reason,
        strategy_label=strategy_label,
        refining=False,
        policy_contract=policy_contract,
    )


def _normalize_dislike(raw: str) -> str:
    return DISLIKE_LABELS.get(raw, raw)


def _food_matches_dislike(name: str, dislike_labels: set[str]) -> bool:
    labels = {value for key, value in KEYWORD_LABELS.items() if key in name}
    return bool(labels & dislike_labels)


def _group_for_food(name: str, convenience: int, comfort: int) -> str:
    lowered = name.lower()
    if any(token in name for token in ["雞胸", "蛋白", "沙拉"]) or "subway" in lowered:
        return GROUP_LABELS["high_protein"]
    if convenience >= 4 or any(token in name for token in ["超商", "便利商店", "7-11", "全家"]):
        return GROUP_LABELS["convenient"]
    if comfort >= 4 or any(token in name for token in ["炸", "雞排", "拉麵", "pizza"]):
        return GROUP_LABELS["comfort"]
    return GROUP_LABELS["balanced"]


def _reason_for_group(group: str) -> str:
    return GROUP_REASONS.get(group, GROUP_REASONS["balanced"])


def _reason_factors_for_food(db: Session, user: User, food_name: str, meal_type: str | None) -> list[str]:
    factors = build_explainability_factors(db, user, meal_type=meal_type)
    if any(token in food_name for token in ["雞胸", "蛋白", "沙拉"]):
        factors.append("Leans higher-protein than the user's recent average.")
    if any(token in food_name for token in ["超商", "便利商店", "7-11", "全家"]):
        factors.append("Fast to pick up when convenience matters.")
    return factors[:4]


def _recommendation_key(item: RecommendationItem) -> str:
    if item.food_id is not None:
        return f"food:{item.food_id}"
    return f"name:{item.name}"


def _default_coach_message(item: RecommendationItem, remaining_kcal: int) -> str:
    if remaining_kcal <= 450:
        return f"{item.name} is the safest fit while keeping today's remaining budget under control."
    if item.group == GROUP_LABELS["high_protein"]:
        return f"{item.name} is the strongest protein-first option in the current shortlist."
    if item.group == GROUP_LABELS["comfort"]:
        return f"{item.name} gives you a comfort-leaning pick without blowing up the day."
    if item.group == GROUP_LABELS["convenient"]:
        return f"{item.name} is the lowest-friction option when convenience matters most."
    return f"{item.name} is the steadiest option from the current shortlist."


def _default_strategy_label(item: RecommendationItem, remaining_kcal: int) -> str:
    if remaining_kcal <= 450:
        return "budget_guard"
    if item.group == GROUP_LABELS["high_protein"]:
        return "protein_anchor"
    if item.group == GROUP_LABELS["comfort"]:
        return "comfort_control"
    if item.group == GROUP_LABELS["convenient"]:
        return "low_friction"
    return "steady_default"


def _apply_llm_recommendation_rerank(
    items: list[RecommendationItem],
    *,
    provider: Any | None,
    meal_type: str | None,
    remaining_kcal: int,
    memory_packet: dict[str, Any] | None,
    communication_profile: dict[str, Any] | None,
) -> dict[str, str]:
    payload = rerank_candidates_sync(
        provider,
        task_label="recommendations",
        meal_type=meal_type,
        remaining_kcal=remaining_kcal,
        memory_packet=memory_packet,
        communication_profile=communication_profile,
        candidates=[
            {
                "key": _recommendation_key(item),
                "name": item.name,
                "group": item.group,
                "kcal_low": item.kcal_low,
                "kcal_high": item.kcal_high,
                "meal_types": item.meal_types,
                "reason_factors": item.reason_factors,
                "is_favorite": item.is_favorite,
                "is_golden": item.is_golden,
            }
            for item in items
        ],
    )
    if not payload["ordered_keys"] and not payload["reason_factors"]:
        return {
            "hero_reason": payload["hero_reason"],
            "coach_message": payload["coach_message"],
            "strategy_label": payload["strategy_label"],
            "policy_contract": payload.get("policy_contract") or {},
            "provider_usage": payload.get("provider_usage") or {},
        }

    by_key = {_recommendation_key(item): item for item in items}
    reordered = [by_key[key] for key in payload["ordered_keys"] if key in by_key]
    reordered.extend(item for item in items if _recommendation_key(item) not in payload["ordered_keys"])
    items[:] = reordered[: len(items)]

    for item in items:
        override = payload["reason_factors"].get(_recommendation_key(item))
        if override:
            item.reason_factors = override[:4]
    return {
        "hero_reason": payload["hero_reason"],
        "coach_message": payload["coach_message"],
        "strategy_label": payload["strategy_label"],
        "policy_contract": payload.get("policy_contract") or {},
        "provider_usage": payload.get("provider_usage") or {},
    }
