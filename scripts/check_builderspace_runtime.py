from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
from typing import Any

sys.path.insert(0, ".")

from backend.app.config import settings
from backend.app.providers.factory import get_ai_provider


DEFAULT_ESTIMATE_TEXT = "今天中午吃烤雞便當，白飯半碗，雞腿一隻，青菜兩樣，滷蛋一顆。"


def _estimate_kwargs(text: str) -> dict[str, Any]:
    return {
        "text": text,
        "meal_type": "lunch",
        "mode": "standard",
        "source_mode": "text",
        "clarification_count": 0,
        "attachments": [],
        "knowledge_packet": {"version": "runtime_check", "matched_packs": []},
        "memory_packet": {},
        "communication_profile": {},
    }


def _runtime_header(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "ai_provider": settings.ai_provider,
        "has_builder_token": bool(settings.ai_builder_token),
        "base_url": settings.ai_builder_base_url,
        "mode": args.mode,
        "hint": args.hint,
        "text": args.text,
        "builderspace_router_model": settings.builderspace_router_model,
        "builderspace_chat_model": settings.builderspace_chat_model,
        "builderspace_frontier_model": settings.builderspace_frontier_model,
    }


async def _run_structured(provider: Any, *, hint: str) -> dict[str, Any]:
    return await provider.complete_structured(
        system_prompt='Reply with compact JSON only as {"pong": true}.',
        user_payload={"ping": "builder"},
        max_tokens=32,
        temperature=0.0,
        model_hint=hint,
    )


async def _run_estimate(provider: Any, *, text: str) -> dict[str, Any]:
    estimate = await provider.estimate_meal(**_estimate_kwargs(text))
    return dataclasses.asdict(estimate)


async def _run_raw_estimate(provider: Any, *, text: str) -> dict[str, Any]:
    packet = {"version": "runtime_check", "matched_packs": []}
    payload = await provider._post_json(  # type: ignore[attr-defined]
        "/chat/completions",
        timeout=60,
        payload={
            "model": settings.builderspace_chat_model,
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
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": provider._prompt(  # type: ignore[attr-defined]
                                text,
                                "lunch",
                                "standard",
                                "text",
                                packet,
                                {},
                                {},
                            ),
                        }
                    ],
                },
            ],
            "max_tokens": provider._estimate_max_tokens(  # type: ignore[attr-defined]
                mode="standard",
                source_mode="text",
                attachments=[],
                knowledge_packet=packet,
            ),
        },
    )
    return {
        "raw_message": payload.get("choices", [{}])[0].get("message", {}).get("content"),
        "usage": payload.get("usage"),
        "transport_meta": payload.get("_transport_meta"),
    }


async def _run_production_safe_probe(provider: Any, *, text: str) -> tuple[bool, dict[str, Any]]:
    report: dict[str, Any] = {
        "probe_kind": "production_safe",
        "notes": [
            "Router health uses complete_structured(..., model_hint='router').",
            "Main chat health uses estimate_meal(text) with a stable sample that is known to route to the remote BuilderSpace text path.",
            "A generic tiny JSON ping is not treated as authoritative health for supermind-agent-v1.",
        ],
    }
    errors: list[dict[str, Any]] = []

    try:
        router_result = await _run_structured(provider, hint="router")
        report["router_check"] = {
            "ok": bool(router_result.get("pong") is True),
            "result": router_result,
                "expected_model": settings.builderspace_router_model,
        }
    except Exception as exc:  # pragma: no cover - exercised by live probe
        errors.append(
            {
                "phase": "router",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )

    try:
        estimate_result = await _run_estimate(provider, text=text)
        evidence_slots = estimate_result.get("evidence_slots") or {}
        provider_usage = evidence_slots.get("provider_usage") if isinstance(evidence_slots, dict) else {}
        route_target = evidence_slots.get("route_target") if isinstance(evidence_slots, dict) else None
        route_reason = evidence_slots.get("route_reason") if isinstance(evidence_slots, dict) else None
        report["estimate_path_sample"] = {
            "ok": bool(route_target == "builderspace" and route_reason != "builderspace_error_fallback"),
            "route_target": route_target,
            "route_reason": route_reason,
            "status": estimate_result.get("status"),
            "estimate_kcal": estimate_result.get("estimate_kcal"),
            "confidence": estimate_result.get("confidence"),
            "provider_usage": provider_usage,
        }
    except Exception as exc:  # pragma: no cover - exercised by live probe
        errors.append(
            {
                "phase": "estimate",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )

    if errors:
        report["errors"] = errors

    router_ok = bool((report.get("router_check") or {}).get("ok"))
    estimate_path_ok = bool((report.get("estimate_path_sample") or {}).get("ok"))
    ok = router_ok and estimate_path_ok and not errors
    report["ok"] = ok
    report["summary"] = {
        "router_ok": router_ok,
        "estimate_path_sample_ok": estimate_path_ok,
        "error_count": len(errors),
    }
    return ok, report


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hint", default="chat")
    parser.add_argument(
        "--mode",
        choices=["probe", "structured", "estimate", "raw_estimate"],
        default="probe",
    )
    parser.add_argument("--text", default=DEFAULT_ESTIMATE_TEXT)
    args = parser.parse_args()

    print(json.dumps(_runtime_header(args), ensure_ascii=False))

    provider = get_ai_provider()
    try:
        if args.mode == "probe":
            ok, result = await _run_production_safe_probe(provider, text=args.text)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if ok else 1
        if args.mode == "raw_estimate":
            result = await _run_raw_estimate(provider, text=args.text)
        elif args.mode == "estimate":
            result = await _run_estimate(provider, text=args.text)
        else:
            result = await _run_structured(provider, hint=args.hint)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
