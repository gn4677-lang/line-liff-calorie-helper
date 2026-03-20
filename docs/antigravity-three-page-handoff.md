# Antigravity Handoff: Three-Page LIFF Surface

## Product split
- `LINE chat` is the capture home.
  - Natural language meal logging
  - Photo / video intake
  - Quick clarification
  - Future-event capture
  - Activity descriptions
- `LIFF` is the control surface.
  - `日誌`
  - `吃什麼`
  - `身體`

Do not reintroduce chat-style capture UI into LIFF. LIFF should receive already-captured reality, then help the user review, edit, and decide.

## LINE-first routing
- If a task can be completed with one short message, prefer `LINE chat`.
- Use LINE first for:
  - capture
  - confirmation
  - clarification
  - async update apply / dismiss
  - daily nudge
  - future meal reminders
- Use LIFF for:
  - dense daily review
  - batch editing
  - trend reading
  - multi-option exploration

## Three pillars mapping

### Frictionless Interaction
- `LINE chat` handles low-friction capture without forcing the user into a structured form.
- `日誌` now resolves the most common manual tasks inline:
  - tap meal section to add
  - tap meal row to edit
  - no daily-task bottom sheet dependency
- `吃什麼` opens with one strong answer plus light chips; browsing is secondary.
- `身體` shows the current model state first, not a dense settings panel.

### Contextual Intelligence
- `eat-feed` now reads:
  - preferences
  - memory signals
  - active hypotheses
  - recent accepted meals
  - recommendation profile
- session smart chips are generated from that context, not a fixed list.
- `身體` reflects body-goal state and activity-adjusted daily budget instead of asking the user to re-enter everything.

### Proactive Intelligence
- `吃什麼` is now a decision surface, not a recommendation directory.
- ranking remains deterministic and memory-first.
- smart chips are hybrid:
  - LLM may propose the best 3 from a controlled chip taxonomy
  - deterministic gating enforces candidate support and safety
- chip selection only reranks the current session and does not directly write long-term preference.

## Page ownership

### 1. 日誌
- Owns today truth.
- Owns unresolved draft / async review banner.
- Owns inline add, edit, kcal correction, meal-type change, time change, delete.
- Does not own long-term charts as a permanent page section.

### 2. 吃什麼
- Owns proactive meal choice.
- First screen only shows:
  - remaining kcal
  - 1 top pick
  - 2-3 smart chips
  - 2 backup picks
- Explore is secondary and lives in a full-screen layer.
- Does not directly write `meal_log`.
- Does not own weekly recovery or body-model editing.

### 3. 身體
- Owns current weight vs target.
- Owns TDEE / base target / effective target framing.
- Owns activity adjustments and model settings.
- Owns trend charts, weekly recovery, and upcoming plan-event review.

## UI structure

### 日誌
- First screen priority:
  - thin header
  - thin draft inbox if needed
  - breakfast
  - lunch
  - dinner
  - snack
- Interaction:
  - tap meal section header -> inline add
  - tap meal row -> inline edit
  - trend details -> full-screen sheet only

### 吃什麼
- First screen priority:
  - remaining kcal line
  - top-pick hero
  - smart chip rail
  - 2 backups
- Interaction:
  - tap hero or backup -> inline detail
  - tap chip -> rerank current session only
  - tap more -> full-screen explore

### 身體
- First screen priority:
  - current weight vs target hero
  - 3 short metrics
    - estimated TDEE
    - today activity burn
    - today allowed kcal
  - activity summary card
  - trends row
  - model row
- Deep settings and detailed trend views should stay off the first screen.

## Eat-feed contract
- `POST /api/eat-feed`
- request:
  - `meal_type`
  - `time_context`
  - `style_context`
  - `location_mode`
  - `saved_place_id?`
  - `lat?`
  - `lng?`
  - `query?`
  - `selected_chip_id?`
  - `explore_mode`
- response:
  - `session_id`
  - `remaining_kcal`
  - `top_pick`
  - `backup_picks`
  - `exploration_sections`
  - `location_context_used`
  - `smart_chips`
  - `hero_reason`
  - `more_results_available`

## Smart chip rules
- Taxonomy is controlled:
  - `high_protein`
  - `soup`
  - `light`
  - `comfort`
  - `filling`
  - `nearby`
  - `quick_pickup`
  - `repeat_safe`
  - `rice_or_noodle`
  - `indulgent`
- Chips are generated per session from:
  - memory packet
  - meal type
  - remaining kcal
  - recent accepted meals
  - current ranked candidates
- LLM can choose from the shortlisted chips if available.
- deterministic gate still decides whether a chip is allowed to show.
- clicking a chip:
  - reranks the session
  - does not immediately update stored preference

## Deterministic recommendation engine
- Ranking order is still controlled by deterministic scoring:
  - source prior
  - memory fit
  - context fit
  - familiarity bonus
  - repeat penalty
  - distance penalty
  - risk penalty
  - chip bonus
- Slow-learning parameters remain limited:
  - `repeat_tolerance`
  - `nearby_exploration_preference`
  - `favorite_bias_strength`
  - `distance_sensitivity`

## Monitoring surfaces
- Observability dashboard should keep tracking:
  - eat-feed session volume
  - top-pick accept rate
  - backup-pick accept rate
  - nearby accept rate
  - correction-after-acceptance rate
  - top-pick source breakdown
  - recommendation profile coverage and average sample size
  - body-goal coverage
  - activity-adjustment event count

## Design constraints
- No embedded map in v1.
- No large CTA stack on `吃什麼`.
- No dashboard hero on `日誌`.
- No settings-heavy first screen on `身體`.
- No duplicate capture explanation inside LIFF.
