from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import settings
from .base import EstimateResult
from .heuristic import HeuristicProvider


class BuilderSpaceProvider:
    def __init__(self) -> None:
        self._fallback = HeuristicProvider()

    async def transcribe_audio(self, *, content: bytes, mime_type: str | None = None) -> str:
        if not settings.ai_builder_token:
            return await self._fallback.transcribe_audio(content=content, mime_type=mime_type)

        files = {"audio_file": ("voice.m4a", content, mime_type or "audio/m4a")}
        data = {"language": settings.builderspace_transcription_lang}
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{settings.ai_builder_base_url}/audio/transcriptions_long",
                headers={"Authorization": f"Bearer {settings.ai_builder_token}"},
                data=data,
                files=files,
            )
            response.raise_for_status()
            payload = response.json()
            return payload.get("text") or payload.get("transcript") or ""

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
        if not settings.ai_builder_token:
            return await self._fallback.estimate_meal(
                text=text,
                meal_type=meal_type,
                mode=mode,
                source_mode=source_mode,
                clarification_count=clarification_count,
                attachments=attachments,
            )

        content: list[dict[str, Any]] = [{"type": "text", "text": self._prompt(text, meal_type, mode, source_mode)}]
        for item in attachments:
            if item.get("type") == "image" and item.get("content_base64"):
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{item.get('mime_type', 'image/jpeg')};base64,{item['content_base64']}",
                        },
                    }
                )

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.ai_builder_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai_builder_token}"},
                json={
                    "model": settings.builderspace_vision_model if any(item.get("type") == "image" for item in attachments) else settings.builderspace_chat_model,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": "You estimate food calories. Reply with compact JSON only."},
                        {"role": "user", "content": content},
                    ],
                    "max_tokens": 800,
                },
            )
            response.raise_for_status()
            payload = response.json()

        try:
            message = payload["choices"][0]["message"]["content"]
            parsed = json.loads(message)
            return EstimateResult(
                parsed_items=parsed.get("parsed_items", []),
                estimate_kcal=int(parsed.get("estimate_kcal", 0)),
                kcal_low=int(parsed.get("kcal_low", 0)),
                kcal_high=int(parsed.get("kcal_high", 0)),
                confidence=float(parsed.get("confidence", 0.5)),
                missing_slots=parsed.get("missing_slots", []),
                followup_question=parsed.get("followup_question"),
                uncertainty_note=parsed.get("uncertainty_note", ""),
                status=parsed.get("status", "ready_to_confirm"),
            )
        except Exception:
            return await self._fallback.estimate_meal(
                text=text,
                meal_type=meal_type,
                mode=mode,
                source_mode=source_mode,
                clarification_count=clarification_count,
                attachments=attachments,
            )

    def _prompt(self, text: str, meal_type: str | None, mode: str, source_mode: str) -> str:
        return (
            "請把這餐估算成 JSON，欄位只有 parsed_items, estimate_kcal, kcal_low, kcal_high, confidence, "
            "missing_slots, followup_question, uncertainty_note, status。"
            f" meal_type={meal_type or 'unknown'} mode={mode} source_mode={source_mode} "
            f"使用者描述：{text}"
        )
