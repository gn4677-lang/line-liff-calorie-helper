from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


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
    evidence_slots: dict[str, object] = field(default_factory=dict)
    comparison_candidates: list[str] = field(default_factory=list)
    ambiguity_flags: list[str] = field(default_factory=list)
    knowledge_packet_version: str | None = None
    matched_knowledge_packs: list[str] = field(default_factory=list)


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
        knowledge_packet: dict | None = None,
        memory_packet: dict | None = None,
        communication_profile: dict | None = None,
    ) -> EstimateResult: ...

    async def transcribe_audio(self, *, content: bytes, mime_type: str | None = None) -> str: ...

    async def extract_visible_text(
        self,
        *,
        attachments: list[dict],
        hint: str = "",
    ) -> list[dict]: ...

    async def complete_structured(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        max_tokens: int = 220,
        temperature: float = 0.1,
        model_hint: str = "chat",
        request_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
