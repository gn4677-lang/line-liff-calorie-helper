from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class EstimateResult:
    parsed_items: list[dict]
    estimate_kcal: int
    kcal_low: int
    kcal_high: int
    confidence: float
    missing_slots: list[str] = field(default_factory=list)
    followup_question: str | None = None
    uncertainty_note: str = ""
    status: str = "ready_to_confirm"


class AiProvider(Protocol):
    async def estimate_meal(
        self,
        *,
        text: str,
        meal_type: str | None,
        mode: str,
        source_mode: str,
        clarification_count: int,
        attachments: list[dict],
    ) -> EstimateResult: ...

    async def transcribe_audio(self, *, content: bytes, mime_type: str | None = None) -> str: ...
