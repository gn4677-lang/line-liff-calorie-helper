# Memory Schema Spec

Engineering reference for the L1/L2/L3 memory system, cold-start onboarding, correction flow, and retrieval packets.

Related implementation specs:

- [conversation-confirmation-tech-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/conversation-confirmation-tech-spec.md)
- [knowledge-pack-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/knowledge-pack-spec.md)
- [proactivity-tech-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/proactivity-tech-spec.md)

This document is more concrete than [memory-onboarding-v2.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/memory-onboarding-v2.md). Use it when changing database fields, writing consolidation jobs, or extending memory-aware prompts.

## Design Goals

- keep L1 factual and traceable
- keep L2 countable and decaying
- keep L3 sparse, useful, and reversible
- make user correction higher-trust than inference
- support cold start without pretending to know the user
- keep prompt packets small and structured

## Source Priority

Memory source priority is fixed and should not be relaxed:

1. `user_corrected`
2. `user_stated`
3. `behavior_inferred`
4. `model_hypothesis`

This priority applies to:
- updating preferences
- signal promotion
- hypothesis conflict resolution
- explainability wording

## Layer Ownership

### L1

Fact storage only.

Primary tables:
- `meal_drafts`
- `meal_logs`
- `weight_logs`
- `plan_events`

Allowed content:
- raw meal evidence
- estimate outputs
- clarification trace
- event and context metadata

Not allowed:
- generalized preference claims
- personality conclusions

### L2

Repeatable pattern storage.

Primary table:
- `memory_signals`

Allowed content:
- repeated food usage
- cuisine repetition
- taste cues
- timing signals
- meal structure signals
- onboarding-seeded preference signals

Not allowed:
- narrative summaries
- user-facing personality copy

### L3

Sparse hypothesis storage.

Primary table:
- `memory_hypotheses`

Allowed content:
- stable or tentative conclusions that help recommendation, planning, or question intensity

Not allowed:
- broad personality labels
- unsupported single-event generalizations

## L1 Schema

### `meal_drafts`

Purpose:
- hold in-progress meal interpretation before confirmation

Core fields:
- `id`
- `user_id`
- `meal_session_id`
- `date`
- `event_at`
- `meal_type`
- `status`
- `raw_input_text`
- `source_mode`
- `mode`
- `attachments`
- `parsed_items`
- `missing_slots`
- `followup_question`
- `draft_context`
- `estimate_kcal`
- `kcal_low`
- `kcal_high`
- `confidence`
- `uncertainty_note`
- `clarification_count`
- `created_at`
- `updated_at`

### `meal_logs`

Purpose:
- hold confirmed meal records and their traceable estimation context

Core fields:
- `id`
- `user_id`
- `meal_session_id`
- `date`
- `event_at`
- `meal_type`
- `description_raw`
- `kcal_estimate`
- `kcal_low`
- `kcal_high`
- `confidence`
- `source_mode`
- `confirmed`
- `parsed_items`
- `uncertainty_note`
- `metadata`
- `created_at`
- `updated_at`

### L1 JSON Metadata

Use JSON for high-variance observations that do not justify repeated migrations.

Expected keys:
- `event_context`
- `location_context`
- `portion_cues`
- `leftover_ratio`
- `shared_meal`
- `share_ratio`
- `people_count`
- `group_dish_flag`
- `taste_cues`
- `cuisine_candidates`
- `uncertainty_factors`
- `clarification_questions`
- `clarification_answers`
- `force_confirmed`
- `edited_after_confirm`

## L2 Schema

### `memory_signals`

Purpose:
- store reusable, countable, decaying evidence

Fields:
- `id`
- `user_id`
- `pattern_type`
- `dimension`
- `canonical_label`
- `raw_labels`
- `value`
- `source`
- `confidence`
- `evidence_count`
- `counter_evidence_count`
- `evidence_score`
- `counter_evidence_score`
- `first_seen_at`
- `last_seen_at`
- `sample_log_ids`
- `status`
- `metadata`

Unique key:
- `(user_id, pattern_type, canonical_label)`

### Field Semantics

- `pattern_type`
  - operational bucket, such as `food_repeat`, `hard_dislike`, `onboarding_preference`
- `dimension`
  - broader semantic dimension, such as `meal_timing`, `meal_structure`, `cuisine_preference`
- `canonical_label`
  - normalized key used for grouping and synthesis
- `raw_labels`
  - original tokens seen from user input or inference
- `value`
  - a display or payload value associated with the signal
- `evidence_score`
  - recency-weighted support score
- `counter_evidence_score`
  - recency-weighted contradiction score
- `status`
  - current lifecycle state

### L2 Status Lifecycle

- `candidate`
  - has some evidence but not enough to be considered stable
- `stable`
  - strong enough to use confidently in retrieval
- `decaying`
  - contradictions or time decay are overtaking support
- `stale`
  - optional terminal state for future cleanup jobs

Recommended logic:
- `stable` when net score is clearly positive and recent
- `candidate` when evidence exists but is not yet robust
- `decaying` when counter-evidence overtakes support

## L3 Schema

### `memory_hypotheses`

Purpose:
- store sparse high-level conclusions derived from L2 or explicit user input

Fields:
- `id`
- `user_id`
- `dimension`
- `label`
- `statement`
- `source`
- `confidence`
- `supporting_signal_ids`
- `evidence_count`
- `counter_evidence_count`
- `last_confirmed_at`
- `status`
- `metadata`

Unique key:
- `(user_id, label)`

### L3 Status Lifecycle

- `tentative`
  - useful enough to try in retrieval or explainability, but not fully trusted
- `active`
  - stable enough to actively influence recommendation and planning
- `stale`
  - contradicted, aged out, or replaced by stronger user input

## Canonicalization

Canonicalization happens before L2 is promoted into L3.

### Phase 1: Deterministic Alias Mapping

Use fixed alias maps for obvious merges:
- `日式`, `日料`, `日本料理` -> `japanese`
- `超商`, `便利商店` -> `convenience_store`
- `韓式`, `韓國料理` -> `korean`

### Phase 2: LLM-Assisted Merge

Only for unresolved labels.

Rules:
- first try to map to an existing canonical label
- only produce a candidate when no safe mapping exists
- candidate labels stay in L2 until enough evidence exists

## Cold Start Onboarding Mapping

Onboarding writes structured `user_stated` values to `preferences`, then seeds corresponding L2 signals.

### Questions and Storage

1. Breakfast habit
   - field: `preferences.breakfast_habit`
   - seed signal: `breakfast_habit:<value>`

2. Carb need
   - field: `preferences.carb_need`
   - seed signal: `carb_need:<value>`

3. Dinner style
   - field: `preferences.dinner_style`
   - seed signal: `dinner_style:<value>`

4. Hard dislikes
   - field: `preferences.hard_dislikes`
   - seed signal per dislike, for example `korean`

5. Compensation preference
   - field: `preferences.compensation_style`
   - seed signal: `compensation_style:<value>`

### Onboarding User State

User table fields:
- `onboarding_completed_at`
- `onboarding_skipped_at`
- `onboarding_version`

## Correction Rules

Correction can come from:
- LIFF settings edits
- direct correction endpoint
- chat-driven phrase detection

### Required Behavior

- correction updates `preferences`
- correction seeds or updates higher-priority signals
- conflicting L3 hypotheses gain counter-evidence or become `stale`
- subsequent retrieval must use corrected values immediately

### Example

If the system holds `rarely_eats_breakfast` and the user says:
- “我最近開始吃早餐了”

Then:
- `preferences.breakfast_habit = regular`
- supporting breakfast signal becomes `user_corrected`
- `rarely_eats_breakfast` becomes `stale`

## Promotion and Demotion Rules

### L2 -> L3 Promotion

Promote only when:
- evidence spans multiple days
- recency-weighted score is strong enough
- counter-evidence is not dominant
- the result is useful for recommendation or planning

### Triggered Tentative Promotion

Do not wait only for a weekly job.

Allow early `tentative` hypotheses when:
- a signal’s evidence score spikes in a short window
- a repeated pattern becomes obvious over 2-3 days

### Demotion

Demote when:
- explicit user correction conflicts with the hypothesis
- counter-evidence accumulates
- support becomes old and decays away

## Retrieval Packets

### `intake_packet`

Use for:
- meal understanding
- clarification decisions

Contains:
- current meal session id
- user-stated constraints
- a small set of relevant signals
- a few recent evidence examples
- reporting bias summary

### `recommendation_packet`

Use for:
- current recommendation generation
- explainability

Contains:
- meal type
- remaining kcal
- explicit preferences
- active hypotheses
- top relevant signals

### `planning_packet`

Use for:
- daily planning
- compensation suggestions

Contains:
- explicit preferences
- recent log count
- recent average kcal
- active hypotheses

### `synthesis_packet`

Use for:
- periodic L2 -> L3 synthesis

Contains:
- canonicalized signals
- representative recent L1 evidence
- current hypotheses
- counter-evidence summary

## Explainability Contract

User-facing explainability should use `reason_factors`.

Do:
- surface readable reasons
- hint at relevant behavior gently
- create opportunities for correction

Do not:
- expose raw labels like `rarely_eats_breakfast`
- expose internal scores
- imply certainty when evidence is tentative

## Reporting Bias as Meta-Memory

`reporting_bias` stays outside L2/L3 tables, but retrieval should treat it as a meta-memory object.

Effects:
- increase clarification intensity when vagueness is high
- reduce confidence in over-precise calorie conclusions
- bias recommendation and planning toward safer assumptions

## Indexing and Performance Notes

Recommended index emphasis:
- `users.line_user_id`
- `meal_drafts.user_id`
- `meal_drafts.meal_session_id`
- `meal_logs.user_id`
- `meal_logs.event_at`
- `memory_signals.user_id + pattern_type + canonical_label`
- `memory_hypotheses.user_id + label`

Prompt packet builders should always:
- cap counts
- order by confidence and recency
- avoid sending full raw history

## Current Implementation References

Database models:
- [models.py](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/models.py)

Runtime schema sync:
- [schema_sync.py](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/schema_sync.py)

Memory service:
- [memory.py](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/memory.py)

API routes:
- [routes.py](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/api/routes.py)

Frontend handoff:
- [antigravity-frontend-handoff.md](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/antigravity-frontend-handoff.md)
