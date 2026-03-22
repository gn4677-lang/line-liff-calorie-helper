# BuilderSpace OpenAPI Reference (2026-03-22)

Source of this note:
- user-provided OpenAPI snapshot in chat on 2026-03-22
- canonical URL mentioned inside the snapshot:
  - `https://www.ai-builders.com/resources/students-backend/openapi.json`

This file is intentionally a focused reference, not a frozen full raw copy.
The goal is to preserve the parts that materially affect the agentic runtime.

## Relevant Endpoint

- Base server URL: `/backend`
- Chat completions endpoint:
  - `POST /v1/chat/completions`

Effective app-facing path when routed through BuilderSpace:
- `/backend/v1/chat/completions`

## Chat Request Contract Notes

The `ChatCompletionRequest` schema is OpenAI-compatible and has:
- `model`
- `messages`
- `temperature`
- `max_tokens`
- `top_p`
- `stream`
- `tools`
- `tool_choice`
- `user`
- `metadata`

Important detail:
- `additionalProperties: true`

That means BuilderSpace may accept extra request fields beyond the basic OpenAI schema.
This matters for agentic runtime options like:
- `response_format`
- `reasoning_effort`
- provider-specific passthrough fields

## gpt-5-Specific Constraints

The snapshot explicitly states:
- `gpt-5` only supports `temperature=1.0` and BuilderSpace will enforce that
- `gpt-5` uses `max_completion_tokens` instead of `max_tokens`
- BuilderSpace will automatically convert `max_tokens` to `max_completion_tokens`
- recommended: `max_tokens >= 1000` for complete `gpt-5` responses

Implication for this repo:
- do not assume a low-token JSON classification request is stable on `gpt-5`
- if using `gpt-5` for structured output, prefer:
  - `temperature=1.0`
  - `response_format={"type":"json_object"}` when appropriate
  - a sufficiently large completion budget

## Response Notes

The `ChatCompletionResponse` is OpenAI-compatible and includes:
- `id`
- `created`
- `model`
- `choices`
- `usage`
- optional `system_fingerprint`
- optional `orchestrator_trace`

`orchestrator_trace` can be included when:
- query param `debug=true`

This is relevant for future observability/debugging if we need deeper BuilderSpace-side traces.

## Model Notes Mentioned in Snapshot

- `deepseek`
  - described as fast and cost-effective
- `supermind-agent-v1`
  - multi-tool agent with search/handoff behavior
- `gpt-5`
  - passthrough to OpenAI-compatible providers
- `grok-4-fast`
  - passthrough to X.AI
- `gemini-*`
  - direct or preview Gemini variants
- `kimi-k2.5`
  - multimodal, also constrained to `temperature=1.0`

## Why This Matters For Agentic Rewrite

This snapshot directly informed the BuilderSpace request-shape fix in:
- [builderspace.py](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/providers/builderspace.py)
- [llm_support.py](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/llm_support.py)

Specifically:
- `request_options` must actually propagate to the remote call
- `gpt-5` request shape should respect BuilderSpace constraints
- low completion budgets can cause brittle structured-output behavior

## Operational Guidance

When debugging BuilderSpace issues in this repo, check in this order:
1. Was the route actually using BuilderSpace?
2. Did `request_options` reach the provider?
3. Was the model `gpt-5` or another model?
4. Did the request respect `gpt-5` constraints?
5. Did the response include `usage` / `finish_reason` / trace metadata?

If a future issue appears, refresh this note against the canonical OpenAPI URL instead of assuming the 2026-03-22 snapshot is still current.
