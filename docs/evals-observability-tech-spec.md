# Evals And Observability Tech Spec v2

Implementation reference for how to measure answer quality, capture uncertainty, record deterministic system errors, and log user dissatisfaction so the app can improve task by task.

## Summary

Yes, this app should use **task-based evals**, not one generic quality score.

Also yes: **deterministic system errors must be logged too**, and they must not be mixed with LLM-quality failures.

The right structure is:

- **task-level evals**
  - routing
  - intake parsing
  - clarification
  - confirmation
  - correction
  - nearby recommendation
  - suggested update
  - nutrition QA
  - planning / compensation
  - proactive nudges
- **runtime observability**
  - every important run leaves a trace
  - every uncertainty leaves a reason
  - every fallback is visible
  - every deterministic error is visible
  - every user complaint can be tied back to the exact response
- **reviewable unknown cases**
  - unknown food
  - unknown brand
  - unknown menu item
  - answer-not-found
  - ambiguous user request
  - dissatisfaction / off-target answer

The goal is not just to know whether the model is "good".
The goal is to know:

- which task is weak
- why it failed
- whether the failure came from retrieval, reasoning, routing, grounding, deterministic code, integration, or UX
- what data needs to be added to the knowledge pack
- what system errors need engineering fixes instead of prompt changes

## External Best-Practice Principles

These are the external principles this spec follows:

- **log both application errors and security-relevant events**
  - OWASP recommends recording application errors, input validation failures, authentication issues, connectivity problems, and backend failures.
  - Source: [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- **use structured logging**
  - OpenTelemetry and major cloud observability stacks assume machine-readable logs, not loose strings.
  - Sources: [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/), [Google Cloud observability guidance](https://cloud.google.com/stackdriver/docs/instrumentation/choose-approach)
- **correlate logs, traces, and requests**
  - Every request / job / notification should be traceable through a shared trace id or correlation id.
  - Sources: [OpenTelemetry trace-log correlation](https://opentelemetry.io/docs/specs/otel/logs/), [Azure monitoring and alerting strategy](https://learn.microsoft.com/en-us/azure/well-architected/reliability/monitoring-alerting-strategy)
- **handled failures should still be logged**
  - A fallback is still an event worth recording.
- **separate operational telemetry from product-quality telemetry**
  - "The system broke" and "the answer was bad" are different classes of failure.
- **do not log secrets or unnecessary sensitive data**
  - Source: [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

## Design Principles

### 1. Measure by task, not by vibe

`meal logging quality` and `nutrition QA quality` are different problems.
They need different metrics and different review queues.

### 2. Keep traceability

Every important answer should be traceable to:

- input
- task route
- model / provider used
- confidence / uncertainty
- local knowledge hits
- search fallback
- deterministic integrations involved
- final user outcome

### 3. Log uncertainty explicitly

If the system does not know, or only roughly knows, that should be logged as structured metadata instead of disappearing into free text.

### 4. User correction is a gold signal

If the user says:

- `答非所問`
- `不是這個意思`
- `不是這個熱量`
- `我不是要問這個`

that is stronger than offline eval.

### 5. Unknown cases should become backlog

Unknown food / brand / menu / packaging patterns should become structured review items so you can feed them back into:

- local knowledge pack
- routing rules
- clarification rules
- model prompts

### 6. Deterministic errors need their own lane

These are not "LLM errors".

Examples:

- LINE content fetch failed
- Supabase upload failed
- ffmpeg failed
- tesseract missing or failed
- Google Places timeout
- background job retry exhausted
- DB write failed

These should go into **operational error tracking**, not quality-event tracking.

## Evaluation Layers

### Layer A: Offline task evals

Use labeled datasets and rerun them against prompts / heuristics / routing logic.

This is for:

- regression detection
- prompt changes
- provider / model swaps
- knowledge pack upgrades

### Layer B: Online runtime telemetry

This is production instrumentation.

It answers:

- what actually happened in user traffic
- what the system did
- where uncertainty and fallbacks happened
- which deterministic integrations failed
- what the user accepted / corrected / rejected

### Layer C: Human review queues

This is where you look at:

- high-impact misses
- dissatisfied users
- unknown foods
- repeated clarification failures
- suggested updates that users keep dismissing
- operational errors that keep degrading the experience

## Telemetry Lanes

Split observability into three lanes.

### Lane 1: Product / quality telemetry

Use for:

- routing quality
- answer quality
- knowledge misses
- clarification quality
- recommendation usefulness

### Lane 2: Operational / deterministic telemetry

Use for:

- API failures
- network failures
- storage failures
- OCR / ffmpeg / parsing failures
- job retries and retry exhaustion
- timeouts
- fallback activation

### Lane 3: User feedback telemetry

Use for:

- explicit dissatisfaction
- implicit dissatisfaction
- suggestion apply / dismiss
- correction after answer
- abandonment after clarification

## Task Taxonomy

Use the same task family across evals and telemetry.

### Task families

- `task_router`
- `meal_log_now`
- `meal_log_correction`
- `clarification`
- `confirmation`
- `future_event_probe`
- `weekly_drift_probe`
- `remaining_or_recommendation`
- `nearby_recommendation`
- `nutrition_or_food_qa`
- `preference_or_memory_correction`
- `planning`
- `compensation`
- `suggested_update_review`
- `fallback_ambiguous`

## What To Record

## 1. Conversation Trace

One trace per user-visible turn or system-initiated event.

Suggested table:

- `conversation_traces`

Suggested fields:

- `id`
- `user_id`
- `line_user_id`
- `surface`
  - `chat`
  - `today`
  - `recommendation`
  - `progress`
- `thread_id`
- `message_id`
- `reply_to_trace_id`
- `is_system_initiated`
- `task_family`
- `task_confidence`
- `source_mode`
  - `text`
  - `image`
  - `audio`
  - `video`
  - `liff_action`
- `input_text`
- `input_metadata`
- `created_at`

Purpose:

- trace the raw user interaction timeline
- connect later dissatisfaction to the exact turn

## 2. Task Run

One row per internal task execution.

Suggested table:

- `task_runs`

Suggested fields:

- `id`
- `trace_id`
- `task_family`
- `route_layer_1`
- `route_layer_2`
- `provider_name`
- `model_name`
- `prompt_version`
- `knowledge_packet_version`
- `started_at`
- `completed_at`
- `latency_ms`
- `status`
  - `success`
  - `partial`
  - `fallback`
  - `failed`
- `error_type`
- `fallback_reason`
- `result_summary`

Purpose:

- separate routing and internal execution from user-visible turns
- track what actually ran

## 3. Uncertainty And Confidence Log

This is mandatory for meal logging and recommendation-style tasks.

Suggested table:

- `uncertainty_events`

Suggested fields:

- `id`
- `trace_id`
- `task_run_id`
- `task_family`
- `estimation_confidence`
- `confirmation_calibration`
- `primary_uncertainties`
- `missing_slots`
- `ambiguity_flags`
- `answer_mode`
- `clarification_budget`
- `clarification_used`
- `stop_reason`
- `used_generic_portion_estimate`
- `used_comparison_mode`
- `created_at`

Purpose:

- know not just that the answer was weak, but exactly why

This is especially important for:

- budget exhausted
- generic estimate fallback
- image-only or video-only ambiguity
- unresolved portion / sharing / leftovers

## 4. Knowledge And Retrieval Log

Suggested table:

- `knowledge_events`

Suggested fields:

- `id`
- `trace_id`
- `task_run_id`
- `question_or_query`
- `knowledge_mode`
  - `local_structured`
  - `local_bm25`
  - `brand_card`
  - `places_cache`
  - `web_search_fallback`
- `matched_items`
- `matched_docs`
- `used_search`
- `search_sources`
- `grounding_type`
  - `catalog`
  - `chain_menu_card`
  - `convenience_store_sku`
  - `convenience_store_archetype`
  - `visual_anchor`
  - `none`
- `knowledge_gap_type`
  - nullable
- `created_at`

Purpose:

- show why an answer existed
- show when local knowledge failed
- show what needs research

## 5. Operational Error Log

Suggested table:

- `error_events`

Suggested fields:

- `id`
- `trace_id`
- `task_run_id`
- `component`
  - `line_api`
  - `supabase_storage`
  - `postgres`
  - `google_places`
  - `ffmpeg`
  - `tesseract`
  - `ocr`
  - `video_pipeline`
  - `background_worker`
  - `notification`
  - `knowledge_loader`
- `operation`
  - `fetch_content`
  - `upload_attachment`
  - `write_log`
  - `search_places`
  - `extract_keyframes`
  - `extract_ocr`
  - `job_run`
  - `push_message`
- `severity`
  - `debug`
  - `info`
  - `warning`
  - `error`
  - `critical`
- `error_code`
- `exception_type`
- `message`
- `retry_count`
- `fallback_used`
- `user_visible_impact`
  - `none`
  - `degraded`
  - `failed_request`
  - `silent_background_failure`
- `request_metadata`
- `created_at`

Purpose:

- record deterministic failures even if the app recovers
- distinguish degraded-success from hard failure

Examples:

- OCR failed, but the system fell back to transcript only
- Google Places timed out, but nearby shortlist used local cache
- ffmpeg failed, so video refinement could not complete
- job retry count hit 3 and the job was marked failed

## 6. User Feedback / Dissatisfaction

Suggested table:

- `feedback_events`

Suggested fields:

- `id`
- `user_id`
- `trace_id`
- `target_trace_id`
- `feedback_type`
  - `explicit_positive`
  - `explicit_negative`
  - `apply_suggested_update`
  - `dismiss_suggested_update`
  - `correction_after_answer`
  - `clarification_abandon`
  - `not_answered_question`
  - `wrong_task_route`
- `feedback_label`
  - `答非所問`
  - `熱量不合理`
  - `不是這個意思`
  - `問題太多`
  - `推薦不實用`
  - `這附近沒有適合的`
- `free_text`
- `severity`
  - `low`
  - `medium`
  - `high`
- `created_at`

Purpose:

- make dissatisfaction queryable
- turn complaints into dataset and backlog

## 7. Unknown Case Queue

Suggested table:

- `unknown_case_events`

Suggested fields:

- `id`
- `trace_id`
- `task_run_id`
- `task_family`
- `unknown_type`
  - `unknown_food`
  - `unknown_brand`
  - `unknown_menu_item`
  - `unknown_packaging`
  - `unknown_location`
  - `unknown_nutrition_fact`
  - `cannot_disambiguate`
- `raw_query`
- `source_hint`
- `ocr_hits`
- `transcript`
- `current_answer`
- `suggested_research_area`
- `review_status`
  - `new`
  - `triaged`
  - `resolved_in_knowledge_pack`
  - `ignored`
- `created_at`

Purpose:

- build a structured research backlog
- feed the knowledge pack on purpose instead of by memory

## 8. Outcome Events

Suggested table:

- `outcome_events`

Suggested fields:

- `id`
- `trace_id`
- `task_family`
- `outcome_type`
  - `meal_auto_recorded`
  - `meal_confirmed`
  - `meal_corrected`
  - `suggested_update_applied`
  - `suggested_update_dismissed`
  - `recommendation_clicked`
  - `nearby_result_opened`
  - `overlay_accepted`
  - `overlay_dismissed`
- `target_id`
- `created_at`

Purpose:

- connect answers to user behavior

## Minimum Instrumentation By Task

### `meal_log_now`

Must record:

- route
- source_mode
- parsed_items
- missing_slots
- estimation_confidence
- confirmation_mode
- clarification_used
- final outcome

Success signals:

- auto-record or confirm without later correction
- low clarification count
- no explicit dissatisfaction

Failure signals:

- later correction
- generic estimate fallback
- `熱量不合理`
- repeated unresolved draft

### `clarification`

Must record:

- question type
- answer mode
- budget before / after
- whether comparison mode was used
- whether the question reduced uncertainty

Success signals:

- uncertainty shrinks
- draft resolves

Failure signals:

- budget exhausted
- user stops replying
- same slot asked again later

### `nutrition_or_food_qa`

Must record:

- local retrieval hits
- whether web fallback was used
- unknown type if local failed
- user dissatisfaction

Success signals:

- local hit
- no correction / complaint

Failure signals:

- `answer_not_found`
- web fallback too often
- user says answer is off-topic

### `nearby_recommendation`

Must record:

- location mode
  - current
  - destination
  - saved place
  - manual
- whether user memory or nearby search supplied results
- whether user clicked a result
- whether async refinement improved shortlist

Success signals:

- result clicked
- saved place / favorite store reused

Failure signals:

- no location context
- user abandons after shortlist
- repeated `這附近沒有適合的`

### `suggested_update_review`

Must record:

- original kcal
- suggested kcal
- delta
- reason
- grounding type
- user applied or dismissed

Success signals:

- apply rate

Failure signals:

- dismiss rate
- repeated dismisses for same source / grounding type

## How To Evaluate

## Offline eval sets

Yes, design evals **by task**.

### Suggested offline eval suites

- `routing_eval_set`
- `meal_parse_eval_set`
- `clarification_eval_set`
- `confirmation_eval_set`
- `correction_eval_set`
- `nearby_recommendation_eval_set`
- `nutrition_qa_eval_set`
- `suggested_update_eval_set`
- `video_grounding_eval_set`

Each row should contain:

- input
- optional attachments / OCR / transcript
- expected task
- expected key slots
- expected answer class
- acceptable uncertainty
- unacceptable failure modes

## Online product metrics

Track these per task and per model / prompt version.

### Intake

- auto-record rate
- correction-after-confirm rate
- average clarification count
- generic-estimate fallback rate
- unresolved draft rate

### Recommendation

- recommendation open rate
- nearby result click-through
- favorite store reuse rate
- golden order reuse rate

### Suggested update

- apply rate
- dismiss rate
- average kcal delta

### Knowledge QA

- local-hit rate
- web-fallback rate
- unknown-case rate
- dissatisfaction rate

### Proactive

- future-event ask-first acceptance rate
- weekly recovery acceptance rate
- notification open / action rate
- notification annoyance signals

### Operational

- error rate by component
- fallback rate by component
- retry exhaustion count
- background job failure count
- degraded-success count

## How To Detect Dissatisfaction

Use both explicit and implicit signals.

### Explicit

Capture phrases such as:

- `答非所問`
- `不是這個意思`
- `不是這個`
- `熱量不對`
- `你在講什麼`
- `不要一直問`
- `這附近根本沒有`

These should create `feedback_events` immediately.

### Implicit

Infer dissatisfaction when:

- user immediately rewrites the request
- user repeatedly corrects the same answer
- user dismisses suggested updates from the same source
- user abandons after repeated clarification
- user re-asks the same nutrition question in different wording

These should create low-confidence `feedback_events` with `severity = low` or `medium`.

## Review Workflow

Run a weekly review over:

- top unknown foods / brands / menu items
- top dismissed suggested updates
- top complaint labels
- top ambiguous routes
- top high-correction foods
- top deterministic degraded-success events
- top retry-exhausted jobs

Suggested triage output:

- add to local knowledge pack
- add alias / canonicalization
- adjust routing rule
- adjust clarification rule
- tighten confirmation threshold
- add UI affordance
- fix integration / parser / worker code
- ignore as outlier

## Storage Strategy

You do not need perfect observability on day one.

### Phase 0 minimum

Store these first:

- `conversation_traces`
- `task_runs`
- `uncertainty_events`
- `error_events`
- `feedback_events`
- `unknown_case_events`

That is enough to start improving the system.

### Phase 1

Add:

- `knowledge_events`
- `outcome_events`

### Phase 2

Add:

- offline eval runner and result snapshots
- score by model / prompt / provider version
- component dashboards and alerts

## Metrics / Alerts / Review Queue

The backend now supports a lightweight observability console layer on top of the raw event tables.

### Metric snapshots

Suggested table:

- `observability_metric_snapshots`

Purpose:

- persist periodic task-level metrics
- support alert evaluation and trend review

### Alert rules

Suggested table:

- `alert_rules`

Rule dimensions:

- `metric_key`
- `task_family`
- `window_hours`
- `comparator`
- `threshold`
- `min_sample_size`
- `cooldown_minutes`
- `severity`
- `status`

### Alert events

Suggested table:

- `alert_events`

Purpose:

- record threshold breaches without losing repeated occurrences
- keep alert state queryable (`open`, `acknowledged`, `resolved`)

### Review queue

Suggested table:

- `review_queue_items`

Queue sources:

- `unknown_case_events`
- high-severity `feedback_events`
- retry-exhausted / critical `error_events`
- `alert_events`

Queue dimensions:

- `queue_type`
- `priority`
- `status`
- `source_table`
- `source_id`
- `task_family`
- `normalized_label`

### Current API surface

- `GET /api/observability/dashboard`
- `GET /api/observability/metrics`
- `GET /api/observability/alert-rules`
- `POST /api/observability/alert-rules`
- `POST /api/observability/alerts/evaluate`
- `GET /api/observability/alerts`
- `POST /api/observability/alerts/{alert_id}/status`
- `GET /api/observability/review-queue`
- `POST /api/observability/review-queue/{item_id}/status`

### Dashboard surface

The dashboard layer should not collapse observability into one generic chart wall.
It should keep separate panels for:

- **summary cards**
  - open alerts
  - new review items
  - nutrition unknown rate
  - dissatisfaction rate
  - retry exhausted count
- **task health**
  - success rate
  - fallback rate
  - unknown-case rate
  - dissatisfaction rate
  - all grouped by `task_family`
- **quality trends**
  - unknown cases by day
  - explicit negative feedback by day
  - degraded errors by day
  - new review queue items by day
- **usage**
  - provider request counts
  - model request breakdown
  - average latency by provider/model
  - token or cost accounting when provider metadata is available
- **memory digest**
  - total signals
  - stable signals
  - active hypotheses
  - tentative hypotheses
  - top signal dimensions
  - top signals / hypotheses
  - reporting bias snapshot
- **operational**
  - error-by-component
  - top error codes
- **eval / review**
  - top unknown labels
  - top feedback labels
  - open alerts
  - high-priority review items
  - critical errors

The purpose is to let the product team answer three different questions quickly:

- what is failing technically
- what is answering badly
- what the memory system is currently learning

## Privacy / Practical Rules

- store attachment references, not duplicated raw media payloads
- store hashes or summaries for large raw inputs when possible
- keep the exact user-facing response text or a compact version for review
- always keep enough metadata to reconstruct why the answer happened
- never log access tokens, DB passwords, or raw secrets
- avoid logging unnecessary personal data if it is not needed for debugging or eval

## Concrete Implementation TODO

### Phase 1: Trace plumbing

- add `conversation_traces`
- add `task_runs`
- emit one trace per user-visible turn
- emit one task run per internal routed task
- add shared `trace_id` propagation

### Phase 2: Uncertainty and fallback logging

- add `uncertainty_events`
- log missing slots, ambiguity flags, clarification budget, stop reason
- log whether generic estimate fallback was used

### Phase 3: Deterministic error logging

- add `error_events`
- add helper wrappers for:
  - LINE API
  - Supabase Storage
  - Google Places
  - ffmpeg
  - tesseract
  - background jobs
- log both hard failures and degraded-success fallbacks

### Phase 4: Feedback capture

- add `feedback_events`
- add helper logic for explicit complaint phrases
- add helper logic for implicit dissatisfaction heuristics
- wire `apply` / `dismiss` of suggested updates into feedback

### Phase 5: Knowledge gap queue

- add `unknown_case_events`
- log unknown food / unknown brand / unknown menu item / answer-not-found
- add review status field

### Phase 6: Outcome logging

- add `outcome_events`
- log record / confirm / correct / apply update / dismiss update / overlay accept

### Phase 7: Offline eval harness

- define task eval datasets
- define per-task metrics
- save eval run snapshots with:
  - provider
  - model
  - prompt version
  - knowledge pack version

## What We Already Have

The current app already stores some useful pieces:

- `confidence`
- `uncertainty_note`
- `ambiguity_flags`
- `missing_slots`
- `confirmation_mode`
- `clarification_used`
- `suggested_update`
- `reporting_bias`
- correction traces inside meal metadata
- job retry count and last error for background jobs

That is a good start, but it is not yet enough for true evals because it still lacks:

- unified trace ids
- explicit user dissatisfaction records
- unknown-case queue
- per-task success / failure outcomes
- model / prompt / retrieval event logging
- structured deterministic error events

## Final Rule

If the question is:

- `Did the model do badly?`

that is too vague.

The system should let you answer:

- did routing fail?
- did grounding fail?
- did local knowledge miss?
- did confirmation ask too much?
- did the user reject the estimate?
- did the user say the answer was off-topic?
- did we simply not know the food?
- did OCR fail and force a degraded answer?
- did Google Places fail and force a cache fallback?
- did a worker retry out and silently reduce quality?

That is the level of observability that will actually let you optimize the app.
