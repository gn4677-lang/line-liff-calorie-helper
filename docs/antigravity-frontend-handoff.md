# Antigravity Frontend Handoff

Source of truth for frontend and interaction work on the LINE + LIFF calorie helper.

- Product baseline: [product-spec-v1.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/product-spec-v1.md)
- Memory design: [memory-onboarding-v2.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/memory-onboarding-v2.md)
- Execution checklist: [TODO.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/TODO.md)
- Architecture: [architecture.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/architecture.md)
- Current frontend shell: [App.tsx](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/frontend/src/App.tsx)
- Current backend contracts: [schemas.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/schemas.py)
- Production app: [gn4677-calorie-helper.ai-builders.space](https://gn4677-calorie-helper.ai-builders.space/)
- LIFF URL: [liff.line.me/2009526305-adlzUvHT](https://liff.line.me/2009526305-adlzUvHT)

## What Exists

- Backend is live on Builder Space.
- Database is live on Supabase Postgres.
- Attachments are stored in Supabase Storage.
- LINE webhook is implemented.
- LIFF auth is implemented with real ID token verification.
- Cold-start onboarding and memory APIs now exist.
- Frontend is still a prototype shell and should be upgraded.

## Frontend Goal

Treat the current frontend as a working prototype and replace it with a stronger product-quality LIFF experience.

The target is not a generic dashboard. It should feel like:

- a daily cockpit for calorie decisions
- a fast meal logging surface
- a low-anxiety coach for uncertain food logging
- a narrow recommendation engine that helps decide what to eat now
- a light-touch onboarding flow that seeds the system without feeling like setup ceremony

The product structure must stay:

- `體重熱量`
- `今日紀錄`
- `食物推薦`

## Non-Negotiable Constraints

- Keep backend contracts stable unless there is a strong reason to change them.
- Keep LIFF auth flow intact:
  - frontend bootstraps from `GET /api/client-config`
  - frontend initializes LIFF SDK
  - frontend sends `X-Line-Id-Token` to backend
  - backend verifies ID token and binds the user
- Do not put secrets in frontend code.
- Assume this runs inside LIFF first, desktop browser second.
- Optimize for mobile-first interaction density.
- Preserve the 3-page information architecture from the spec.
- Keep onboarding answers and corrections simple, structured, and easy to revise later.

## Required Screens

### 1. 體重熱量

Purpose:
- answer “am I on track?”

Must show:
- latest weight entry
- 7-day average
- 14-day direction
- daily calorie target
- target adjustment hint

Interaction notes:
- weight logging should be extremely short
- single-day fluctuations should not feel alarming

### 2. 今日紀錄

Purpose:
- answer “what did I eat, how much is left, what should I do next?”

Must show:
- current day summary
- consumed kcal
- remaining kcal
- meal log list
- active draft state
- clarification UI when needed
- confirm / force confirm actions
- quick entry for text logging

Interaction notes:
- this is the main daily cockpit
- clarification should feel like a compact conversational step, not a form wizard
- draft should feel temporary and easy to finish

### 3. 食物推薦

Purpose:
- answer “what can I eat right now?”

Must show:
- grouped recommendations
- day plan
- compensation options
- optional explainability entry or inline factors

Interaction notes:
- recommendation groups should be visually distinct
- privilege a few usable options over a large searchable list

## Required Flows

### Boot Flow

1. Open LIFF
2. Load `GET /api/client-config`
3. Initialize LIFF
4. If not logged in, LIFF login redirect
5. If logged in, fetch `GET /api/me` with `X-Line-Id-Token`
6. Load onboarding state, summary, recommendations

States needed:
- booting
- auth failed
- authenticated and loading data
- ready

### Cold Start Flow

1. Load `GET /api/onboarding-state`
2. If `should_show = true`, show a 5-question onboarding card
3. Submit to `POST /api/preferences/onboarding`
4. Or skip via `POST /api/onboarding/skip`
5. Refresh recommendation and planning surfaces

States needed:
- unseen
- answering
- skipped
- completed

### Meal Logging Flow

1. User enters meal text
2. `POST /api/intake`
3. If draft is `awaiting_clarification`, show follow-up question inline
4. `POST /api/intake/{draft_id}/clarify`
5. When draft is ready, let user confirm
6. `POST /api/intake/{draft_id}/confirm`
7. Refresh summary and recommendations

### Preference Correction Flow

1. User opens settings or taps a correction surface
2. Load `GET /api/preferences`
3. Submit changes to `POST /api/preferences/correction`
4. Refresh recommendation and planning views

## API Contracts Antigravity Should Assume

### `GET /api/onboarding-state`

```json
{
  "should_show": true,
  "completed": false,
  "skipped": false,
  "version": "v1",
  "preferences": {
    "breakfast_habit": "variable",
    "carb_need": "flexible",
    "dinner_style": "normal",
    "hard_dislikes": [],
    "compensation_style": "let_system_decide"
  }
}
```

### `POST /api/preferences/onboarding`

```json
{
  "breakfast_habit": "rare",
  "carb_need": "flexible",
  "dinner_style": "high_protein",
  "hard_dislikes": ["韓式"],
  "compensation_style": "gentle_1d"
}
```

### `GET /api/preferences`

```json
{
  "breakfast_habit": "rare",
  "carb_need": "flexible",
  "dinner_style": "high_protein",
  "hard_dislikes": ["韓式"],
  "compensation_style": "gentle_1d"
}
```

### `POST /api/preferences/correction`

Partial update:

```json
{
  "breakfast_habit": "regular",
  "correction_note": "我最近開始吃早餐了"
}
```

### `GET /api/recommendations`

Each item now supports:

```json
{
  "name": "雞胸便當",
  "group": "高蛋白優先",
  "reason": "蛋白質密度較高，通常更適合減脂期的主力選擇。",
  "reason_factors": [
    "晚餐你通常比較接受高蛋白選項。",
    "這個選項的蛋白質密度比較高。"
  ]
}
```

### `POST /api/plans/day`

Response now supports:

```json
{
  "plan": {
    "allocations": {
      "breakfast": 180,
      "lunch": 630,
      "dinner": 720,
      "flex": 270
    },
    "reason_factors": [
      "你最近早餐通常吃得比較少，所以把熱量額度往午晚餐和彈性空間移。"
    ]
  }
}
```

### `POST /api/plans/compensation`

Response now supports:

```json
{
  "compensation": {
    "options": [],
    "reason_factors": [
      "你偏向不要做激烈補償，所以先以回到正常軌道為主。"
    ]
  }
}
```

## Suggested Design Direction

Avoid:

- generic admin dashboard look
- flat white cards everywhere
- dense tables
- long forms for meal logging
- too many recommendation items
- onboarding that feels like profile setup ceremony

Prefer:

- mobile-first stacked layout
- strong hierarchy around remaining calories
- draft card that feels conversational
- grouped recommendation blocks with distinct visual tone
- onboarding that feels short, useful, and skippable
- preference correction surfaces that feel lightweight rather than settings-heavy
- subtle but intentional motion
- a visual direction that feels personal and coach-like rather than enterprise

## Safe Refactor Boundaries

Antigravity can safely change:

- component structure
- state organization in frontend
- CSS system
- page layout
- interaction design
- loading, error, empty states
- onboarding UI
- explainability presentation

Antigravity should not change without coordinating:

- LIFF auth contract
- backend endpoint names
- request and response field names
- webhook assumptions
- memory source priority rules
- database schema assumptions

## Acceptance Bar For Frontend Revision

- LIFF opens and authenticates without extra manual steps
- onboarding is understandable in under 20 seconds and skippable
- first screen clearly shows remaining calories
- logging a meal feels possible in under 30 seconds
- clarification flow feels compact and non-annoying
- recommendation screen feels actionable, not informational
- explainability is available but not noisy
- preference correction is easy to find and easy to trust
- UI works on common mobile widths inside LINE
- no secrets are exposed in frontend
