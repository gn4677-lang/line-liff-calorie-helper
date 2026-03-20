# Activity / Energy Integration Report

## What changed

- Distilled [Tedd.md](C:/Users/exsaf/Desktop/新增資料夾/Tedd.md) into permanent local knowledge packs:
  - [activity_met_values_tw.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/activity_met_values_tw.json)
  - [energy_model_rules_tw.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/energy_model_rules_tw.md)
- Registered those packs in [pack_registry.json](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/knowledge/pack_registry.json).
- Added an energy-question service in [energy_qa.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/energy_qa.py).
- Wired `/api/qa/nutrition` and LINE webhook text replies through that service.
- Added startup prewarm for the knowledge layer in [main.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/main.py).

## Product logic

The app now treats energy state in two layers:

- Stable layer:
  - `estimated_tdee_kcal`
  - `base_target_kcal`
  - `default_daily_deficit_kcal`
- Daily variable layer:
  - `today_activity_burn_kcal`
  - `effective_target_kcal`
  - `remaining_kcal`

This is the important rule:

- Do not rewrite TDEE when the user logs exercise on the same day.
- Same-day exercise should only change `today_activity_burn_kcal`, which then changes `effective_target_kcal`.

That keeps the long-term body model stable while still letting the user see today's usable budget move.

## QA behavior

`/api/qa/nutrition` now answers three additional calorie-question classes before falling back to food QA:

1. Remaining calorie questions
2. TDEE / body-goal questions
3. Activity-burn questions

Examples now supported:

- `我今天還剩多少熱量`
- `我的 TDEE 是多少`
- `我跳舞跳了兩小時消耗多少熱量`

Activity-burn estimates use:

- local MET pack match
- latest known body weight when available
- parsed duration from natural language
- range-based answers instead of fake precision

If weight is missing, the answer degrades to a generic 60-75 kg adult range.

## LINE behavior

LINE text routing now explicitly recognizes energy questions. That means the chat surface can answer:

- remaining calories
- TDEE context
- exercise-burn questions

without sending those messages down the food-estimation path.

## Frontend implications

The correct Progress-page hierarchy is:

1. Stable TDEE card
2. Daily effective budget card
3. Remaining-calorie card

I also updated [ProgressPage.tsx](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/frontend/src/pages/ProgressPage.tsx) to show:

- `今日可用熱量`
- `今日剩餘`

with the formula surfaced as:

- `base + activity`

## Antigravity note

I updated [antigravity-three-page-handoff.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/antigravity-three-page-handoff.md) so the frontend handoff now states:

- TDEE must stay stable
- activity burn is a separate daily add-back
- effective target needs its own visual treatment

## Validation

Passed:

- `pytest backend/tests/test_energy_qa.py backend/tests/test_confirmation_and_qa.py backend/tests/test_three_page_workflows.py -q`

Covered scenarios:

- remaining calories from day summary
- TDEE answer with daily activity context
- dance burn estimate using latest weight
- LINE webhook reply for dance-burn question
