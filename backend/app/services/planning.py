from __future__ import annotations

from ..models import Preference
from ..schemas import CompensationResponse, DayPlanResponse


def build_day_plan(target_kcal: int, preference: Preference | None = None) -> DayPlanResponse:
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
        reason_factors.append("你最近早餐通常吃得比較少，所以把熱量額度往午晚餐和彈性空間移。")

    if preference and preference.dinner_style == "indulgent":
        dinner_ratio += 0.05
        lunch_ratio -= 0.03
        flex_ratio -= 0.02
        reason_factors.append("晚餐你通常想吃得更放鬆一點，所以晚餐額度有拉高。")
    elif preference and preference.dinner_style == "high_protein":
        reason_factors.append("晚餐偏好高蛋白，所以晚餐配額會保留給蛋白質密度高的選項。")

    allocations = {
        "breakfast": round(target_kcal * breakfast_ratio),
        "lunch": round(target_kcal * lunch_ratio),
        "dinner": round(target_kcal * dinner_ratio),
        "flex": round(target_kcal * flex_ratio),
    }

    return DayPlanResponse(
        target_kcal=target_kcal,
        allocations=allocations,
        coach_message="這是今天的基礎配額。先照這個抓大方向，之後再依實際進食微調。",
        reason_factors=reason_factors,
    )


def build_compensation_plan(extra_kcal: int, compensation_style: str = "gentle") -> CompensationResponse:
    gentle = max(round(extra_kcal / 2), 0)
    spread = max(round(extra_kcal / 3), 0)
    reason_factors: list[str] = []

    if compensation_style == "normal_return":
        preferred_label = "回到正常就好"
        reason_factors.append("你偏向不要做激烈補償，所以先以回到正常軌道為主。")
    elif compensation_style == "distributed_2_3d":
        preferred_label = "分 2-3 天攤平"
        reason_factors.append("你比較適合把回收分散到幾天內，壓力會更低。")
    elif compensation_style == "let_system_decide":
        preferred_label = "讓系統幫我決定"
        reason_factors.append("系統先用較溫和的回收節奏，避免單日補償過度。")
    else:
        preferred_label = "小幅回收 1 天"
        reason_factors.append("你可接受短天數的小幅回收，所以先給 1 天溫和版本。")

    options = [
        {
            "label": "回到正常就好",
            "daily_adjustment": 0,
            "days": 0,
            "note": "不做額外補償，明天直接回到正常熱量安排。",
        },
        {
            "label": "小幅回收 1 天",
            "daily_adjustment": gentle,
            "days": 1,
            "note": "明天小幅收回一些熱量，但不做極端節食。",
        },
        {
            "label": "分 2-3 天攤平",
            "daily_adjustment": spread,
            "days": 3,
            "note": "把回收分散到幾天內，穩定度通常比單日硬砍更好。",
        },
        {
            "label": "讓系統幫我決定",
            "daily_adjustment": spread,
            "days": 2,
            "note": "先用中間方案，之後再依實際進食和體重變化調整。",
        },
    ]

    return CompensationResponse(
        options=options,
        coach_message=f"先以「{preferred_label}」作為預設方向，再看你接下來兩三天的進食狀況。",
        reason_factors=reason_factors,
    )
