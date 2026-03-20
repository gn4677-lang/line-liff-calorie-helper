# BuilderSpace Optimization Report

Date: 2026-03-20

## What changed

- Added BuilderSpace tuning settings in `backend/app/config.py` and `.env.example`:
  - `BUILDERSPACE_OCR_MAX_TOKENS`
  - `BUILDERSPACE_TEXT_MAX_TOKENS`
  - `BUILDERSPACE_VISION_MAX_TOKENS`
  - `BUILDERSPACE_HYBRID_TEXT_SHORTCUT`
  - `BUILDERSPACE_RESULT_CACHE_TTL_SECONDS`
  - `BUILDERSPACE_RESULT_CACHE_MAX_ENTRIES`
- Changed `backend/app/providers/factory.py` to reuse singleton provider instances instead of creating a new provider object on every request.
- Reworked `backend/app/providers/builderspace.py`:
  - prompt version bumped to `builderspace-estimation-v3`
  - shared `httpx.AsyncClient` with keep-alive and HTTP/2
  - dynamic completion budgets instead of one fixed `max_tokens=900`
  - compact knowledge packet projection for prompt payloads
  - text-only hybrid shortcut that skips remote LLM calls for high-confidence structured matches
  - route-policy labels written into `evidence_slots`
  - in-memory LRU-style result cache for repeat remote text requests
  - broader fallback to heuristic on BuilderSpace request or parse failure

## Why `max_tokens` mattered

`max_tokens` is the completion budget, not the input size.  
The old setting used one large budget for every estimate call. That was conservative because the app asks for a small JSON object, not a long natural-language answer.

Lowering the completion budget helps by:

- reducing tail latency on remote calls
- reducing token cost
- reducing the chance that the model rambles outside the schema

The new budgets are:

- OCR / visible-text extraction: `220`
- text estimation default: `320`
- image / vision estimation default: `480`
- exact item or archetype text estimate: capped to `260`
- component-sum text estimate: capped to `280`
- clarification text estimate: capped to `220`

## Hybrid routing rule

When `AI_PROVIDER=builderspace`, the app now still uses the local heuristic path for text-only requests when:

- there are no image attachments
- `source_mode` is text
- the knowledge packet already found a strong structured match
- the strategy is one of:
  - `exact_item`
  - `archetype_range`
  - `component_sum`
  - `shop_profile`
  - `broth_rule`

This means BuilderSpace is now reserved for:

- image and video tasks
- vague text with weak or no structured grounding
- cases where the local pack cannot anchor the estimate safely

There is also a stricter text route policy now:

- grounded clarification turns stay local
- very short and ungrounded text stays local because the remote model rarely adds enough value to justify the latency
- links or long grounded descriptions still go remote because they are more likely to require synthesis

## Prompt-size improvement

The provider no longer serializes the full runtime packet into the LLM prompt. It now sends a compact packet with only the fields the model actually needs.

Measured packet shrinkage:

- `Subway roasted chicken breast`: `1513` bytes -> `694` bytes
- `勝王 拉麵 加叉燒`: `1836` bytes -> `1262` bytes
- `鹽酥雞 雞皮 甜不辣`: `2741` bytes -> `1780` bytes

## Expected impact

- Heuristic text paths remain in the `~0.1s - 0.3s` backend range.
- BuilderSpace text paths should improve because:
  - fewer requests reach the remote model
  - the remaining requests send smaller prompts
  - the connection is reused
  - the completion budget is tighter
  - repeat remote text requests can hit the result cache instead of recomputing
- Vision tasks are still slower than text tasks, but they should see lower overhead than before.

## Verification

Validation command:

```powershell
& 'C:\Users\exsaf\AppData\Local\Programs\Python\Python312\python.exe' -m pytest backend\tests\test_knowledge_packets.py backend\tests\test_intake_flow.py backend\tests\test_video_intake.py -q --basetemp backend\.pytest_tmp
```

Result:

- `17 passed`

## Next recommended step

If you want another performance step after this one, the highest-value change is request-result caching for repeated text estimates keyed by:

- normalized text
- source mode
- knowledge packet version
- provider prompt version
