from __future__ import annotations

from ..schemas import CompensationResponse, DayPlanResponse


def build_day_plan(target_kcal: int) -> DayPlanResponse:
    allocations = {
        "breakfast": round(target_kcal * 0.2),
        "lunch": round(target_kcal * 0.35),
        "dinner": round(target_kcal * 0.35),
        "flex": round(target_kcal * 0.1),
    }
    return DayPlanResponse(
        target_kcal=target_kcal,
        allocations=allocations,
        coach_message="今天先照這個框架走，彈性熱量留給突發狀況或晚上的選擇。",
    )


def build_compensation_plan(extra_kcal: int) -> CompensationResponse:
    gentle = max(round(extra_kcal / 2), 0)
    spread = max(round(extra_kcal / 3), 0)
    return CompensationResponse(
        options=[
            {"label": "不補償", "daily_adjustment": 0, "days": 0, "note": "直接回到正常目標，避免報復性節食。"},
            {"label": "小幅回收", "daily_adjustment": gentle, "days": 1, "note": "明天稍微收一點，但不要極端。"},
            {"label": "三天攤平", "daily_adjustment": spread, "days": 3, "note": "如果今天超標較多，分 3 天回收更穩。"},
        ],
        coach_message="補償的目的不是懲罰，而是回到穩定節奏。",
    )
