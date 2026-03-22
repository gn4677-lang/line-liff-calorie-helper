from __future__ import annotations

import asyncio
from collections import OrderedDict
import copy
import json
import threading
import time
from decimal import Decimal
from typing import Any

import httpx

from ..config import settings
from .base import EstimateResult
from .heuristic import HeuristicProvider


TEXT_ONLY_SOURCE_MODES = {"", "text", None}
SHORTCUT_STRATEGIES = {"exact_item", "archetype_range", "component_sum", "shop_profile", "broth_rule"}


class BuilderSpaceProvider:
    prompt_version = "builderspace-estimation-v4"

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
        memory_packet: dict | None = None,
        communication_profile: dict | None = None,
    ) -> EstimateResult:
        packet = knowledge_packet or {}
        memory = memory_packet or {}
        profile = communication_profile or {}
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
                memory_packet=memory,
                communication_profile=profile,
            )
            return self._annotate_result(result, policy=policy, cache_status="bypassed")

        cache_key = self._cache_key(
            text=text,
            meal_type=meal_type,
            mode=mode,
            source_mode=source_mode,
            clarification_count=clarification_count,
            knowledge_packet=packet,
            memory_packet=memory,
            communication_profile=profile,
            policy=policy,
        )
        if cache_key:
            cached = self._get_cached_result(cache_key)
            if cached is not None:
                return self._annotate_result(cached, policy=policy, cache_status="hit")

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": self._prompt(text, meal_type, mode, source_mode, packet, memory, profile),
            },
            *image_parts,
        ]

        try:
            model_name = settings.builderspace_vision_model if image_parts else settings.builderspace_chat_model
            model_hint = "vision" if image_parts else "chat"
            payload = await self._post_json(
                "/chat/completions",
                timeout=60,
                payload={
                    "model": model_name,
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
            usage = self._usage_metadata_from_payload(payload, model_name=model_name, model_hint=model_hint)
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
            if usage:
                result.evidence_slots = {
                    **result.evidence_slots,
                    "provider_usage": usage,
                }
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
                memory_packet=memory,
                communication_profile=profile,
            )
            return self._annotate_result(result, policy={**policy, "target": "heuristic", "reason": "builderspace_error_fallback"}, cache_status="bypassed")

    def _prompt(
        self,
        text: str,
        meal_type: str | None,
        mode: str,
        source_mode: str,
        knowledge_packet: dict[str, Any] | None,
        memory_packet: dict[str, Any] | None = None,
        communication_profile: dict[str, Any] | None = None,
    ) -> str:
        packet = json.dumps(
            self._compact_packet_for_prompt(knowledge_packet),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        memory = json.dumps(
            self._compact_memory_packet_for_prompt(memory_packet),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        profile = json.dumps(
            self._compact_communication_profile(communication_profile),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return "\n".join(
            [
                "Task: estimate calories for one meal and return JSON only.",
                "Rules:",
                "- Use the knowledge packet as the first source of truth.",
                "- Use the memory packet to personalize assumptions, but not to overwrite grounded evidence.",
                "- Use the communication profile when phrasing one follow-up question.",
                "- Prefer exact local matches over generic assumptions.",
                "- Keep the answer compact and deterministic.",
                "- Ask at most one follow-up question for the single biggest uncertainty.",
                "- Never invent exact brand nutrition facts that are not in the packet.",
                "Output schema:",
                '{"parsed_items":[{"name":"string","kcal":0}],"estimate_kcal":0,"kcal_low":0,"kcal_high":0,"confidence":0.0,"missing_slots":[],"followup_question":null,"uncertainty_note":"","status":"ready_to_confirm","evidence_slots":{},"comparison_candidates":[],"ambiguity_flags":[]}',
                f"meal_type={meal_type or 'unknown'} mode={mode} source_mode={source_mode}",
                f"user_text={text}",
                f"knowledge_packet={packet}",
                f"memory_packet={memory}",
                f"communication_profile={profile}",
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

    def _compact_memory_packet_for_prompt(self, memory_packet: dict[str, Any] | None) -> dict[str, Any]:
        packet = memory_packet or {}
        compact = {
            "user_stated_constraints": {
                "breakfast_habit": ((packet.get("user_stated_constraints") or packet.get("preferences") or {}).get("breakfast_habit")),
                "carb_need": ((packet.get("user_stated_constraints") or packet.get("preferences") or {}).get("carb_need")),
                "dinner_style": ((packet.get("user_stated_constraints") or packet.get("preferences") or {}).get("dinner_style")),
                "hard_dislikes": list(((packet.get("user_stated_constraints") or packet.get("preferences") or {}).get("hard_dislikes", [])))[:4],
            },
            "relevant_signals": [
                {
                    "dimension": item.get("dimension"),
                    "canonical_label": item.get("canonical_label"),
                    "confidence": item.get("confidence"),
                    "status": item.get("status"),
                }
                for item in packet.get("relevant_signals", [])[:6]
                if isinstance(item, dict)
            ],
            "active_hypotheses": [
                {
                    "dimension": item.get("dimension"),
                    "label": item.get("label"),
                    "confidence": item.get("confidence"),
                    "status": item.get("status"),
                }
                for item in packet.get("active_hypotheses", [])[:6]
                if isinstance(item, dict)
            ],
            "recent_evidence": [
                {
                    "meal_type": item.get("meal_type"),
                    "parsed_items": [entry.get("name") for entry in item.get("parsed_items", [])[:3] if isinstance(entry, dict) and entry.get("name")],
                    "event_at": item.get("event_at"),
                }
                for item in packet.get("recent_evidence", [])[:3]
                if isinstance(item, dict)
            ],
            "recent_acceptance": [
                {
                    "meal_type": item.get("meal_type"),
                    "description": item.get("description"),
                    "kcal_estimate": item.get("kcal_estimate"),
                    "store_name": item.get("store_name"),
                }
                for item in packet.get("recent_acceptance", [])[:4]
                if isinstance(item, dict)
            ],
            "reporting_bias": {
                key: value
                for key, value in (packet.get("reporting_bias") or {}).items()
                if key in {"underreport_score", "overreport_score", "vagueness_score", "missing_detail_score", "log_confidence_score"}
            },
            "recommendation_profile": {
                key: value
                for key, value in (packet.get("recommendation_profile") or {}).items()
                if key in {"repeat_tolerance", "nearby_exploration_preference", "favorite_bias_strength", "distance_sensitivity"}
            },
            "store_context_memory": [
                {
                    "food_name": item.get("food_name"),
                    "top_store_name": item.get("top_store_name"),
                    "top_avg_kcal": item.get("top_avg_kcal"),
                    "top_portion_ratio": item.get("top_portion_ratio"),
                }
                for item in packet.get("store_context_memory", [])[:4]
                if isinstance(item, dict)
            ],
            "recent_log_count": packet.get("recent_log_count"),
            "recent_average_kcal": packet.get("recent_average_kcal"),
        }
        compact["user_stated_constraints"] = {
            key: value for key, value in compact["user_stated_constraints"].items() if value not in (None, "", [])
        }
        return {key: value for key, value in compact.items() if value not in (None, "", [], {}, False)}

    def _compact_communication_profile(self, communication_profile: dict[str, Any] | None) -> dict[str, Any]:
        profile = communication_profile or {}
        compact = {
            key: value
            for key, value in profile.items()
            if key in {"directness", "detail_level", "confirmation_style", "planning_proactivity", "comparison_answer_style"} and value not in (None, "")
        }
        return compact

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
        memory_packet: dict[str, Any] | None,
        communication_profile: dict[str, Any] | None,
        policy: dict[str, Any],
    ) -> str | None:
        if not policy.get("cacheable"):
            return None
        compact_packet = self._compact_packet_for_prompt(knowledge_packet)
        compact_memory = self._compact_memory_packet_for_prompt(memory_packet)
        compact_profile = self._compact_communication_profile(communication_profile)
        key_payload = {
            "prompt_version": self.prompt_version,
            "text": text.strip(),
            "meal_type": meal_type or "",
            "mode": mode,
            "source_mode": source_mode or "",
            "clarification_count": clarification_count,
            "packet": compact_packet,
            "memory": compact_memory,
            "communication_profile": compact_profile,
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
        body = response.json()
        if isinstance(body, dict):
            body["_transport_meta"] = self._transport_meta(response=response, timeout=timeout)
        return body

    async def complete_structured(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        max_tokens: int = 220,
        temperature: float = 0.1,
        model_hint: str = "chat",
        request_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not settings.ai_builder_token:
            return {}
        model_name = settings.builderspace_chat_model
        if model_hint == "frontier":
            model_name = settings.builderspace_frontier_model
        elif model_hint == "router":
            model_name = settings.builderspace_router_model
        elif model_hint == "vision":
            model_name = settings.builderspace_vision_model
        effective_temperature = temperature
        effective_max_tokens = max_tokens
        extra_options = copy.deepcopy(request_options) if isinstance(request_options, dict) else {}
        if model_name == "gpt-5":
            effective_temperature = 1.0
            effective_max_tokens = max(effective_max_tokens, 1000)
            extra_options.setdefault("max_completion_tokens", effective_max_tokens)
        payload_body: dict[str, Any] = {
            "model": model_name,
            "temperature": effective_temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "max_tokens": effective_max_tokens,
        }
        if extra_options:
            payload_body.update(extra_options)
        payload = await self._post_json(
            "/chat/completions",
            timeout=45,
            payload=payload_body,
        )
        parsed = self._parse_json_object(payload)
        usage = self._usage_metadata_from_payload(payload, model_name=model_name, model_hint=model_hint)
        if usage:
            parsed["_provider_usage"] = usage
        parsed["_provider_model_name"] = model_name
        parsed["_provider_model_hint"] = model_hint
        return parsed

    def _transport_meta(self, *, response: httpx.Response, timeout: float) -> dict[str, Any]:
        headers = response.headers
        return {
            "http_status": response.status_code,
            "timeout_s": timeout,
            "rate_limit_remaining_requests": self._coerce_int(
                headers.get("x-ratelimit-remaining-requests") or headers.get("x-ratelimit-remaining-req")
            ),
            "rate_limit_remaining_tokens": self._coerce_int(
                headers.get("x-ratelimit-remaining-tokens") or headers.get("x-ratelimit-remaining-token")
            ),
            "rate_limit_reset_requests_s": self._coerce_int(
                headers.get("x-ratelimit-reset-requests") or headers.get("x-ratelimit-reset-req")
            ),
            "rate_limit_reset_tokens_s": self._coerce_int(
                headers.get("x-ratelimit-reset-tokens") or headers.get("x-ratelimit-reset-token")
            ),
        }

    def _usage_metadata_from_payload(
        self,
        payload: dict[str, Any],
        *,
        model_name: str,
        model_hint: str,
    ) -> dict[str, Any]:
        usage = payload.get("usage") if isinstance(payload, dict) else None
        usage_payload = usage if isinstance(usage, dict) else {}
        prompt_tokens = self._coerce_int(
            usage_payload.get("prompt_tokens")
            or usage_payload.get("input_tokens")
            or usage_payload.get("prompt_token_count")
        )
        completion_tokens = self._coerce_int(
            usage_payload.get("completion_tokens")
            or usage_payload.get("output_tokens")
            or usage_payload.get("completion_token_count")
        )
        total_tokens = self._coerce_int(usage_payload.get("total_tokens"))
        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        pricing = self._pricing_for_model_hint(model_hint)
        estimated_cost_usd = None
        if prompt_tokens is not None or completion_tokens is not None:
            prompt_cost = Decimal(str(pricing["input_cost_per_1k_usd"])) * Decimal(prompt_tokens or 0) / Decimal(1000)
            completion_cost = Decimal(str(pricing["output_cost_per_1k_usd"])) * Decimal(completion_tokens or 0) / Decimal(1000)
            estimated_cost_usd = float(prompt_cost + completion_cost)

        transport_meta = payload.get("_transport_meta") if isinstance(payload, dict) else {}
        if not isinstance(transport_meta, dict):
            transport_meta = {}
        usage_meta = {
            "provider_name": "builderspace",
            "model_name": model_name,
            "model_hint": model_hint,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "request_count": 1,
            "token_budget_per_hour": settings.builderspace_token_budget_per_hour or None,
            "request_budget_per_hour": settings.builderspace_request_budget_per_hour or None,
            "cost_budget_usd_per_day": settings.builderspace_cost_budget_usd_per_day or None,
            "rate_limit_remaining_requests": transport_meta.get("rate_limit_remaining_requests"),
            "rate_limit_remaining_tokens": transport_meta.get("rate_limit_remaining_tokens"),
            "rate_limit_reset_requests_s": transport_meta.get("rate_limit_reset_requests_s"),
            "rate_limit_reset_tokens_s": transport_meta.get("rate_limit_reset_tokens_s"),
        }
        if all(
            usage_meta.get(key) in {None, 0, 0.0}
            for key in ("prompt_tokens", "completion_tokens", "total_tokens", "estimated_cost_usd")
        ):
            if usage_meta.get("rate_limit_remaining_requests") is None and usage_meta.get("rate_limit_remaining_tokens") is None:
                return {}
        return usage_meta

    def _pricing_for_model_hint(self, model_hint: str) -> dict[str, float]:
        normalized = (model_hint or "chat").strip().lower()
        if normalized == "frontier":
            return {
                "input_cost_per_1k_usd": settings.builderspace_frontier_input_cost_per_1k_usd,
                "output_cost_per_1k_usd": settings.builderspace_frontier_output_cost_per_1k_usd,
            }
        if normalized == "vision":
            return {
                "input_cost_per_1k_usd": settings.builderspace_vision_input_cost_per_1k_usd,
                "output_cost_per_1k_usd": settings.builderspace_vision_output_cost_per_1k_usd,
            }
        if normalized == "router":
            return {
                "input_cost_per_1k_usd": settings.builderspace_router_input_cost_per_1k_usd,
                "output_cost_per_1k_usd": settings.builderspace_router_output_cost_per_1k_usd,
            }
        return {
            "input_cost_per_1k_usd": settings.builderspace_chat_input_cost_per_1k_usd,
            "output_cost_per_1k_usd": settings.builderspace_chat_output_cost_per_1k_usd,
        }

    def _coerce_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return None

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
