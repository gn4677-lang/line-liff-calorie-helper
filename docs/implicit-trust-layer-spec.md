# Implicit Trust Layer Spec

Implementation-facing spec for the product layer that makes the system feel like it is learning from the user without adding extra survey-style friction.

This spec complements:

- [surface-interaction-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/surface-interaction-spec.md)
- [memory-onboarding-v2.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/memory-onboarding-v2.md)
- [proactivity-tech-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/proactivity-tech-spec.md)
- [evals-observability-tech-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/evals-observability-tech-spec.md)

## Summary

Trust should be built through visible behavioral improvement, not explicit helpfulness prompts.

The trust layer has four jobs:

1. make corrections feel heard
2. make system learning lightly visible
3. make improvements happen immediately
4. measure trust through behavior change rather than surveys

This layer must remain low-friction:

- do not ask "was this helpful?"
- do not add survey-like feedback prompts
- do not turn memory into a user-facing personality report
- do not over-explain every recommendation

## Key Changes

### 1. Self-announcing corrections

When the user corrects a meal estimate or recommendation-related assumption, the system should not update silently.

Required behavior:

- after a correction is applied, send one short confirmation line
- the message should name what changed
- do not ask a follow-up question unless the correction itself still leaves a blocking ambiguity

Examples of acceptable behavior:

- `已改成 800 kcal。`
- `我把這筆改成半碗飯了。`
- `這次先照你剛剛修正的版本。`

Not allowed:

- survey-style confirmation
- long explanations
- immediate extra questioning after a clean correction

Primary surfaces:

- LINE chat
- correction preview apply flow
- suggested update apply flow

### 2. Visible learning, but lightly

The product should show that it has learned something, but only where that directly helps the user.

#### Today page

Show subtle learning cues for:

- entries that were corrected before
- entries using a corrected default
- async updates that refined a prior estimate

Acceptable UI patterns:

- small note under the entry
- corrected badge
- `沿用你上次修正過的份量`

#### Eat page

Show brief context for:

- golden options
- favorite-store-driven recommendations
- recommendation output influenced by past acceptance

Acceptable UI patterns:

- `你常選的穩定選項`
- `根據你最近常接受的類型`
- `這家是你常用店家`

#### Progress page

Show trust-building context for:

- weekly coaching tied to recent behavior
- recovery suggestions influenced by known preferences
- current intervention framed as connected to real recent data

Acceptable UI patterns:

- `根據你這週目前的狀態`
- `照你最近比較容易執行的方式`
- `這次先用你平常較能接受的回收節奏`

Not allowed:

- generic motivational filler
- personality-style labels
- repeated "the system learned you are..." phrasing

### 3. Immediate and durable learning

User correction must update behavior immediately, not only after a slow synthesis job.

Required rule:

- `user_corrected` should take effect in the next similar interaction within 1-2 relevant interactions

Required write behavior:

- correction updates should immediately affect:
  - relevant food defaults
  - relevant preference-like constraints
  - store/order memory where applicable
- the update must persist across sessions
- background memory synthesis may consolidate later, but cannot be the first time the system learns

This is especially important for:

- corrected kcal defaults
- portion expectations
- store/order defaults
- recommendation dislike/avoid signals

### 4. Recommendation outcomes should influence future behavior

Recommendation outcome signals must shape future recommendation policy, but with asymmetric weights.

Strong positive signals:

- clicked
- applied
- accepted top pick
- chosen after shortlist exposure

Strong negative signals:

- explicit dismiss
- explicit dislike
- direct negative correction

Weak negative signals:

- passive ignore

Design rule:

- ignore should lower confidence only slightly
- explicit dismissal should lower confidence much more strongly
- a single passive ignore must not erase a store or candidate from future recommendation surfaces

User-visible trust cue:

- when a recommendation is influenced by past acceptance, show a short reason
- do not show recommendation-score internals

### 5. Silent bias calibration

`reporting_bias` may influence estimation and clarification behavior, but should not be announced explicitly to the user.

Allowed uses:

- raise clarification intensity when vagueness is high
- slightly increase estimate conservatism when underreporting evidence is strong
- tighten confirmation behavior when prior correction frequency is high

Not allowed:

- telling the user they are being adjusted because they are vague
- explicit percentage adjustments explained as bias correction
- large hidden kcal jumps without a visible uncertainty reason

Bias should primarily influence:

- one more question
- a wider range
- a more cautious confirmation stance

not:

- dramatic invisible rewrites

## Public Interfaces / UI Contracts

This trust layer should reuse existing surfaces and contracts instead of introducing new product flows.

### Existing outputs that should carry trust cues

- `reason_factors`
- `hero_reason`
- correction confirmation copy
- suggested update copy
- entry-level metadata on Today timeline
- weekly coaching copy on Progress

### Allowed additions

- corrected-note fields on meal/timeline items
- recommendation provenance labels such as favorite / golden / memory-based
- correction-applied summary text
- trust-related explanation strings for internal admin/debug views

### Explicitly not allowed

- `was_this_helpful`
- thumbs-up / thumbs-down prompts injected into normal product flow
- forced feedback modals
- memory profile shown as a user-facing personality page

## Measurement / Evals

Trust should be measured through behavior change, not direct questionnaires.

Primary signals:

- after a correction, the same mistake does not recur within 1-2 similar interactions
- explicit negative feedback decreases over similar cases
- recommendation dismissals reduce recurrence of similar recommendations in similar contexts
- users can act on recommendations because the displayed reason is legible

Operational signals to track:

- `correction_after_answer`
- `suggested_update_applied`
- `suggested_update_dismissed`
- `explicit_negative_feedback`
- recommendation accepted / ignored / dismissed
- repeated same-error recurrence rate

Good trust outcome:

- the user notices that the system improved without being asked to teach it again

Bad trust outcome:

- the user has to repeat the same correction
- the system learns invisibly but gives no visible sign it listened
- the UI starts asking survey-style questions

## Test Plan

- correcting a kcal estimate sends one short acknowledgment line
- correction does not trigger an unnecessary extra question
- the next similar meal estimate uses the corrected signal within 1-2 interactions
- Today shows subtle corrected/defaulted notes without clutter
- Eat shows short recommendation provenance or reason cues
- Progress frames weekly coaching with recent-context language rather than generic advice
- passive ignore does not over-penalize a candidate
- explicit dismiss has a stronger negative effect than ignore
- reporting bias influences clarification/confirmation silently, without explicit bias messaging
- no explicit helpfulness prompts appear in chat or LIFF

## Assumptions

- the current memory precedence remains:
  - `user_corrected > user_stated > behavior_inferred > model_hypothesis`
- trust cues should stay lightweight and contextual
- this layer is implemented by extending existing chat, Today, Eat, and Progress behavior
- observability continues to capture correction, feedback, and recommendation outcomes, but the product surface should stay low-friction
