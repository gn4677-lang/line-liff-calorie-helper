# Knowledge Pack Spec v2

Implementation reference for the local-first nutrition, calorie estimation, and video-grounding layer.

## Goal

Use stable local knowledge before search, and pass only a compact, versioned packet into the meal-estimation model.

The permanent pack is for:

- stable food archetypes
- stable chain menu items
- ramen shop profiles and broth rules
- component-level Taiwan snack and luwei estimates
- visual anchors and brand cards

Search remains a fallback for:

- new or limited menu items
- volatile convenience-store SKUs not retained locally
- explicit source lookups

## Registry

The knowledge system is now indexed by:

- [pack_registry.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/pack_registry.json)

The registry defines:

- pack kind
- pack roles
- priority
- schema
- matching fields
- serving fields
- calorie fields

This replaces the old file-name-only lookup behavior.

## Structured Packs

Core packs:

- [food_catalog_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/food_catalog_tw.json)
- [chain_menu_cards_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/chain_menu_cards_tw.json)
- [convenience_store_archetypes_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/convenience_store_archetypes_tw.json)
- [convenience_store_skus_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/convenience_store_skus_tw.json)
- [drink_chain_maps.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/drink_chain_maps.json)
- [drink_portion_defaults.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/drink_portion_defaults.json)
- [visual_portion_anchors_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/visual_portion_anchors_tw.json)
- [social_dining_templates_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/social_dining_templates_tw.json)
- [taipei_area_order_maps.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/taipei_area_order_maps.json)

New deep-research packs:

- [fried_item_components_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/fried_item_components_tw.json)
- [luwei_components_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/luwei_components_tw.json)
- [ramen_estimation_rules_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/ramen_estimation_rules_tw.json)
- [ramen_shop_profiles_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/ramen_shop_profiles_tw.json)
- [activity_met_values_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/activity_met_values_tw.json)
- [energy_model_rules_tw.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/energy_model_rules_tw.md)

## Retrieval and Grounding

v2 retrieval order:

1. alias normalization
2. registry-aware structured lookup
3. direct brand-card and markdown hits
4. BM25 over local docs
5. targeted search fallback

v2 estimation grounding:

1. build a compact `knowledge_packet`
2. select a primary strategy
3. pass that packet to the provider
4. persist packet version and matched packs in draft metadata

Primary strategies:

- `exact_item`
- `archetype_range`
- `shop_profile`
- `broth_rule`
- `component_sum`
- `generic`

## Packet Design

The estimation packet is built by:

- [knowledge.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/knowledge.py)

The packet contains:

- `version`
- `query`
- `primary_strategy`
- `primary_matches`
- `supporting_matches`
- `matched_packs`
- `brand_hints`
- `visual_anchors`
- `risk_cues`
- `followup_slots`
- `instruction_hints`

The packet is intentionally compact. Raw deep-research markdown is never passed directly to the model.

## Provider Wiring

The provider interface now accepts `knowledge_packet`.

Relevant files:

- [base.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/providers/base.py)
- [heuristic.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/providers/heuristic.py)
- [builderspace.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/providers/builderspace.py)
- [routes.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/api/routes.py)
- [video_intake.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/video_intake.py)

The draft metadata now records:

- `knowledge_packet_version`
- `matched_knowledge_packs`

## Best-Practice Rules

The v2 design follows these operating rules:

- Keep retrieved context structured and small before it reaches the model.
- Separate task instructions from retrieved knowledge.
- Prefer exact local matches over generic guesses.
- Version prompt behavior and version knowledge packets.
- Test the retrieval and packet path directly, not just the final text output.

Reference sources:

- [OpenAI Prompting Guide](https://platform.openai.com/docs/guides/prompting)
- [OpenAI Evaluation Best Practices](https://platform.openai.com/docs/guides/evaluation-best-practices)
- [OpenAI Reasoning Best Practices](https://platform.openai.com/docs/guides/reasoning-best-practices)
- [Anthropic Prompt Engineering Overview](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)
- [Anthropic Long Context Tips](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips)

## Validation

Current packet-focused regression coverage is in:

- [test_confirmation_and_qa.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/tests/test_confirmation_and_qa.py)
- [test_video_intake.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/tests/test_video_intake.py)
- [test_intake_flow.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/tests/test_intake_flow.py)
- [test_knowledge_packets.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/tests/test_knowledge_packets.py)
