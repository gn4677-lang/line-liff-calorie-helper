# Knowledge System Upgrade Report

Date: 2026-03-20

## Scope

This pass did four things together:

1. distilled the new deep-research notes from `fry.md` and `ramen.md`
2. reorganized the permanent knowledge packs behind a registry
3. rewired the estimation path so the model consumes a compact `knowledge_packet`
4. added regression coverage for ramen, fried snacks, luwei, QA, intake, and video grounding

## Deep-Research Distillation

### fry.md

Stable findings that were promoted into permanent knowledge:

- Taiwan fried-snack and luwei estimates should be component-first, not bundle-average-first.
- The biggest variance drivers are oil absorption, coating thickness, sauce, and unknown portion size.
- Fried vegetables and tofu products are common underestimation traps.
- Luwei should separate low-risk leafy items from high-impact items like instant noodles, tofu skin, blood cake, and offal.
- When details are missing, the system should widen ranges first and only ask about the one detail that changes the estimate most.

These findings became:

- [fried_item_components_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/fried_item_components_tw.json)
- [luwei_components_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/luwei_components_tw.json)

### ramen.md

Stable findings that were promoted into permanent knowledge:

- Clear broth, chicken paitan, tonkotsu, heavy miso, and tsukemen need different calorie baselines.
- Ramen estimation must separate noodles, broth richness, aroma oil, protein toppings, and extras.
- Extra noodles, extra chashu, backfat, butter, and rice materially move the total.
- Shop-level profiles are useful when a user mentions stable Taiwan ramen shops or award-shop names directly.

These findings became:

- [ramen_estimation_rules_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/ramen_estimation_rules_tw.json)
- [ramen_shop_profiles_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/ramen_shop_profiles_tw.json)

## What Changed

### 1. Registry-based pack indexing

I added [pack_registry.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/pack_registry.json).

This is now the source of truth for:

- which packs exist
- what role each pack plays
- how each pack should be matched
- which fields contain calories, aliases, serving basis, and notes

This replaces the old file-name-only logic.

### 2. Unified local retrieval and grounding

I rewrote [knowledge.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/knowledge.py) so that QA, suggested updates, and video grounding all use the same registry-aware structured lookup.

Key behavior:

- local QA still prefers structured matches first
- brand cards and markdown docs still backstop structured lookup
- video grounding now exposes ramen, fried-snack, and luwei packs in addition to chain and convenience-store packs
- convenience-store and chain matches now respect brand hints more carefully

### 3. Compact knowledge packet for estimation

The main estimation path now builds a compact packet before calling the provider.

The packet contains:

- `primary_strategy`
- `primary_matches`
- `supporting_matches`
- `matched_packs`
- `risk_cues`
- `followup_slots`
- `instruction_hints`

Important strategies:

- `exact_item`
- `archetype_range`
- `shop_profile`
- `broth_rule`
- `component_sum`

This was wired through:

- [base.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/providers/base.py)
- [builderspace.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/providers/builderspace.py)
- [heuristic.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/providers/heuristic.py)
- [routes.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/api/routes.py)
- [video_intake.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/video_intake.py)
- [intake.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/intake.py)

### 4. Metadata and versioning

Draft metadata now stores:

- `knowledge_packet_version`
- `matched_knowledge_packs`

Task runs also now record:

- `prompt_version`
- `knowledge_packet_version`

That makes it possible to compare prompt or packet changes against downstream quality later.

## Best-Practice Alignment

The design changes follow a few consistent rules from official LLM guidance:

- Keep retrieved context structured and bounded rather than dumping raw research.
  Sources:
  [OpenAI Prompting Guide](https://platform.openai.com/docs/guides/prompting),
  [Anthropic Long Context Tips](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips)
- Separate instructions from retrieved knowledge.
  Sources:
  [OpenAI Prompting Guide](https://platform.openai.com/docs/guides/prompting),
  [Anthropic Prompt Engineering Overview](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)
- Use structured outputs and stable schemas so provider behavior is testable.
  Sources:
  [OpenAI Prompting Guide](https://platform.openai.com/docs/guides/prompting),
  [OpenAI Reasoning Best Practices](https://platform.openai.com/docs/guides/reasoning-best-practices)
- Version prompt behavior and evaluate changes directly.
  Sources:
  [OpenAI Evaluation Best Practices](https://platform.openai.com/docs/guides/evaluation-best-practices)

## Validation

Packet-focused and flow-focused tests passed with a repo-local pytest temp directory:

```powershell
python -m pytest backend/tests/test_confirmation_and_qa.py backend/tests/test_video_intake.py backend/tests/test_knowledge_packets.py backend/tests/test_intake_flow.py -q --basetemp backend/.pytest_tmp
```

Result:

- `20 passed`

I also attempted the entire `backend/tests` suite. That run was blocked by a Windows file-lock issue in pytest temp cleanup, not by a knowledge-packet assertion failure. The lock is on `backend/.pytest_tmp/.../test.db`, so this is an infra/test-isolation problem rather than a pack-index problem.

## Remaining Gaps

The system is materially better, but not literally complete:

- convenience-store exact SKU coverage is still intentionally narrow
- second-wave ramen shop coverage still needs more shops if you want broader city coverage
- more fried and luwei variants can still be added
- some non-knowledge parts of the app still contain older mojibake text and routing strings outside the new packet path
- the full backend suite still needs a stable Windows-safe temp-db cleanup strategy

## Practical Outcome

The app can now do these things much more cleanly than before:

- estimate ramen with broth-aware logic instead of one generic bowl heuristic
- estimate fried-snack and luwei orders by component sum
- pass local knowledge into the estimator instead of only using it for QA
- keep pack behavior inspectable and versioned
- test the knowledge path directly
