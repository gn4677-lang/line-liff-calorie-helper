from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import Food, Preference, User
from ..providers.heuristic import CATALOG
from ..schemas import RecommendationItem, RecommendationsResponse


def get_recommendations(db: Session, user: User, meal_type: str | None, remaining_kcal: int) -> RecommendationsResponse:
    preference = db.scalar(select(Preference).where(Preference.user_id == user.id))
    dislikes = set(preference.dislikes if preference else [])

    stored = list(
        db.scalars(
            select(Food)
            .where(Food.user_id == user.id)
            .order_by(desc(Food.is_golden), desc(Food.is_favorite), desc(Food.usage_count), Food.name)
        )
    )

    candidates: list[RecommendationItem] = []
    for food in stored:
        if meal_type and food.meal_types and meal_type not in food.meal_types:
            continue
        if food.name in dislikes:
            continue
        if food.kcal_high and food.kcal_high > max(remaining_kcal + 150, 250):
            continue
        group = _group_for_food(food.name, food.convenience_level, food.comfort_level, any(token in food.name for token in ["雞", "蛋", "豆漿", "魚"]))
        candidates.append(
            RecommendationItem(
                food_id=food.id,
                name=food.name,
                meal_types=food.meal_types or ["meal"],
                kcal_low=food.kcal_low,
                kcal_high=food.kcal_high,
                group=group,
                reason=_reason_for_group(group),
                external_links=food.external_links,
                is_favorite=food.is_favorite,
                is_golden=food.is_golden,
            )
        )

    if not candidates:
        for item in CATALOG[:8]:
            if meal_type and meal_type not in item["meal_types"]:
                continue
            group = "高蛋白優先" if item["protein"] else "最穩"
            candidates.append(
                RecommendationItem(
                    name=item["name"],
                    meal_types=item["meal_types"],
                    kcal_low=round(item["kcal"] * 0.9),
                    kcal_high=round(item["kcal"] * 1.1),
                    group=group,
                    reason=_reason_for_group(group),
                )
            )

    return RecommendationsResponse(remaining_kcal=remaining_kcal, items=candidates[:12])


def _group_for_food(name: str, convenience: int, comfort: int, high_protein: bool) -> str:
    if high_protein:
        return "高蛋白優先"
    if convenience >= 4:
        return "最方便"
    if comfort >= 4 or any(token in name for token in ["炸", "奶茶", "咖哩"]):
        return "想吃爽一點"
    return "最穩"


def _reason_for_group(group: str) -> str:
    mapping = {
        "最穩": "熱量範圍相對穩定，適合先守住今天。",
        "最方便": "準備成本低，最適合忙碌時直接執行。",
        "想吃爽一點": "滿足感較高，但還在可控範圍。",
        "高蛋白優先": "在熱量可控下優先拉高蛋白質密度。",
        "聚餐前適合": "適合先預留一些熱量彈性。",
        "爆卡後適合": "偏保守、回穩友善。",
    }
    return mapping.get(group, "符合目前情境。")
