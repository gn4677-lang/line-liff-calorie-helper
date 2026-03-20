from __future__ import annotations

import asyncio
from collections import OrderedDict
import copy
import json
import threading
import time
from typing import Any

import httpx

from ..config import settings
from .base import EstimateResult
from .heuristic import HeuristicProvider


TEXT_ONLY_SOURCE_MODES = {"", "text", None}
SHORTCUT_STRATEGIES = {"exact_item", "archetype_range", "component_sum", "shop_profile", "broth_rule"}


class BuilderSpaceProvider:
    prompt_version = "builderspace-estimation-v3"

    def __init__(self) -> None:
        self._fallback = HeuristicProvider()
        self._clients: dict[tuple[int, int], httpx.AsyncClient] = {}
        self._result_cache: OrderedDict[str, tuple[float, EstimateResult]] = OrderedDict()
        self._cache_lock = threading.Lock()

    async def extract_visible_text(
        self,
        *,
        attachments: list[dict],
        hint: str = "",
    ) -> list[dict]:
        if not settings.ai_builder_token:
            return []

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "Read visible food, menu, package, and brand text from the attached images. "
                    "Return compact JSON only as an array of objects with keys: text, kind, confidence. "
                    "kind should be one of brand, menu_item, package, menu_board, other. "
                    "Only include legible, food-relevant text. "
                    f"Hint: {hint}"
                ),
            },
            *self._image_parts(attachments),
        ]

        payload = await self._post_json(
            "/chat/completions",
            timeout=45,
            payload={
                "model": settings.builderspace_vision_model,
                "temperature": 0.0,
                "messages": [
                    {"role": "system", "content": "You extract visible food-related text. Reply with compact JSON only."},
                    {"role": "user", "content": content},
                ],
                "max_tokens": settings.builderspace_ocr_max_tokens,
            },
        )
        return self._parse_json_list(payload)

    async def transcribe_audio(self, *, content: bytes, mime_type: str | None = None) -> str:
        if not settings.ai_builder_token:
            return await self._fallback.transcribe_audio(content=content, mime_type=mime_type)

        files = {"audio_file": ("voice.m4a", content, mime_type or "audio/m4a")}
        data = {"language": settings.builderspace_transcription_lang}
        payload = await self._post_json(
            "/audio/transcriptions_long",
            timeout=45,
            data=data,
            files=files,
        )
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
        knowledge_packet: dict | None = None,
    ) -> EstimateResult:
        packet = knowledge_packet or {}
        image_parts = self._image_parts(attachments)
        policy = self._route_policy(
            text=text,
            mode=mode,
            source_mode=source_mode,
            attachments=attachments,
            knowledge_packet=packet,
        )
        if policy["target"] == "heuristic":
            result = await self._fallback.estimate_meal(
                text=text,
                meal_type=meal_type,
                mode=mode,
                source_mode=source_mode,
                clarification_count=clarification_count,
                attachments=attachments,
                knowledge_packet=packet,
            )
            return self._annotate_result(result, policy=policy, cache_status="bypassed")

        cache_key = self._cache_key(
            text=text,
            meal_type=meal_type,
            mode=mode,
            source_mode=source_mode,
            clarification_count=clarification_count,
            knowledge_packet=packet,
            policy=policy,
        )
        if cache_key:
            cached = self._get_cached_result(cache_key)
            if cached is not None:
                return self._annotate_result(cached, policy=policy, cache_status="hit")

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": self._prompt(text, meal_type, mode, source_mode, packet),
            },
            *image_parts,
        ]

        try:
            payload = await self._post_json(
                "/chat/completions",
                timeout=60,
                payload={
                    "model": settings.builderspace_vision_model if image_parts else settings.builderspace_chat_model,
                    "temperature": 0.1,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You estimate food calories for Taiwan meals. "
                                "Use the knowledge packet as grounded context. "
                                "Prefer exact local matches over generic assumptions. "
                                "Reply with compact JSON only."
                            ),
                        },
                        {"role": "user", "content": content},
                    ],
                    "max_tokens": self._estimate_max_tokens(
                        mode=mode,
                        source_mode=source_mode,
                        attachments=attachments,
                        knowledge_packet=packet,
                    ),
                },
            )
            parsed = self._parse_json_object(payload)
            result = EstimateResult(
                parsed_items=parsed.get("parsed_items", []),
                estimate_kcal=int(parsed.get("estimate_kcal", 0)),
                kcal_low=int(parsed.get("kcal_low", 0)),
                kcal_high=int(parsed.get("kcal_high", 0)),
                confidence=float(parsed.get("confidence", 0.5)),
                missing_slots=parsed.get("missing_slots", []),
                followup_question=parsed.get("followup_question"),
                uncertainty_note=parsed.get("uncertainty_note", ""),
                status=parsed.get("status", "ready_to_confirm"),
                evidence_slots=parsed.get("evidence_slots", {}),
                comparison_candidates=parsed.get("comparison_candidates", []),
                ambiguity_flags=parsed.get("ambiguity_flags", []),
                knowledge_packet_version=packet.get("version"),
                matched_knowledge_packs=packet.get("matched_packs", []),
            )
            if cache_key:
                self._store_cached_result(cache_key, result)
            return self._annotate_result(result, policy=policy, cache_status="miss")
        except Exception:
            result = await self._fallback.estimate_meal(
                text=text,
                meal_type=meal_type,
                mode=mode,
                source_mode=source_mode,
                clarification_count=clarification_count,
                attachments=attachments,
                knowledge_packet=packet,
            )
            return self._annotate_result(result, policy={**policy, "target": "heuristic", "reason": "builderspace_error_fallback"}, cache_status="bypassed")

    def _prompt(
        self,
        text: str,
        meal_type: str | None,
        mode: str,
        source_mode: str,
        knowledge_packet: dict[str, Any] | None,
    ) -> str:
        packet = json.dumps(
            self._compact_packet_for_prompt(knowledge_packet),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return "\n".join(
            [
                "Task: estimate calories for one meal and return JSON only.",
                "Rules:",
                "- Use the knowledge packet as the first source of truth.",
                "- Prefer exact local matches over generic assumptions.",
                "- Keep the answer compact and deterministic.",
                "- Ask at most one follow-up question for the single biggest uncertainty.",
                "- Never invent exact brand nutrition facts that are not in the packet.",
                "Output schema:",
                '{"parsed_items":[{"name":"string","kcal":0}],"estimate_kcal":0,"kcal_low":0,"kcal_high":0,"confidence":0.0,"missing_slots":[],"followup_question":null,"uncertainty_note":"","status":"ready_to_confirm","evidence_slots":{},"comparison_candidates":[],"ambiguity_flags":[]}',
                f"meal_type={meal_type or 'unknown'} mode={mode} source_mode={source_mode}",
                f"user_text={text}",
                f"knowledge_packet={packet}",
            ]
        )

    def _compact_packet_for_prompt(self, knowledge_packet: dict[str, Any] | None) -> dict[str, Any]:
        packet = knowledge_packet or {}
        compact = {
            "version": packet.get("version"),
            "primary_strategy": packet.get("primary_strategy"),
            "matched_packs": list(packet.get("matched_packs", []))[:6],
            "primary_matches": [self._compact_match(item) for item in packet.get("primary_matches", [])[:4]],
            "supporting_matches": [self._compact_match(item) for item in packet.get("supporting_matches", [])[:2]],
            "instruction_hints": list(packet.get("instruction_hints", []))[:3],
            "followup_slots": list(packet.get("followup_slots", []))[:4],
            "risk_cues": list(packet.get("risk_cues", []))[:6],
            "brand_hints": list(packet.get("brand_hints", []))[:3],
            "packaging_cues": list(packet.get("packaging_cues", []))[:4],
            "likely_convenience_store": bool(packet.get("likely_convenience_store")),
            "visual_anchors": [
                {
                    "name": item.get("display_name") or item.get("name") or item.get("anchor_id"),
                    "anchor_id": item.get("anchor_id"),
                }
                for item in packet.get("visual_anchors", [])[:2]
                if item.get("display_name") or item.get("name") or item.get("anchor_id")
            ],
        }
        return {key: value for key, value in compact.items() if value not in (None, "", [], False)}

    def _compact_match(self, item: dict[str, Any]) -> dict[str, Any]:
        compact = {
            "name": item.get("name"),
            "pack_id": item.get("pack_id"),
            "chain_id": item.get("chain_id"),
            "kcal_low": item.get("kcal_low"),
            "kcal_high": item.get("kcal_high"),
            "serving": item.get("serving"),
            "notes": str(item.get("notes", "")).strip()[:160],
            "risk_flags": list(item.get("risk_flags", []))[:4],
        }
        return {key: value for key, value in compact.items() if value not in (None, "", [])}

    def _estimate_max_tokens(
        self,
        *,
        mode: str,
        source_mode: str,
        attachments: list[dict],
        knowledge_packet: dict[str, Any] | None,
    ) -> int:
        if self._image_parts(attachments) or source_mode in {"image", "single-photo", "before-after-photo", "video"}:
            return max(settings.builderspace_vision_max_tokens, 320)

        strategy = (knowledge_packet or {}).get("primary_strategy")
        if mode == "clarification":
            return min(settings.builderspace_text_max_tokens, 220)
        if strategy in {"exact_item", "archetype_range"}:
            return min(settings.builderspace_text_max_tokens, 260)
        if strategy == "component_sum":
            return min(settings.builderspace_text_max_tokens, 280)
        return settings.builderspace_text_max_tokens

    def _route_policy(
        self,
        *,
        text: str,
        mode: str,
        source_mode: str | None,
        attachments: list[dict],
        knowledge_packet: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not settings.ai_builder_token:
            return {"target": "heuristic", "label": "heuristic_no_token", "reason": "builder_token_missing", "cacheable": False}
        if self._image_parts(attachments):
            return {"target": "builderspace", "label": "builderspace_vision", "reason": "image_attachment_present", "cacheable": False}
        if source_mode in {"image", "single-photo", "before-after-photo", "video"}:
            return {"target": "builderspace", "label": "builderspace_media", "reason": "media_source_mode", "cacheable": False}
        if source_mode not in TEXT_ONLY_SOURCE_MODES:
            return {"target": "builderspace", "label": "builderspace_non_text", "reason": "non_text_source_mode", "cacheable": False}

        packet = knowledge_packet or {}
        normalized = text.strip().lower()
        strategy = packet.get("primary_strategy")
        has_primary = bool(packet.get("primary_matches"))
        if mode == "clarification" and has_primary:
            return {"target": "heuristic", "label": "heuristic_clarification", "reason": "grounded_clarification", "cacheable": False}
        if not settings.builderspace_hybrid_text_shortcut:
            return {"target": "builderspace", "label": "builderspace_text", "reason": "hybrid_shortcut_disabled", "cacheable": True}
        if "http://" in normalized or "https://" in normalized:
            return {"target": "builderspace", "label": "builderspace_text", "reason": "contains_url", "cacheable": True}
        if has_primary and strategy in SHORTCUT_STRATEGIES:
            if strategy in {"exact_item", "archetype_range"} and len(normalized) > 160:
                return {"target": "builderspace", "label": "builderspace_text", "reason": "long_grounded_text", "cacheable": True}
            if strategy in {"component_sum", "shop_profile", "broth_rule"} and len(normalized) > 220:
                return {"target": "builderspace", "label": "builderspace_text", "reason": "complex_grounded_text", "cacheable": True}
            return {"target": "heuristic", "label": "heuristic_grounded_text", "reason": f"structured_{strategy}", "cacheable": False}
        if len(normalized) <= 24 and not has_primary:
            return {"target": "heuristic", "label": "heuristic_short_text", "reason": "too_vague_for_remote_gain", "cacheable": False}
        return {"target": "builderspace", "label": "builderspace_text", "reason": "ungrounded_text", "cacheable": True}

    def _annotate_result(self, result: EstimateResult, *, policy: dict[str, Any], cache_status: str) -> EstimateResult:
        annotated = copy.deepcopy(result)
        annotated.evidence_slots = {
            **annotated.evidence_slots,
            "route_target": policy.get("target"),
            "route_policy": policy.get("label"),
            "route_reason": policy.get("reason"),
            "llm_cache": cache_status,
        }
        return annotated

    def _cache_key(
        self,
        *,
        text: str,
        meal_type: str | None,
        mode: str,
        source_mode: str | None,
        clarification_count: int,
        knowledge_packet: dict[str, Any] | None,
        policy: dict[str, Any],
    ) -> str | None:
        if not policy.get("cacheable"):
            return None
        compact_packet = self._compact_packet_for_prompt(knowledge_packet)
        key_payload = {
            "prompt_version": self.prompt_version,
            "text": text.strip(),
            "meal_type": meal_type or "",
            "mode": mode,
            "source_mode": source_mode or "",
            "clarification_count": clarification_count,
            "packet": compact_packet,
        }
        return json.dumps(key_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _get_cached_result(self, cache_key: str) -> EstimateResult | None:
        now = time.monotonic()
        with self._cache_lock:
            entry = self._result_cache.get(cache_key)
            if entry is None:
                return None
            expires_at, result = entry
            if expires_at <= now:
                self._result_cache.pop(cache_key, None)
                return None
            self._result_cache.move_to_end(cache_key)
            return copy.deepcopy(result)

    def _store_cached_result(self, cache_key: str, result: EstimateResult) -> None:
        expires_at = time.monotonic() + max(settings.builderspace_result_cache_ttl_seconds, 1)
        with self._cache_lock:
            self._result_cache[cache_key] = (expires_at, copy.deepcopy(result))
            self._result_cache.move_to_end(cache_key)
            while len(self._result_cache) > settings.builderspace_result_cache_max_entries:
                self._result_cache.popitem(last=False)

    def _image_parts(self, attachments: list[dict]) -> list[dict[str, Any]]:
        return [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{item.get('mime_type', 'image/jpeg')};base64,{item['content_base64']}",
                },
            }
            for item in attachments
            if item.get("type") == "image" and item.get("content_base64")
        ]

    def _get_client(self) -> httpx.AsyncClient:
        key = (threading.get_ident(), id(asyncio.get_running_loop()))
        client = self._clients.get(key)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                http2=True,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0),
            )
            self._clients[key] = client
        return client

    async def _post_json(
        self,
        path: str,
        *,
        timeout: float,
        payload: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._get_client().post(
            f"{settings.ai_builder_base_url}{path}",
            headers={"Authorization": f"Bearer {settings.ai_builder_token}"},
            timeout=timeout,
            json=payload,
            data=data,
            files=files,
        )
        response.raise_for_status()
        return response.json()

    def _parse_json_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = payload["choices"][0]["message"]["content"]
        if isinstance(message, list):
            text = "".join(part.get("text", "") for part in message if isinstance(part, dict))
        else:
            text = str(message)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("Expected a JSON object.")
        return parsed

    def _parse_json_list(self, payload: dict[str, Any]) -> list[dict]:
        try:
            message = payload["choices"][0]["message"]["content"]
            text = str(message).strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
        except Exception:
            return []
        return []
