from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import Food, Preference, User
from ..providers.heuristic import CATALOG
from ..schemas import RecommendationItem, RecommendationsResponse
from .memory import DISLIKE_LABELS, build_explainability_factors


KEYWORD_LABELS = {
    "韓式": "korean",
    "炸": "fried",
    "沙拉": "cold_food",
    "便利商店": "convenience_store",
    "超商": "convenience_store",
    "雞胸": "high_protein",
    "蛋白": "high_protein",
    "飲料": "sugary_drink",
    "奶茶": "sugary_drink",
}


def get_recommendations(db: Session, user: User, meal_type: str | None, remaining_kcal: int) -> RecommendationsResponse:
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
            group = "高蛋白優先" if item["protein"] else "最穩"
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

    return RecommendationsResponse(remaining_kcal=remaining_kcal, items=candidates[:12])


def _normalize_dislike(raw: str) -> str:
    return DISLIKE_LABELS.get(raw, raw)


def _food_matches_dislike(name: str, dislike_labels: set[str]) -> bool:
    labels = {value for key, value in KEYWORD_LABELS.items() if key in name}
    return bool(labels & dislike_labels)


def _group_for_food(name: str, convenience: int, comfort: int) -> str:
    if any(token in name for token in ["雞胸", "高蛋白", "Subway", "subway", "沙拉雞"]):
        return "高蛋白優先"
    if convenience >= 4 or any(token in name for token in ["超商", "便利商店", "7-11", "全家"]):
        return "最方便"
    if comfort >= 4 or any(token in name for token in ["炸", "滷味", "雞排", "鹹酥雞"]):
        return "想吃爽一點"
    return "最穩"


def _reason_for_group(group: str) -> str:
    mapping = {
        "最穩": "熱量和可得性都比較穩，適合拿來當保守選項。",
        "最方便": "取得成本低，現在就能執行，不太需要額外準備。",
        "想吃爽一點": "保留一點滿足感，但還在今天可接受的範圍內。",
        "高蛋白優先": "蛋白質密度較高，通常更適合減脂期的主力選擇。",
        "聚餐前適合": "先留一些熱量空間，之後比較不容易失控。",
        "爆卡後適合": "這類選項回收力道比較溫和，不容易造成補償壓力。",
    }
    return mapping.get(group, "這個選項和你今天的剩餘熱量與可得性相對匹配。")


def _reason_factors_for_food(db: Session, user: User, food_name: str, meal_type: str | None) -> list[str]:
    factors = build_explainability_factors(db, user, meal_type=meal_type)
    if any(token in food_name for token in ["雞胸", "高蛋白", "沙拉雞"]):
        factors.append("這個選項的蛋白質密度比較高。")
    if any(token in food_name for token in ["超商", "便利商店", "7-11", "全家"]):
        factors.append("這類選項通常取得很快，執行門檻低。")
    return factors[:4]
