# Agentic Ownership Rollout Report

Date: 2026-03-21

## Scope

This rollout implemented the core wiring required to move the app closer to:

- `LLM-first for interpretation, ranking, framing, and importance`
- `deterministic for permission to act, math, filters, writes, queues, and telemetry`

The changes focused on the highest-leverage backend surfaces without introducing any new infra-first subsystem.

## What Was Implemented

### Wave 0

- Added rollout flags in [`backend/app/config.py`](../backend/app/config.py):
  - `chat_correction_llm_enabled`
  - `future_event_llm_enabled`
  - `memory_group_llm_enabled`
  - `proactive_rank_llm_enabled`
  - `canary_only_memory_group_llm`
  - `canary_only_proactive_rank_llm`
- Added shared rollout helpers:
  - `is_canary_identity(...)`
  - `llm_rollout_enabled(...)`
- Added typed contracts in [`backend/app/schemas.py`](../backend/app/schemas.py):
  - `CorrectionInterpretation`
  - `FutureMealEventIntent`
  - `ProactiveRankDecision`
- Extended `PreferenceCorrectionRequest` to support soft `dislikes`.

### Wave 1

- Added new LLM support helpers in [`backend/app/services/llm_support.py`](../backend/app/services/llm_support.py):
  - `interpret_chat_correction_sync(...)`
  - `interpret_future_meal_event_sync(...)`
  - `rank_proactive_decision_sync(...)`
- Upgraded `process_line_event_payload(...)` in [`backend/app/api/routes.py`](../backend/app/api/routes.py):
  - correction interpretation now supports:
    - preference correction
    - recent-meal correction override into the correction route
  - future meal event understanding now records a structured intent contract before deterministic parsing
  - contracts are written into trace input metadata
- Fixed webhook worker trace wiring so the event worker updates the existing event trace instead of deriving a second trace id.

### Wave 2

- Upgraded `run_memory_consolidation_job(...)` in [`backend/app/services/memory.py`](../backend/app/services/memory.py):
  - `extract_behavioral_signal_groups_sync(...)` is now explicitly controlled by rollout gating
  - deterministic grouping remains the fallback path
  - fallback reasons are explicit:
    - `memory_group_llm_disabled`
    - `memory_group_canary_only`
    - `memory_grouping_fallback`

### Wave 3

- Reworked [`backend/app/services/daily_nudge.py`](../backend/app/services/daily_nudge.py) so proactive delivery remains deterministic-triggered but LLM-ranked:
  - meal event reminder
  - daily no-log nudge
  - dinner pick
- Added bounded proactive ranking:
  - suppression support
  - why-now framing
  - notification payload metadata:
    - `proactive_rank_decision`
    - `fallback_source`
- Extended webhook worker task-run summaries in [`backend/app/services/background_jobs.py`](../backend/app/services/background_jobs.py) so trace/task-run observability now includes:
  - `structured_intent_route`
  - `correction_interpretation`
  - `future_event_intent`
  - corresponding fallback reasons

## Deterministic Boundaries Preserved

The rollout did **not** hand ownership of these surfaces to the LLM:

- write transitions
- correction apply / overwrite behavior
- meal event creation and date normalization
- memory admission thresholds
- promotion / visibility gates
- kcal / drift / overlay arithmetic
- bounded retrieval and hard filters
- webhook ingress / dedupe / queue behavior
- worker lease / retry state
- telemetry writes

## Tests Run

### Targeted suites

```powershell
python -m pytest `
  backend/tests/test_llm_integration_wiring.py `
  backend/tests/test_line_proactive_extensions.py `
  backend/tests/test_observability_console.py `
  backend/tests/test_confirmation_and_qa.py `
  backend/tests/test_summary_and_recommendations.py `
  backend/tests/test_video_intake.py `
  -q --basetemp <fresh-temp>
```

Result:

- `50 passed`

### Agentic gate

```powershell
.\scripts\run_agentic_checks.ps1
```

Result:

- `59 passed, 48 deselected`
- remote LLM runtime snapshot: `ready`

### Full backend suite

```powershell
python -m pytest backend/tests -q --basetemp <fresh-temp>
```

Result:

- `107 passed`

## Remaining Gaps

These are still intentionally incomplete or only partially expanded:

- recommendation policy already had an LLM layer; this rollout did not redesign the candidate generation stack
- weekly coaching already had an LLM layer; this rollout did not add a separate planning copywriter pass
- clarification next-question choice remains hybrid but still largely bounded by the existing confirmation engine
- proactive ranking is now wired for notifications, but not yet expanded into a broader multi-trigger importance marketplace

## Operational Note

This rollout exercised the real remote-runtime assumption only at the configuration gate level:

- `AI_PROVIDER=builderspace`
- `AI_BUILDER_TOKEN` present

The code paths were validated with monkeypatched provider calls in tests and the repo agentic gate reported runtime as `ready`.
