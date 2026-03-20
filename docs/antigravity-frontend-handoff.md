# Antigravity Frontend Handoff

Source of truth for frontend and interaction work on the LINE + LIFF calorie helper.

## Reference Docs

- Product baseline: [product-spec-v1.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/product-spec-v1.md)
- Memory design: [memory-onboarding-v2.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/memory-onboarding-v2.md)
- Memory schema: [memory-schema-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/memory-schema-spec.md)
- Conversation / confirmation: [conversation-confirmation-tech-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/conversation-confirmation-tech-spec.md)
- Knowledge pack: [knowledge-pack-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/knowledge-pack-spec.md)
- Proactivity / nearby search: [proactivity-tech-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/proactivity-tech-spec.md)
- Evals / observability: [evals-observability-tech-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/evals-observability-tech-spec.md)
- Observability admin UI: [observability-admin-ui-contract.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/observability-admin-ui-contract.md)
- Surface split / chat vs LIFF: [surface-interaction-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/surface-interaction-spec.md)
- Video intake: [video-intake-tech-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/video-intake-tech-spec.md)
- Execution checklist: [TODO.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/TODO.md)
- Current frontend shell: [App.tsx](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/frontend/src/App.tsx)
- Current backend contracts: [schemas.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/schemas.py)
- Production app: [gn4677-calorie-helper.ai-builders.space](https://gn4677-calorie-helper.ai-builders.space/)
- LIFF URL: [liff.line.me/2009526305-adlzUvHT](https://liff.line.me/2009526305-adlzUvHT)

## Current State

- Backend is live on Builder Space.
- Database is live on Supabase Postgres.
- Attachments are stored in Supabase Storage.
- LINE webhook is implemented.
- LIFF auth is implemented with real ID token verification.
- Cold-start onboarding, memory APIs, nutrition QA, weekly summary, nearby recommendation APIs, async update jobs, notifications, and video intake APIs now exist.
- Frontend is still a prototype shell and should be upgraded.

## Core LIFF Surfaces

Do not collapse these into a single generic dashboard.

### 1. 體重熱量

Purpose:

- answer `Am I on track this week?`

Must show:

- latest weight
- 7-day average
- 14-day direction
- daily target
- weekly drift
- recovery overlay state when active
- target-adjustment or recovery hint when relevant

### 2. 今日紀錄

Purpose:

- answer `What did I eat, how much is left, and what should I do next?`

Must show:

- consumed / remaining kcal
- weekly drift summary
- meal log list
- active draft state
- clarification UI
- confirmation / correction surfaces
- answer chips when `answer_mode = chips_first_with_text_fallback`
- pending async updates

### 3. 食物推薦

Purpose:

- answer `What can I eat right now, and where should I get it?`

Must show:

- grouped recommendations
- reason factors
- nearby recommendation launcher
- saved places and favorite stores
- golden orders
- day plan
- compensation options
- overlay-aware planning state

## Surface Rules

- `LINE chat` handles capture, short clarification, correction preview, quick nudges, async update decisions, and location branching.
- `今日紀錄` handles today truth-state, unresolved drafts, same-day async updates, and today recovery overlay.
- `食物推薦` handles nearby / destination-based choice, recommendation browsing, favorite stores, and golden orders.
- `體重熱量` handles weekly drift, trends, plan events, and recovery decisions.
- The same proactive behavior must not be duplicated across all surfaces; follow [surface-interaction-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/surface-interaction-spec.md).

## Internal Admin Surface

- Observability should be rendered as a separate internal admin surface, not merged into the three user-facing pages.
- Keep error / debug / eval / review queue separated into distinct panels.
- Include:
  - summary cards
  - task health table
  - quality trend charts
  - provider / model usage panel
  - memory digest panel
  - operational error panel
  - alert list
  - review queue panel

## Non-Negotiable Constraints

- Keep backend contracts stable unless there is a strong reason to change them.
- Keep LIFF auth flow intact:
  - load `GET /api/client-config`
  - initialize LIFF SDK
  - send `X-Line-Id-Token`
  - backend verifies and binds the user
- Do not put secrets in frontend code.
- Assume LIFF first, desktop browser second.
- Optimize for mobile-first interaction density.
- Keep onboarding answers and corrections structured and easy to revise.
- Keep the three-page split explicit; do not merge them into one super-page.

## Required Flows

### Boot Flow

1. Open LIFF
2. Load `GET /api/client-config`
3. Initialize LIFF
4. Authenticate and load `GET /api/me`
5. Load onboarding state, summary, recommendations, notifications

### Cold Start Flow

1. `GET /api/onboarding-state`
2. If `should_show = true`, show the 5-question onboarding card
3. Submit to `POST /api/preferences/onboarding`
4. Or skip via `POST /api/onboarding/skip`

### Meal Logging Flow

1. User enters meal text, photo, audio, or video
2. `POST /api/intake` or `POST /api/intake/video`
3. If `confirmation_mode = auto_recordable`, show success state immediately
4. If `needs_clarification`, show one follow-up question and answer chips when present
5. `POST /api/intake/{draft_id}/clarify`
6. If needed, `POST /api/intake/{draft_id}/confirm`

### Correction Flow

1. User triggers correction from chat or LIFF
2. System creates a correction preview
3. UI shows new kcal, old kcal, and overwrite intent
4. Confirm to overwrite the previous record

### Nearby Recommendation Flow

1. User enters recommendation mode
2. UI asks where to search:
   - current area
   - destination
   - saved place
   - manual input
3. `POST /api/location/resolve` or `POST /api/recommendations/nearby`
4. Show heuristic shortlist immediately
5. If `search_job_id` exists, poll `GET /api/search-jobs/{job_id}`
6. Surface improved nearby candidates or async update actions when ready

### Async Update Flow

1. Intake or nearby search creates a `search_job`
2. UI polls notifications or job status
3. If a better estimate is found, show:
   - new kcal
   - old kcal
   - reason
   - sources
4. Let the user `Apply` or `Dismiss`

## Contract Notes

- `DraftResponse` now includes:
  - `confirmation_mode`
  - `estimation_confidence`
  - `confirmation_calibration`
  - `primary_uncertainties`
  - `clarification_kind`
  - `answer_mode`
  - `answer_options`
- `DaySummaryResponse` now includes:
  - weekly fields
  - `recovery_overlay`
  - `pending_async_updates_count`
- `PreferenceResponse` now includes:
  - `communication_profile`
- Nutrition QA is available through:
  - `POST /api/qa/nutrition`
- Proactive APIs now include:
  - `POST /api/recommendations/nearby`
  - `POST /api/location/resolve`
  - `GET /api/notifications`
  - `POST /api/search-jobs/{job_id}/apply`
  - `POST /api/search-jobs/{job_id}/dismiss`
  - `GET /api/saved-places`
  - `GET /api/favorite-stores`
- Video intake APIs now include:
  - `POST /api/intake/video`
  - async `video_precision` jobs
  - richer `suggested_update` with OCR / grounding sources

## Frontend Design Priority

The frontend should make uncertainty feel manageable, not alarming.

Most important UI upgrades:

- clearer draft / clarification states
- better correction preview
- weekly overlay visibility
- explainability entry for recommendations
- structured onboarding and settings surfaces
- nearby recommendation launcher with place-choice branching
- async update inbox / notification center
- saved place and favorite store management
- video upload and pending-refinement state
- the exact cross-surface split defined in [surface-interaction-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/surface-interaction-spec.md)
