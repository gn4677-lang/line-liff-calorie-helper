import asyncio

import pytest

from app.config import settings
from app.providers.builderspace import BuilderSpaceProvider
from app.services.knowledge import KNOWLEDGE_PACKET_VERSION, build_estimation_knowledge_packet, list_knowledge_packs

pytestmark = pytest.mark.agentic


def test_pack_registry_lists_new_structured_packs():
    packs = {item["pack_id"] for item in list_knowledge_packs()}
    assert "fried_item_components_tw" in packs
    assert "luwei_components_tw" in packs
    assert "ramen_estimation_rules_tw" in packs
    assert "ramen_shop_profiles_tw" in packs


def test_estimation_packet_uses_ramen_shop_profile():
    packet = build_estimation_knowledge_packet("\u52dd\u738b \u62c9\u9eb5 \u52a0\u53c9\u71d2")
    assert packet["version"] == KNOWLEDGE_PACKET_VERSION
    assert packet["primary_strategy"] == "shop_profile"
    assert packet["primary_matches"][0]["name"] == "\u52dd\u738b"
    assert "ramen_shop_profiles_tw" in packet["matched_packs"]


def test_estimation_packet_component_sum_for_fried_combo():
    packet = build_estimation_knowledge_packet("\u9e7d\u9165\u96de \u96de\u76ae \u751c\u4e0d\u8fa3")
    assert packet["primary_strategy"] == "component_sum"
    assert "\u96de\u76ae" in [item["name"] for item in packet["primary_matches"]]
    assert "fried_item_components_tw" in packet["matched_packs"]


def test_estimation_packet_component_sum_for_luwei_combo():
    packet = build_estimation_knowledge_packet("\u738b\u5b50\u9eb5 \u8c46\u76ae \u9d28\u8840")
    assert packet["primary_strategy"] == "component_sum"
    names = [item["name"] for item in packet["primary_matches"]]
    assert "\u738b\u5b50\u9eb5" in names
    assert "\u9d28\u8840" in names
    assert "luwei_components_tw" in packet["matched_packs"]


def test_builderspace_prompt_includes_compact_knowledge_packet():
    provider = BuilderSpaceProvider()
    packet = build_estimation_knowledge_packet("Subway roasted chicken breast")
    prompt = provider._prompt("Subway roasted chicken breast", "lunch", "standard", "text", packet)
    assert "knowledge_packet=" in prompt
    assert "Subway 6-inch Roasted Chicken Breast" in prompt
    assert "source_path" not in prompt


def test_builderspace_route_policy_shortcuts_structured_text(monkeypatch):
    provider = BuilderSpaceProvider()
    packet = build_estimation_knowledge_packet("\u52dd\u738b \u62c9\u9eb5 \u52a0\u53c9\u71d2")
    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)

    policy = provider._route_policy(
        text="\u52dd\u738b \u62c9\u9eb5 \u52a0\u53c9\u71d2",
        mode="standard",
        source_mode="text",
        attachments=[],
        knowledge_packet=packet,
    )

    assert policy["target"] == "heuristic"
    assert policy["label"] == "heuristic_grounded_text"


def test_builderspace_route_policy_keeps_media_tasks_on_llm_path(monkeypatch):
    provider = BuilderSpaceProvider()
    packet = build_estimation_knowledge_packet("Subway roasted chicken breast", source_mode="image")
    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)

    policy = provider._route_policy(
        text="Subway roasted chicken breast",
        mode="standard",
        source_mode="image",
        attachments=[{"type": "image", "content_base64": "abc", "mime_type": "image/jpeg"}],
        knowledge_packet=packet,
    )

    assert policy["target"] == "builderspace"
    assert policy["label"] in {"builderspace_vision", "builderspace_media"}


def test_builderspace_shortcuts_structured_text_requests(monkeypatch):
    provider = BuilderSpaceProvider()
    packet = build_estimation_knowledge_packet("\u52dd\u738b \u62c9\u9eb5 \u52a0\u53c9\u71d2")

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("builderspace request should have been skipped")

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(provider, "_post_json", fail_if_called)

    result = asyncio.run(
        provider.estimate_meal(
            text="\u52dd\u738b \u62c9\u9eb5 \u52a0\u53c9\u71d2",
            meal_type="dinner",
            mode="standard",
            source_mode="text",
            clarification_count=0,
            attachments=[],
            knowledge_packet=packet,
        )
    )

    assert result.estimate_kcal > 0
    assert result.knowledge_packet_version == KNOWLEDGE_PACKET_VERSION
    assert "ramen_shop_profiles_tw" in result.matched_knowledge_packs
    assert result.evidence_slots["route_policy"] == "heuristic_grounded_text"
    assert result.evidence_slots["llm_cache"] == "bypassed"


def test_builderspace_caches_remote_text_results(monkeypatch):
    provider = BuilderSpaceProvider()
    packet = build_estimation_knowledge_packet("mystery lunch set")
    calls = {"count": 0}

    async def fake_post_json(*args, **kwargs):
        calls["count"] += 1
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"parsed_items":[{"name":"mystery lunch set","kcal":640}],'
                            '"estimate_kcal":640,"kcal_low":560,"kcal_high":760,'
                            '"confidence":0.61,"missing_slots":[],"followup_question":null,'
                            '"uncertainty_note":"","status":"ready_to_confirm",'
                            '"evidence_slots":{},"comparison_candidates":[],"ambiguity_flags":[]}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(settings, "ai_builder_token", "test-token", raising=False)
    monkeypatch.setattr(settings, "builderspace_hybrid_text_shortcut", True, raising=False)
    monkeypatch.setattr(settings, "builderspace_result_cache_ttl_seconds", 600, raising=False)
    monkeypatch.setattr(provider, "_post_json", fake_post_json)

    first = asyncio.run(
        provider.estimate_meal(
            text="mystery lunch set",
            meal_type="lunch",
            mode="standard",
            source_mode="text",
            clarification_count=0,
            attachments=[],
            knowledge_packet=packet,
        )
    )
    second = asyncio.run(
        provider.estimate_meal(
            text="mystery lunch set",
            meal_type="lunch",
            mode="standard",
            source_mode="text",
            clarification_count=0,
            attachments=[],
            knowledge_packet=packet,
        )
    )

    assert calls["count"] == 1
    assert first.evidence_slots["llm_cache"] == "miss"
    assert second.evidence_slots["llm_cache"] == "hit"
    assert second.estimate_kcal == 640


def test_builderspace_uses_smaller_text_token_budget():
    provider = BuilderSpaceProvider()
    exact_packet = build_estimation_knowledge_packet("Subway roasted chicken breast")
    component_packet = build_estimation_knowledge_packet("\u9e7d\u9165\u96de \u96de\u76ae \u751c\u4e0d\u8fa3")

    assert provider._estimate_max_tokens(
        mode="standard",
        source_mode="text",
        attachments=[],
        knowledge_packet=exact_packet,
    ) == min(settings.builderspace_text_max_tokens, 260)
    assert provider._estimate_max_tokens(
        mode="standard",
        source_mode="text",
        attachments=[],
        knowledge_packet=component_packet,
    ) == min(settings.builderspace_text_max_tokens, 280)
    assert provider._estimate_max_tokens(
        mode="standard",
        source_mode="image",
        attachments=[{"type": "image", "content_base64": "abc", "mime_type": "image/jpeg"}],
        knowledge_packet=exact_packet,
    ) == max(settings.builderspace_vision_max_tokens, 320)


def test_intake_draft_metadata_records_knowledge_packet(client):
    response = client.post(
        "/api/intake",
        json={
            "text": "\u52dd\u738b \u62c9\u9eb5 \u52a0\u53c9\u71d2",
            "mode": "standard",
            "meal_type": "dinner",
        },
    )
    assert response.status_code == 200
    draft = response.json()["draft"]
    assert draft["metadata"]["knowledge_packet_version"] == KNOWLEDGE_PACKET_VERSION
    assert "ramen_shop_profiles_tw" in draft["metadata"]["matched_knowledge_packs"]
