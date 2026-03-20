# Proactivity Tech Spec v2

Implementation reference for proactive recommendation flows, nearby search, saved places, async research jobs, and event notifications.

## Goal

Increase usefulness without turning the bot into a noisy push system.

The design principle is:

- ask at the right moment
- preload the next useful step
- notify only for high-value events
- never silently rewrite logs

## Proactivity Layers

### 1. In-conversation proactivity

Triggered only inside the current interaction.

Examples:
- ask whether recommendation should use current location or a future destination
- offer portion comparison chips when quantity is unclear
- ask whether a future dinner event should be planned
- offer `Apply` or `Dismiss` when async research finds a better calorie estimate

### 2. In-page proactivity

Shown inside LIFF pages without sending a push message.

Current targets:
- `Today`: active draft, pending async updates, weekly recovery overlay
- `Eat`: nearby recommendation entry points, saved places, favorite stores, golden orders
- `Progress`: weekly drift, whether gentle recovery is worth offering

### 3. Event notifications

Only for high-value events:
- background research completed
- unfinished draft left hanging
- tomorrow has a stored plan event
- weekly drift is clearly over target and no response has been given yet

Not allowed in v1:
- background continuous location tracking
- repeated daily nudges
- aggressive push campaigns

## Location Context

`eat_location_context` is not just GPS.

Priority order:
1. explicit location in the current request
2. LIFF geolocation
3. LINE location message
4. saved place
5. inferred default place

Saved places are **progressive setup**, not mandatory onboarding.

When the user asks for nearby recommendations and no place is known, the system should first branch into:
- current area
- where I am going next
- home area
- office area
- manual input

## Store Memory

Nearby recommendation should not start from maps alone.

High-priority memory objects:
- `saved_places`
- `favorite_stores`
- `golden_orders`
- `store_order_signals`

These are used before external search so the system can surface:
- stable stores near office
- reliable home-area choices
- low-risk store and order pairs

## Async Research

All slow lookups must go through `search_jobs`.

Supported job types:
- `nearby_places`
- `menu_precision`
- `brand_lookup`
- `external_food_check`

Flow:
1. return a heuristic answer quickly
2. create a persisted job
3. background worker processes the job
4. if a better result is found, create a `suggested_update`
5. notify the user
6. user chooses `Apply` or `Dismiss`

`Suggested Update` is the default behavior. Silent overwrite is not allowed.

## Background Worker

v1 uses a polling worker in the same FastAPI service.

Rules:
- poll every `BACKGROUND_POLL_INTERVAL_SECONDS`
- cap each batch with `BACKGROUND_JOB_BATCH_SIZE`
- persist status in DB
- keep `job_retry_count`
- keep `last_error`
- fail permanently after 3 retries

This prevents poison jobs from blocking the loop.

## Model Routing

Builder Space model selection is controlled by backend routing.

Default stack:
- router / light classification: `deepseek`
- meal understanding / wording / local QA: `supermind-agent-v1`
- complex research synthesis / normalization: `gpt-5`

Fallback rules:
- layer 3 failure -> layer 2
- layer 2 failure -> deterministic fallback or ask-first

High-tier model failure must never block the main interaction.

## API Surface

New endpoints:
- `POST /api/location/resolve`
- `POST /api/recommendations/nearby`
- `GET /api/search-jobs/{job_id}`
- `POST /api/search-jobs/{job_id}/apply`
- `POST /api/search-jobs/{job_id}/dismiss`
- `GET /api/notifications`
- `POST /api/notifications/{id}/read`
- `POST /api/saved-places`
- `GET /api/saved-places`
- `POST /api/favorite-stores`
- `GET /api/favorite-stores`

Expanded endpoints:
- `POST /api/intake`
- `GET /api/day-summary`
- `GET /api/recommendations`
- `POST /api/plans/compensation`

## Files

Core implementation:
- [routes.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/api/routes.py)
- [proactive.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/proactive.py)
- [background_jobs.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/background_jobs.py)
- [google_places.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/services/google_places.py)
- [models.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/models.py)
- [schemas.py](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend/app/schemas.py)

Related specs:
- [conversation-confirmation-tech-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/conversation-confirmation-tech-spec.md)
- [knowledge-pack-spec.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/knowledge-pack-spec.md)
- [memory-onboarding-v2.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/memory-onboarding-v2.md)
