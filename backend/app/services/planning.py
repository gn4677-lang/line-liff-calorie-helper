from __future__ import annotations

from datetime import date, timedelta

from ..models import Preference
from ..schemas import CompensationResponse, DayPlanResponse


def build_day_plan(target_kcal: int, preference: Preference | None = None, overlay: dict | None = None) -> DayPlanResponse:
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
        reason_factors.append("最近早餐通常不是主力，所以把彈性留到中晚餐。")

    if preference and preference.dinner_style == "indulgent":
        dinner_ratio += 0.05
        lunch_ratio -= 0.03
        flex_ratio -= 0.02
        reason_factors.append("晚餐通常想吃得比較滿足，所以晚餐配額略高。")
    elif preference and preference.dinner_style == "high_protein":
        reason_factors.append("晚餐優先保留高蛋白選項。")

    if overlay:
        reason_factors.append(overlay.get("overlay_reason", "這幾天先照補償預算走。"))

    allocations = {
        "breakfast": round(effective_target * breakfast_ratio),
        "lunch": round(effective_target * lunch_ratio),
        "dinner": round(effective_target * dinner_ratio),
        "flex": round(effective_target * flex_ratio),
    }

    return DayPlanResponse(
        target_kcal=effective_target,
        allocations=allocations,
        coach_message="這是今天比較穩的配額分配。",
        reason_factors=reason_factors[:4],
    )


def build_compensation_plan(extra_kcal: int, compensation_style: str = "gentle", *, base_target: int = 1800) -> CompensationResponse:
    gentle = max(round(extra_kcal / 2), 0)
    spread = max(round(extra_kcal / 3), 0)
    reason_factors: list[str] = []

    if compensation_style == "normal_return":
        preferred_label = "回到正常"
        reason_factors.append("先回到正常即可，避免報復性節食。")
    elif compensation_style == "distributed_2_3d":
        preferred_label = "分 2-3 天攤平"
        reason_factors.append("比較適合不想單日壓太低的做法。")
    elif compensation_style == "let_system_decide":
        preferred_label = "讓系統幫我決定"
        reason_factors.append("系統會優先選比較穩的回收節奏。")
    else:
        preferred_label = "小幅回收 1 天"
        reason_factors.append("先做小幅回收，比較不容易反彈。")

    options = [
        {
            "label": "回到正常",
            "daily_adjustment": 0,
            "days": 0,
            "note": "不做額外補償，只回到平常節奏。",
            "overlay": None,
        },
        {
            "label": "小幅回收 1 天",
            "daily_adjustment": gentle,
            "days": 1,
            "note": "明天小幅收一下即可。",
            "overlay": build_recovery_overlay(base_target, gentle, 1, "明天小幅回收 1 天。"),
        },
        {
            "label": "分 2-3 天攤平",
            "daily_adjustment": spread,
            "days": 3,
            "note": "把回收攤平，日常感受會比較穩。",
            "overlay": build_recovery_overlay(base_target, spread, 3, "這幾天先把超標分散回收。"),
        },
        {
            "label": "讓系統幫我決定",
            "daily_adjustment": spread,
            "days": 2,
            "note": "預設先走比較溫和的 2 天回收。",
            "overlay": build_recovery_overlay(base_target, spread, 2, "系統先用溫和 2 天回收。"),
        },
    ]

    return CompensationResponse(
        options=options,
        coach_message=f"如果要調整，這次我會先偏向「{preferred_label}」。",
        reason_factors=reason_factors[:4],
    )


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
