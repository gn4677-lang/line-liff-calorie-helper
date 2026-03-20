# Energy Model Rules

Stable local rules for TDEE, activity-burn estimates, and calorie-budget answers.

## Core Concepts

- TDEE is the user's total daily energy expenditure.
- Treat TDEE as a stable body-goal estimate, not a same-day variable.
- The app should separate:
  - `estimated_tdee_kcal`
  - `base_target_kcal`
  - `today_activity_burn_kcal`
  - `effective_target_kcal`
- `effective_target_kcal` is the daily intake budget after adding back today's activity burn.

## Product Logic

- `estimated_tdee_kcal` should change conservatively over time from weight and intake trends.
- Same-day exercise should not rewrite TDEE.
- Same-day exercise should change `today_activity_burn_kcal`, which then changes `effective_target_kcal`.
- Remaining calories should always be computed from:
  - `effective_target_kcal - consumed_kcal`

## Activity-Burn Estimation

- Use MET-based estimation when the user asks how much an activity burned.
- Base formula:
  - `kcal ~= MET * body_weight_kg * hours`
- Use the user's latest known weight when available.
- If weight is missing, respond with a broad generic range and say why it is broad.
- If duration is missing, give a per-hour estimate and ask for duration.

## Intensity Rules

- Light activity is usually below 3 MET.
- Moderate activity is usually 3.0-5.9 MET.
- Vigorous activity is usually 6+ MET.
- Dance is especially variable by style and effort, so default to a wide range unless the style is explicit.

## Quality Rules

- Do not present activity-burn estimates as exact facts.
- Mention the largest uncertainty driver:
  - body weight
  - duration
  - pace
  - dance style
  - rest density
- Wearables can be directionally useful, but their calorie-burn numbers are noisy.
- The classic `7700 kcal ~= 1 kg` rule is only a rough heuristic and should not be treated as exact short-term planning math.

## Answer Style

- If the user asks about remaining calories, answer with today's numbers first.
- If the user asks about TDEE, answer with:
  - current TDEE
  - base target
  - default daily deficit
  - whether today's activity has added calories back
- If the user asks about activity burn, answer with a range and say what inputs were used.
