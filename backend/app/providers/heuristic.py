from __future__ import annotations

import re

from .base import EstimateResult


CATALOG = [
    {"name": "雞胸便當", "patterns": ["雞胸便當", "舒肥雞便當"], "kcal": 520, "meal_types": ["lunch", "dinner"], "protein": True},
    {"name": "雞腿便當", "patterns": ["雞腿便當", "排骨便當"], "kcal": 780, "meal_types": ["lunch", "dinner"], "protein": True},
    {"name": "無糖豆漿", "patterns": ["無糖豆漿", "豆漿"], "kcal": 110, "meal_types": ["breakfast", "snack"], "protein": True},
    {"name": "茶葉蛋", "patterns": ["茶葉蛋", "水煮蛋"], "kcal": 75, "meal_types": ["breakfast", "snack"], "protein": True},
    {"name": "鮪魚飯糰", "patterns": ["飯糰"], "kcal": 180, "meal_types": ["breakfast", "snack"], "protein": False},
    {"name": "沙拉", "patterns": ["沙拉"], "kcal": 220, "meal_types": ["lunch", "dinner"], "protein": False},
    {"name": "壽司", "patterns": ["壽司", "sushi"], "kcal": 320, "meal_types": ["lunch", "dinner"], "protein": True},
    {"name": "牛肉麵", "patterns": ["牛肉麵"], "kcal": 650, "meal_types": ["lunch", "dinner"], "protein": True},
    {"name": "滷味", "patterns": ["滷味"], "kcal": 550, "meal_types": ["dinner", "snack"], "protein": True},
    {"name": "炸雞", "patterns": ["炸雞", "鹽酥雞"], "kcal": 480, "meal_types": ["snack", "dinner"], "protein": True},
    {"name": "火鍋", "patterns": ["火鍋"], "kcal": 800, "meal_types": ["dinner"], "protein": True},
    {"name": "合菜", "patterns": ["合菜", "聚餐"], "kcal": 900, "meal_types": ["lunch", "dinner"], "protein": True},
    {"name": "自助餐", "patterns": ["自助餐"], "kcal": 700, "meal_types": ["lunch", "dinner"], "protein": True},
    {"name": "早餐店吐司", "patterns": ["吐司", "三明治"], "kcal": 280, "meal_types": ["breakfast"], "protein": False},
    {"name": "珍奶", "patterns": ["珍奶", "手搖", "奶茶"], "kcal": 350, "meal_types": ["snack"], "protein": False},
]

GENERIC_SCENARIOS = {
    "便當": ("雞腿便當", 680, ["protein_type", "rice_portion", "fried_or_sauce"], "你這個便當的主菜是什麼？白飯大概吃了幾成？"),
    "火鍋": ("火鍋", 800, ["meat_amount", "rice", "sauce"], "火鍋你有吃白飯或王子麵嗎？肉大概是少量、普通還是偏多？"),
    "合菜": ("合菜", 900, ["high_calorie_dishes", "rice", "sharing_ratio"], "這次合菜你主要有吃哪些高熱量菜？白飯有沒有吃？"),
    "自助餐": ("自助餐", 700, ["main_items", "rice_portion"], "自助餐主要夾了哪些主菜？白飯大概幾成？"),
    "早餐": ("早餐", 350, ["main_item", "drink"], "早餐主食是什麼？有沒有搭飲料？"),
}

VAGUE_WORDS = ["一些", "隨便", "不多", "一點點", "差不多"]


class HeuristicProvider:
    async def transcribe_audio(self, *, content: bytes, mime_type: str | None = None) -> str:
        return "語音轉文字未啟用 Builder Space，請改用文字補充內容。"

    async def estimate_meal(
        self,
        *,
        text: str,
        meal_type: str | None,
        mode: str,
        source_mode: str,
        clarification_count: int,
        attachments: list[dict],
    ) -> EstimateResult:
        normalized = " ".join(filter(None, [text] + [item.get("transcript", "") for item in attachments])).strip()
        combined = normalized or ("image meal" if attachments else "")

        if not combined and source_mode in {"image", "single-photo", "before-after-photo"}:
            return EstimateResult(
                parsed_items=[],
                estimate_kcal=550,
                kcal_low=350,
                kcal_high=800,
                confidence=0.28,
                missing_slots=["main_items", "portion"],
                followup_question="我目前只有照片，請補一句：主食是什麼？大概吃了幾成？",
                uncertainty_note="只有影像沒有文字，先保守粗估。",
                status="awaiting_clarification",
            )

        items = []
        confidence = 0.35
        quantity_multiplier = self._quantity_multiplier(combined)

        for entry in CATALOG:
            if any(pattern in combined for pattern in entry["patterns"]):
                items.append(
                    {
                        "name": entry["name"],
                        "kcal": round(entry["kcal"] * quantity_multiplier),
                        "meal_types": entry["meal_types"],
                        "protein": entry["protein"],
                    }
                )
                confidence += 0.16

        if not items:
            scenario = next((key for key in GENERIC_SCENARIOS if key in combined), None)
            if scenario:
                name, kcal, missing_slots, question = GENERIC_SCENARIOS[scenario]
                return EstimateResult(
                    parsed_items=[{"name": name, "kcal": kcal, "meal_types": [meal_type or "meal"], "protein": True}],
                    estimate_kcal=kcal,
                    kcal_low=round(kcal * 0.75),
                    kcal_high=round(kcal * 1.25),
                    confidence=0.42,
                    missing_slots=missing_slots,
                    followup_question=question if clarification_count < self._budget(mode) else None,
                    uncertainty_note="場景辨識成功，但份量與高熱量細節仍不夠完整。",
                    status="awaiting_clarification" if clarification_count < self._budget(mode) else "ready_to_confirm",
                )

            question = "你剛剛這餐的主食、主菜和飲料各是什麼？大概吃了幾成？" if clarification_count < self._budget(mode) else None
            return EstimateResult(
                parsed_items=[],
                estimate_kcal=500,
                kcal_low=250,
                kcal_high=850,
                confidence=0.2,
                missing_slots=["main_items", "portion", "high_calorie_items"],
                followup_question=question,
                uncertainty_note="目前資訊不足，只能先做很粗的預估。",
                status="awaiting_clarification" if question else "ready_to_confirm",
            )

        total = sum(item["kcal"] for item in items)
        missing_slots = []
        if not self._has_quantity_cue(combined):
            missing_slots.append("portion")
        if any(word in combined for word in ["分食", "一起吃", "共食"]):
            missing_slots.append("sharing_ratio")
        if any(word in combined for word in ["沒吃完", "剩下", "吃幾成"]):
            missing_slots.append("leftover_ratio")
        if any(word in combined for word in VAGUE_WORDS):
            confidence -= 0.08

        question = None
        if missing_slots and clarification_count < self._budget(mode) and confidence < 0.82:
            question = self._pick_question(missing_slots)

        return EstimateResult(
            parsed_items=items,
            estimate_kcal=total,
            kcal_low=round(total * 0.82),
            kcal_high=round(total * 1.18),
            confidence=max(0.25, min(round(confidence, 2), 0.92)),
            missing_slots=missing_slots,
            followup_question=question,
            uncertainty_note="已抓到主要食物，但份量仍有不確定性。" if missing_slots else "估算已達可接受可信度。",
            status="awaiting_clarification" if question else "ready_to_confirm",
        )

    def _budget(self, mode: str) -> int:
        return {"quick": 1, "standard": 2, "fine": 4}.get(mode, 2)

    def _quantity_multiplier(self, text: str) -> float:
        if any(word in text for word in ["兩份", "雙份", "double", "兩個"]):
            return 2.0
        if any(word in text for word in ["半", "一半", "半碗", "半份"]):
            return 0.75
        return 1.0

    def _has_quantity_cue(self, text: str) -> bool:
        return bool(re.search(r"半|一半|吃了幾成|全吃|吃完|兩份|兩個|\d+%|\d+成", text))

    def _pick_question(self, missing_slots: list[str]) -> str:
        if "portion" in missing_slots:
            return "這餐大概吃了幾成？如果有白飯，飯量是半碗、正常還是偏多？"
        if "sharing_ratio" in missing_slots:
            return "這餐是幾個人分？你吃比較少、一半，還是比較多？"
        if "leftover_ratio" in missing_slots:
            return "有沒有沒吃完？主食和主菜分別大概吃了幾成？"
        return "請再補一句最重要的高熱量項和份量。"
