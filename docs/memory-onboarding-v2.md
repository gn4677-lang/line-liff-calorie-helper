# L1/L2/L3 Memory System + Cold Start Onboarding v2

This document is the implementation-facing report for the memory architecture, onboarding flow, correction flow, retrieval strategy, and explainability model.

Companion implementation specs:

- [conversation-confirmation-tech-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/conversation-confirmation-tech-spec.md)
- [knowledge-pack-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/knowledge-pack-spec.md)
- [proactivity-tech-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/proactivity-tech-spec.md)

## Goal

The system should not try to sound profound. It should try to:

- work from cold start
- learn only when evidence exists
- be easy to correct
- avoid wasting context and model budget

Source priority is fixed:

`user_corrected > user_stated > behavior_inferred > model_hypothesis`

## Layer Model

### L1 Fact Layer

Purpose:
- keep traceable records
- preserve evidence for later consolidation
- support meal estimation, clarification, and review

Stored in:
- `meal_logs`
- `meal_drafts`
- `weight_logs`
- `plan_events`

Design:
- keep the schema minimal
- promote only high-value fields to first-class columns
- store extra observations in JSON metadata

Core L1 fields:
- `meal_session_id`
- `event_at`
- `logged_at`
- `meal_type`
- `source_mode`
- `kcal_estimate`
- `kcal_low`
- `kcal_high`
- `confidence`
- `status`

L1 metadata examples:
- `event_context`
- `location_context`
- `portion_cues`
- `leftover_ratio`
- `shared_meal`
- `taste_cues`
- `cuisine_candidates`
- `uncertainty_factors`
- `clarification_questions`
- `clarification_answers`
- `force_confirmed`
- `edited_after_confirm`

### L2 Signal Layer

Purpose:
- represent repeatable, countable, and decaying patterns
- keep memory grounded in evidence rather than narrative summaries

Stored in:
- `memory_signals`

Key behavior:
- time-weighted evidence
- canonicalized labels
- candidate / stable / decaying / stale lifecycle
- counter-evidence tracking

Examples:
- repeated foods
- cuisine patterns
- taste patterns
- meal timing patterns
- meal structure patterns
- onboarding-seeded explicit preferences

### L3 Hypothesis Layer

Purpose:
- hold higher-level user hypotheses that are useful for recommendation and planning
- stay mostly internal while still enabling soft explainability

Stored in:
- `memory_hypotheses`

Key behavior:
- weekly synthesis
- threshold-triggered tentative updates
- stronger thresholds for negative preference claims
- immediate downgrade when the user explicitly corrects the system

Examples:
- `rarely_eats_breakfast`
- `needs_carbs`
- `prefers_salty_food`
- `dislikes_korean`

## Reporting Bias

`reporting_bias` remains a separate table.

Reason:
- it is meta-memory about logging quality, not food preference itself

Usage:
- intake clarification intensity
- recommendation trust calibration
- planning confidence

## Cold Start Onboarding

Entry:
- first LIFF launch after successful auth

Behavior:
- single page
- 5 questions
- skippable
- answers stored as `user_stated`
- values immediately affect recommendation and planning

Questions:
1. breakfast habit
2. carb need
3. dinner style
4. hard dislikes
5. compensation preference

Question 5 wording should stay situational:
- return to normal
- gentle recovery for 1 day
- spread over 2-3 days
- let the system decide

## Correction

Primary path:
- chat corrections

Secondary path:
- LIFF settings edits

Correction is the highest-trust memory source and must immediately override weaker inferred memory.

Examples:
- “I actually eat breakfast now.”
- “Don’t recommend Korean food.”
- “I do need carbs.”

## Retrieval Strategy

Use structured retrieval first.

Do not send entire history to the model.

Task-specific packets:
- `intake_packet`
- `recommendation_packet`
- `planning_packet`
- `synthesis_packet`

Each packet should be small and bounded.

Examples:
- intake packet: relevant signals, a few similar logs, reporting bias
- recommendation packet: active hypotheses, relevant signals, meal constraints
- planning packet: recent aggregate behavior, compensation style, active hypotheses
- synthesis packet: canonicalized L2 snapshot plus small representative evidence

## Prompt Design

Use task-specific prompts instead of one giant prompt.

LLM should handle:
- ambiguous food understanding
- minimum clarification question generation
- semantic normalization
- L2 to L3 synthesis
- soft recommendation and planning rationale

Deterministic logic should handle:
- scoring
- filtering
- counting
- decay
- thresholds
- source precedence

Prompt guardrails:
- map to existing labels before inventing new candidates
- avoid personality commentary
- do not generalize from one-off social events
- return `no_change` when evidence is weak

## Explainability

Do not show raw L3 labels by default.

Use `reason_factors` for soft, readable explanations such as:
- “晚餐你通常比較接受高蛋白選項。”
- “最近早餐紀錄偏少，所以這次不會優先推早餐型選項。”
- “這次先避開你明確排斥的類型：韓式。”

Explainability should help the user build trust and trigger correction when needed, without turning the UI into a personality report.

## Frontend Requirements

Frontend should support:
- cold-start onboarding
- skippable setup
- preference correction
- explainability surfaces
- mobile-first LIFF interactions

Antigravity should read this together with:
- [antigravity-frontend-handoff.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/antigravity-frontend-handoff.md)
- [antigravity-prompt.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/antigravity-prompt.md)
- [memory-schema-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/memory-schema-spec.md)
- [product-spec-v1.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/product-spec-v1.md)
