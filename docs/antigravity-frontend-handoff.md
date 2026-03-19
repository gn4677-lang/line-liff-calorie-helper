# Antigravity Frontend Handoff

Source of truth for frontend and interaction work on the LINE + LIFF calorie helper.

- Product baseline: [product-spec-v1.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/product-spec-v1.md)
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
- Frontend is currently a functional shell, not a polished product UI.

## Frontend Goal

Antigravity should treat the current frontend as a working prototype and replace it with a stronger product-quality LIFF experience.

The design target is not "generic dashboard". It should feel like:

- a daily cockpit for calorie decisions
- a fast meal logging surface
- a low-anxiety coach for uncertain food logging
- a narrow recommendation engine that helps decide what to eat now

The UI should preserve the existing product structure:

- `Progress`
- `Today`
- `Eat`

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

## Required Screens

### 1. Progress

Purpose:
- answer "am I on track?"

Must show:
- today's weight entry or latest weight
- 7-day average
- 14-day direction
- daily calorie target
- target adjustment hint

Interaction notes:
- weight logging should be extremely short
- single-day fluctuations should not feel alarming

### 2. Today

Purpose:
- answer "what did I eat, how much is left, what should I do next?"

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
- clarification should feel like a compact conversational step, not a big form
- draft should feel temporary and easy to finish

### 3. Eat

Purpose:
- answer "what can I eat right now?"

Must show:
- grouped recommendations
- day plan
- compensation options

Interaction notes:
- recommendation groups should be visually distinct
- should privilege "few useful options" over "large list"

## Key Flows To Design

### Boot Flow

1. Open LIFF
2. Load `GET /api/client-config`
3. Initialize LIFF
4. If not logged in, LIFF login redirect
5. If logged in, fetch `GET /api/me` with `X-Line-Id-Token`
6. Load summary and recommendations

States needed:
- booting
- auth failed
- authenticated and loading data
- ready

### Meal Logging Flow

1. User enters meal text
2. `POST /api/intake`
3. If draft is `awaiting_clarification`, show follow-up question inline
4. `POST /api/intake/{draft_id}/clarify`
5. When draft is ready, let user confirm
6. `POST /api/intake/{draft_id}/confirm`
7. Refresh summary and recommendations

States needed:
- idle
- estimating
- clarifying
- ready to confirm
- confirmed
- error

### Weight Logging Flow

1. User enters weight
2. `POST /api/weights`
3. Refresh summary area

### Recommendation Flow

1. Load `GET /api/recommendations`
2. Group by recommendation group
3. Render concise cards

## API Contracts Antigravity Should Assume

### `GET /api/client-config`

Response:

```json
{
  "liff_id": "2009526305-adlzUvHT",
  "auth_required": true
}
```

### `GET /api/me`

Headers:

```text
X-Line-Id-Token: <liff id token>
```

Response:

```json
{
  "line_user_id": "Uxxxx",
  "display_name": "User Name",
  "daily_calorie_target": 1800,
  "provider": "heuristic",
  "now": "2026-03-19T04:43:57.834294Z"
}
```

### `GET /api/day-summary`

Response shape:

```json
{
  "coach_message": "string",
  "summary": {
    "date": "2026-03-19",
    "target_kcal": 1800,
    "consumed_kcal": 650,
    "remaining_kcal": 1150,
    "logs": [],
    "seven_day_average_weight": 72.1,
    "fourteen_day_direction": "down",
    "target_adjustment_hint": "Keep current target for now."
  }
}
```

### `POST /api/intake`

Request:

```json
{
  "text": "雞胸便當加半碗飯",
  "meal_type": "lunch",
  "mode": "standard",
  "source_mode": "text",
  "attachments": []
}
```

Response shape:

```json
{
  "coach_message": "string",
  "draft": {
    "id": "uuid",
    "date": "2026-03-19",
    "meal_type": "lunch",
    "status": "awaiting_clarification",
    "source_mode": "text",
    "mode": "standard",
    "parsed_items": [],
    "missing_slots": [],
    "followup_question": "飯大概吃幾成？",
    "estimate_kcal": 540,
    "kcal_low": 460,
    "kcal_high": 650,
    "confidence": 0.72,
    "uncertainty_note": "portion is still uncertain"
  }
}
```

### `POST /api/intake/{draft_id}/clarify`

Request:

```json
{
  "answer": "飯吃一半，雞胸有吃完"
}
```

### `POST /api/intake/{draft_id}/confirm`

Request:

```json
{
  "force_confirm": false
}
```

### `GET /api/recommendations`

Response shape:

```json
{
  "coach_message": "string",
  "recommendations": {
    "remaining_kcal": 1150,
    "items": [
      {
        "name": "Subway 6-inch chicken",
        "meal_types": ["lunch", "dinner"],
        "kcal_low": 350,
        "kcal_high": 450,
        "group": "最穩",
        "reason": "high protein, easy to estimate",
        "external_links": [],
        "is_favorite": true,
        "is_golden": true
      }
    ]
  }
}
```

### `POST /api/weights`

Request:

```json
{
  "weight": 72.4
}
```

### `POST /api/plans/day`

Request:

```json
{}
```

### `POST /api/plans/compensation`

Request:

```json
{
  "expected_extra_kcal": 600
}
```

## Suggested Design Direction

Avoid:

- generic admin dashboard look
- flat white cards everywhere
- dense tables
- long forms for meal logging
- too many recommendation items

Prefer:

- mobile-first stacked layout
- strong hierarchy around remaining calories
- draft card that feels conversational
- grouped recommendation blocks with distinct visual tone
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

Antigravity should not change without coordinating:

- LIFF auth contract
- backend endpoint names
- request and response field names
- webhook assumptions
- database schema assumptions

## Acceptance Bar For Frontend Revision

- LIFF opens and authenticates without extra manual steps
- first screen clearly shows remaining calories
- logging a meal feels possible in under 30 seconds
- clarification flow feels compact and non-annoying
- recommendation screen feels actionable, not informational
- UI works on common mobile widths inside LINE
- no secrets are exposed in frontend

## Recommended Working Strategy For Antigravity

1. Read [product-spec-v1.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/product-spec-v1.md) for product intent.
2. Read [App.tsx](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/frontend/src/App.tsx) only to understand current API usage and LIFF boot flow.
3. Preserve the boot/auth/API logic.
4. Replace the current UI shell with a stronger componentized frontend.
5. Keep production deploy target unchanged.
