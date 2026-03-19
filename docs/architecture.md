# Architecture

## Layers

1. Channel Layer
   - LINE webhook input
   - LINE content retrieval for image and audio
   - LIFF client pages and LIFF SDK integration
2. Delivery Layer
   - FastAPI routes
   - request and response DTOs
   - auth and LINE signature verification
   - error mapping and response shaping
3. Application Layer
   - intake orchestration
   - clarification orchestration
   - confirmation orchestration
   - recommendation orchestration
   - planning orchestration
   - weight logging orchestration
4. Domain Layer
   - meal draft state machine
   - calorie math
   - follow-up decision rules
   - recommendation eligibility rules
   - reporting bias scoring
   - target-adjustment heuristics
5. Infrastructure Layer
   - Supabase Postgres as primary database target
   - local SQLite fallback for dev and tests
   - Builder Space provider
   - LINE SDK client
   - background jobs and logging hooks

## Runtime shape

- Single FastAPI process serves APIs and the built frontend
- Heuristic provider is the default local/test mode
- Builder Space provider can be enabled with env vars
