from __future__ import annotations

import re

from .base import EstimateResult


GENERIC_ITEMS = [
    {"name": "烤雞便當", "patterns": ["chicken bento", "bento", "便當"], "kcal": 620, "meal_types": ["lunch", "dinner"], "protein": True},
    {"name": "鹽酥雞大餐", "patterns": ["fried chicken", "鹽酥雞", "雞排"], "kcal": 720, "meal_types": ["lunch", "dinner", "snack"], "protein": True},
    {"name": "日式拉麵", "patterns": ["ramen", "拉麵"], "kcal": 840, "meal_types": ["lunch", "dinner"], "protein": True},
    {"name": "漢堡套餐", "patterns": ["burger", "漢堡"], "kcal": 700, "meal_types": ["breakfast", "lunch", "dinner"], "protein": True},
    {"name": "溫沙拉", "patterns": ["salad", "沙拉"], "kcal": 220, "meal_types": ["lunch", "dinner"], "protein": False},
    {"name": "茶葉蛋", "patterns": ["tea egg", "茶葉蛋"], "kcal": 75, "meal_types": ["breakfast", "snack"], "protein": True},
    {"name": "烤地瓜", "patterns": ["sweet potato", "地瓜"], "kcal": 180, "meal_types": ["breakfast", "snack"], "protein": False},
]

CATALOG = GENERIC_ITEMS

GENERIC_SCENARIOS = {
    "bento": ("bento meal", 650, ["main_items", "rice_portion", "fried_or_sauce"]),
    "ramen": ("ramen", 840, ["broth_style", "extra_toppings"]),
    "fried": ("fried snack meal", 700, ["main_components", "portion", "oil_level"]),
    "luwei": ("luwei bowl", 480, ["main_components", "sauce"]),
}

VAGUE_WORDS = ["something", "some", "a bit", "maybe", "\u4e00\u4e9b", "\u597d\u50cf", "\u5927\u6982"]


class HeuristicProvider:
    prompt_version = "heuristic-estimation-v2"

    async def transcribe_audio(self, *, content: bytes, mime_type: str | None = None) -> str:
        return "Audio transcription is unavailable on the heuristic provider."

    async def estimate_meal(
        self,
        *,
        text: str,
        meal_type: str | None,
        mode: str,
        source_mode: str,
        clarification_count: int,
        attachments: list[dict],
        knowledge_packet: dict | None = None,
    ) -> EstimateResult:
        combined = " ".join(filter(None, [text] + [item.get("transcript", "") for item in attachments])).strip()
        evidence_slots = self._empty_evidence_slots(source_mode)
        packet = knowledge_packet or {}

        if not combined and source_mode in {"image", "single-photo", "before-after-photo", "video"}:
            return EstimateResult(
                parsed_items=[],
                estimate_kcal=550,
                kcal_low=350,
                kcal_high=820,
                confidence=0.28,
                missing_slots=["main_items", "portion"],
                followup_question="What were the main items and about how much did you eat?",
                uncertainty_note="Only the media source is available, so this is still a broad placeholder range.",
                status="awaiting_clarification",
                evidence_slots=evidence_slots,
                ambiguity_flags=["media_only"],
                knowledge_packet_version=packet.get("version"),
                matched_knowledge_packs=packet.get("matched_packs", []),
            )

        if packet.get("primary_matches"):
            return self._estimate_from_packet(
                text=combined,
                mode=mode,
                clarification_count=clarification_count,
                source_mode=source_mode,
                packet=packet,
            )

        return self._estimate_from_generic_rules(
            text=combined,
            mode=mode,
            clarification_count=clarification_count,
            source_mode=source_mode,
            meal_type=meal_type or "meal",
            packet=packet,
        )

    def _estimate_from_packet(
        self,
        *,
        text: str,
        mode: str,
        clarification_count: int,
        source_mode: str,
        packet: dict,
    ) -> EstimateResult:
        matches = packet.get("primary_matches", [])
        multiplier = self._quantity_multiplier(text)
        strategy = packet.get("primary_strategy", "generic")
        low = sum(int(item.get("kcal_low") or 0) for item in matches)
        high = sum(int(item.get("kcal_high") or 0) for item in matches)
        delta_low, delta_high = self._modifier_delta(text, strategy=strategy)
        low = max(round(low * multiplier + delta_low), 0)
        high = max(round(high * multiplier + delta_high), low)
        estimate = round((low + high) / 2)

        items = [{"name": item["name"], "kcal": round(((item["kcal_low"] + item["kcal_high"]) / 2) * multiplier)} for item in matches]
        evidence_slots = self._empty_evidence_slots(source_mode)
        evidence_slots["identified_items"] = bool(items)
        evidence_slots["main_items"] = [item["name"] for item in items]
        evidence_slots["portion_signal"] = self._has_quantity_cue(text)
        evidence_slots["high_calorie_modifiers"] = bool(delta_high)
        evidence_slots["knowledge_strategy"] = strategy

        missing_slots = list(packet.get("followup_slots", []))
        if strategy == "component_sum" and not evidence_slots["portion_signal"]:
            missing_slots = list(dict.fromkeys(["portion", *missing_slots]))
        if strategy in {"shop_profile", "broth_rule"} and not any(token in text for token in ["\u52a0\u9eb5", "extra noodles", "\u52a0\u53c9\u71d2", "backfat", "\u80cc\u8102"]):
            missing_slots = list(dict.fromkeys(["extra_toppings", *missing_slots]))

        confidence = 0.56
        if strategy in {"exact_item", "shop_profile"}:
            confidence += 0.14
        if evidence_slots["portion_signal"]:
            confidence += 0.08
        if missing_slots:
            confidence -= 0.04 * min(len(missing_slots), 3)

        question = None
        if missing_slots and clarification_count < self._budget(mode):
            question = self._pick_question(missing_slots, strategy=strategy)

        return EstimateResult(
            parsed_items=items,
            estimate_kcal=estimate,
            kcal_low=low,
            kcal_high=high,
            confidence=max(0.3, min(round(confidence, 2), 0.92)),
            missing_slots=missing_slots,
            followup_question=question,
            uncertainty_note=self._uncertainty_note(strategy, missing_slots),
            status="awaiting_clarification" if question else "ready_to_confirm",
            evidence_slots=evidence_slots,
            comparison_candidates=[item["name"] for item in items[:3]],
            ambiguity_flags=[word for word in VAGUE_WORDS if word in text.lower()],
            knowledge_packet_version=packet.get("version"),
            matched_knowledge_packs=packet.get("matched_packs", []),
        )

    def _estimate_from_generic_rules(
        self,
        *,
        text: str,
        mode: str,
        clarification_count: int,
        source_mode: str,
        meal_type: str,
        packet: dict,
    ) -> EstimateResult:
        lowered = text.lower()
        items = []
        multiplier = self._quantity_multiplier(lowered)
        evidence_slots = self._empty_evidence_slots(source_mode)
        for entry in GENERIC_ITEMS:
            if any(pattern.lower() in lowered for pattern in entry["patterns"]):
                items.append({"name": entry["name"], "kcal": round(entry["kcal"] * multiplier), "protein": entry["protein"]})

        if items:
            evidence_slots["identified_items"] = True
            evidence_slots["main_items"] = [item["name"] for item in items]
            total = sum(item["kcal"] for item in items)
            missing_slots = [] if self._has_quantity_cue(lowered) else ["portion"]
            question = None
            if missing_slots and clarification_count < self._budget(mode):
                question = self._pick_question(missing_slots, strategy="generic")
            return EstimateResult(
                parsed_items=items,
                estimate_kcal=total,
                kcal_low=round(total * 0.82),
                kcal_high=round(total * 1.18),
                confidence=0.52 if not missing_slots else 0.42,
                missing_slots=missing_slots,
                followup_question=question,
                uncertainty_note="This estimate is based on generic meal patterns because no stronger local match was available.",
                status="awaiting_clarification" if question else "ready_to_confirm",
                evidence_slots=evidence_slots,
                comparison_candidates=[item["name"] for item in items[:3]],
                ambiguity_flags=[word for word in VAGUE_WORDS if word in lowered],
                knowledge_packet_version=packet.get("version"),
                matched_knowledge_packs=packet.get("matched_packs", []),
            )

        scenario = self._generic_scenario(lowered)
        if scenario:
            name, kcal, missing_slots = scenario
            question = None
            if clarification_count < self._budget(mode):
                question = self._pick_question(missing_slots, strategy="generic")
            return EstimateResult(
                parsed_items=[{"name": name, "kcal": kcal, "protein": True}],
                estimate_kcal=kcal,
                kcal_low=round(kcal * 0.75),
                kcal_high=round(kcal * 1.25),
                confidence=0.38,
                missing_slots=missing_slots,
                followup_question=question,
                uncertainty_note="This is still a broad scenario estimate. The main items and portion could move the total a lot.",
                status="awaiting_clarification",
                evidence_slots=evidence_slots,
                comparison_candidates=["small", "regular", "large"],
                ambiguity_flags=[word for word in VAGUE_WORDS if word in lowered],
                knowledge_packet_version=packet.get("version"),
                matched_knowledge_packs=packet.get("matched_packs", []),
            )

        return EstimateResult(
            parsed_items=[],
            estimate_kcal=500,
            kcal_low=260,
            kcal_high=860,
            confidence=0.2,
            missing_slots=["main_items", "portion", "high_calorie_items"],
            followup_question="What were the main items and roughly how much did you finish?",
            uncertainty_note="The description is still too vague for a reliable estimate.",
            status="awaiting_clarification",
            evidence_slots=evidence_slots,
            comparison_candidates=["small", "regular", "large"],
            ambiguity_flags=[word for word in VAGUE_WORDS if word in lowered],
            knowledge_packet_version=packet.get("version"),
            matched_knowledge_packs=packet.get("matched_packs", []),
        )

    def _modifier_delta(self, text: str, *, strategy: str) -> tuple[int, int]:
        lowered = text.lower()
        low = 0
        high = 0
        if any(token in lowered for token in ["\u52a0\u9eb5", "extra noodles"]):
            low += 180
            high += 260
        if any(token in lowered for token in ["\u52a0\u53c9\u71d2", "extra chashu", "double meat"]):
            low += 120
            high += 260
        if any(token in lowered for token in ["backfat", "\u80cc\u8102", "butter", "\u5976\u6cb9"]):
            low += 80
            high += 180
        if strategy == "component_sum" and any(token in lowered for token in ["\u91ac", "sauce", "\u8fa3\u6cb9", "\u9ebb\u8fa3"]):
            low += 30
            high += 120
        return low, high

    def _generic_scenario(self, text: str) -> tuple[str, int, list[str]] | None:
        if any(token in text for token in ["bento", "\u4fbf\u7576"]):
            return GENERIC_SCENARIOS["bento"]
        if any(token in text for token in ["ramen", "\u62c9\u9eb5"]):
            return GENERIC_SCENARIOS["ramen"]
        if any(token in text for token in ["fried", "\u9e7d\u9165\u96de", "\u96de\u6392"]):
            return GENERIC_SCENARIOS["fried"]
        if any(token in text for token in ["\u6ef7\u5473", "\u9ebb\u8fa3\u71d9"]):
            return GENERIC_SCENARIOS["luwei"]
        return None

    def _budget(self, mode: str) -> int:
        return {"quick": 1, "standard": 2, "fine": 4}.get(mode, 2)

    def _quantity_multiplier(self, text: str) -> float:
        lowered = text.lower()
        if any(word in lowered for word in ["double", "\u5169\u4efd", "\u52a0\u500d"]):
            return 2.0
        if any(word in lowered for word in ["half", "\u534a\u4efd", "\u5403\u4e00\u534a"]):
            return 0.6
        return 1.0

    def _has_quantity_cue(self, text: str) -> bool:
        return bool(re.search(r"(\d+|\u534a\u4efd|\u4e00\u4efd|\u5169\u4efd|small|medium|large|regular)", text.lower()))

    def _pick_question(self, missing_slots: list[str], *, strategy: str) -> str:
        if "portion" in missing_slots:
            return "Was it a small, regular, or large portion, or about how much did you finish?"
        if "combo_items" in missing_slots:
            return "Did it include a drink, side, or dessert as part of the order?"
        if "broth_style" in missing_slots:
            return "Was it a clear broth, heavy tonkotsu, chicken paitan, or rich miso style?"
        if "extra_toppings" in missing_slots:
            return "Did you add extra noodles, extra chashu, backfat, butter, or rice?"
        if "main_components" in missing_slots:
            return "What were the main components, for example chicken, skin, tempura, noodles, or tofu skin?"
        return "What is the single detail that would change the estimate the most: portion, toppings, or sauce?"

    def _uncertainty_note(self, strategy: str, missing_slots: list[str]) -> str:
        if not missing_slots:
            return "This estimate is grounded by the local knowledge packet."
        if strategy in {"shop_profile", "broth_rule"}:
            return "The biggest uncertainty is the broth richness and any ramen add-ons."
        if strategy == "component_sum":
            return "The biggest uncertainty is oil, sauce, and how many fried or braised components were included."
        return "The estimate is still sensitive to portion size and missing add-ons."

    def _empty_evidence_slots(self, source_mode: str) -> dict[str, object]:
        return {
            "source_mode": source_mode,
            "identified_items": False,
            "main_items": [],
            "portion_signal": False,
            "high_calorie_modifiers": False,
            "knowledge_strategy": None,
        }
