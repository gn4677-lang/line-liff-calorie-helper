# Conversation, Confirmation, and Weekly Overlay Tech Spec

Implementation reference for the chat router, meal confirmation engine, clarification budget, portion comparison mode, and weekly overlay behavior.

## Goals

- keep meal logging low-friction
- auto-record high-confidence meals
- cap follow-up questions with a clear budget
- make weekly recovery a soft overlay instead of rewriting the base target
- keep conversation behavior explainable for frontend and bot surfaces

## Task Routing

The chat router uses a hierarchical classification strategy.

### Layer 1

- `logging`
- `query`
- `settings_or_help`
- `ambiguous`

### Layer 2

- `meal_log_now`
- `meal_log_correction`
- `future_event_probe`
- `weekly_drift_probe`
- `remaining_or_recommendation`
- `weight_log`
- `nutrition_or_food_qa`
- `preference_or_memory_correction`
- `meta_help`
- `fallback_ambiguous`

When confidence is low, the system does not guess. It returns a short disambiguation prompt and LINE quick replies.

## Confirmation Engine

Each intake must end up in one of four modes:

- `auto_recordable`
- `needs_clarification`
- `needs_confirmation`
- `correction_preview`

### Auto-recordable

Conditions:

- `estimation_confidence >= 0.78`
- no high-impact missing slots

Behavior:

- write the meal log immediately
- still reply with estimate, range, uncertainties, and an edit hint

### Needs clarification

Conditions:

- at least one high-impact missing slot
- clarification budget still available

Behavior:

- ask one question only
- prefer portion comparison chips when the missing slot is portion-related

### Needs confirmation

Conditions:

- budget exhausted, or
- the estimate is usable but not safe to silently auto-record

Behavior:

- stop asking more questions
- explicitly say the system is using a generic portion estimate

### Correction preview

Behavior:

- do not create a duplicate meal log
- preview a recalculated version of the most relevant recent log
- confirm before overwriting

## Confidence Model

### Estimation confidence

Evidence-based only.

Inputs:

- source quality
- identified items
- portion resolution
- high-calorie modifier resolution
- leftover / sharing resolution
- ambiguity penalties

### Confirmation calibration

Does not change raw estimation confidence.

Inputs from the last 7 days:

- reporting bias
- correction rate
- log completeness
- weekly drift status

Purpose:

- temporarily make the system more conservative
- automatically relax again when user behavior stabilizes

## Clarification Budget

Budget is stored in draft metadata:

- `clarification_budget`
- `clarification_used`
- `asked_slots`
- `last_question_type`
- `comparison_mode_used`
- `stop_reason`

Mode budgets:

- `quick`: 0-1
- `standard`: 1-2
- `fine`: up to 4

## Portion Comparison Mode

Comparison mode is a fallback for unresolved portion questions.

Priority:

1. confirmed L1 meal logs
2. user-stated anchors
3. generic anchors

Default quick reply anchors:

- `半碗`
- `一碗`
- `比便當白飯少`
- `比便當白飯多`
- `一個手掌大小`
- `跟上次差不多`
- `我自己補一句`

## Weekly Overlay

The base `daily_calorie_target` stays unchanged.

Weekly layer adds:

- `weekly_target_kcal`
- `weekly_consumed_kcal`
- `weekly_drift_kcal`
- `weekly_remaining_kcal`
- `weekly_drift_status`
- `should_offer_weekly_recovery`
- `recovery_overlay`

Overlay is used when a compensation option is accepted. It stores:

- `overlay_days`
- `overlay_allocations`
- `overlay_reason`
- `overlay_active_until`

Frontend should display this as `補償中`, not as a new permanent target.

## LINE UX

- Rich Menu: persistent entry only
- Quick Reply: clarification chips, disambiguation, weekly recovery options
- LIFF: larger comparison UI, history edits, and full planning views

## Files

Core implementation lives in:

- [routes.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/api/routes.py)
- [intake.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/intake.py)
- [confirmation.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/confirmation.py)
- [summary.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/summary.py)
