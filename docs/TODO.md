# TODO

## P0 Foundations

- [ ] Create repo structure: `frontend/`, `backend/`, `shared/`, `docs/`
- [ ] Scaffold FastAPI backend
- [ ] Scaffold React + Vite LIFF frontend
- [ ] Add root `Dockerfile` for single-process, single-port deployment
- [ ] Add `.env.example` with LINE, LIFF, Supabase, Builder Space variables
- [ ] Add local dev, build, and deploy-readiness scripts
- [ ] Document 5-layer architecture in `docs/architecture.md`

## P1 Contracts and Data

- [ ] Define shared API contracts for intake, clarify, confirm, summary, recommendations, and plans
- [ ] Create Supabase schema for `users`
- [ ] Create Supabase schema for `foods`
- [ ] Create Supabase schema for `preferences`
- [ ] Create Supabase schema for `meal_logs`
- [ ] Create Supabase schema for `meal_drafts`
- [ ] Create Supabase schema for `weight_logs`
- [ ] Create Supabase schema for `plan_events`
- [ ] Create Supabase schema for `reporting_bias`
- [ ] Define attachment metadata shape and storage bucket layout

## P2 Auth and User Binding

- [ ] Implement LIFF token bootstrap flow
- [ ] Verify LIFF token on backend and bind trusted `line_user_id`
- [ ] Add single-user allowlist for v1
- [ ] Implement `GET /api/me`

## P3 LINE + LIFF Shell

- [ ] Implement `POST /webhooks/line` with signature verification
- [ ] Handle LINE text messages
- [ ] Handle LINE image message content retrieval
- [ ] Handle LINE audio message content retrieval
- [ ] Build LIFF shell pages: `Progress`, `Today`, `Eat`
- [ ] Add Today-page quick actions for intake, remaining calories, and recommendations

## P4 AI Provider Adapter

- [ ] Define `AiProvider` interface
- [ ] Implement `BuilderSpaceProvider` for chat completions
- [ ] Implement `BuilderSpaceProvider` for multimodal image analysis
- [ ] Implement `BuilderSpaceProvider` for audio transcription
- [ ] Add model config, retries, timeouts, and provider error mapping

## P5 Intake Core

- [ ] Define canonical `MealDraft` model and state transitions
- [ ] Implement draft lookup policy by `user_id + date + meal_type + active status`
- [ ] Implement modality normalization for text input
- [ ] Implement modality normalization for audio input
- [ ] Implement modality normalization for image input
- [ ] Implement attachment ingestion flow and attachment metadata persistence
- [ ] Build raw input envelope format so text, transcript, and images feed one unified estimator pipeline
- [ ] Implement meal-type inference rules
- [ ] Implement source-mode tracking: text, voice, single-photo, before-after-photo, favorite
- [ ] Implement parsed item extraction from normalized input
- [ ] Implement high-calorie component detection
- [ ] Implement quantity-cue extraction
- [ ] Implement leftover-cue extraction
- [ ] Implement sharing-cue extraction
- [ ] Implement group-meal cue extraction
- [ ] Implement first-pass calorie estimate output
- [ ] Implement estimate range output
- [ ] Implement confidence scoring output
- [ ] Implement missing-slot detection
- [ ] Rank missing slots by calorie impact
- [ ] Implement “estimable / rough-estimable / not-estimable” decision logic
- [ ] Implement precision-mode policy for `quick`
- [ ] Implement precision-mode policy for `standard`
- [ ] Implement precision-mode policy for `fine`
- [ ] Implement follow-up question budget rules by mode
- [ ] Implement follow-up suppression rules when uncertainty is low enough
- [ ] Implement life-language question templates for quantity clarification
- [ ] Implement life-language question templates for leftovers clarification
- [ ] Implement life-language question templates for sharing clarification
- [ ] Implement life-language question templates for group-meal clarification
- [ ] Implement one-question prioritization for quick mode
- [ ] Implement one-to-two-question prioritization for standard mode
- [ ] Implement multi-question sequencing for fine mode
- [ ] Implement draft status transition to `awaiting_clarification`
- [ ] Implement draft status transition to `ready_to_confirm`
- [ ] Implement clarification answer merge logic
- [ ] Implement repeated-clarification loop guard to avoid annoying the user
- [ ] Implement confirm payload generation for LINE reply
- [ ] Implement confirm payload generation for LIFF UI
- [ ] Implement final log write to `meal_logs`
- [ ] Implement post-confirm draft archival
- [ ] Implement daily summary recalculation after confirm
- [ ] Implement edit-after-confirm flow
- [ ] Implement idempotency for duplicate webhook deliveries
- [ ] Implement no-content / failed-download handling for image inputs
- [ ] Implement no-content / failed-download handling for audio inputs
- [ ] Implement fallback when model output is malformed
- [ ] Implement fallback when confidence is too low to auto-estimate
- [ ] Add dedicated handling for leftovers scenario
- [ ] Add dedicated handling for shared-meal scenario
- [ ] Add dedicated handling for group-dish scenario
- [ ] Add dedicated handling for buffet / all-you-can-eat scenario
- [ ] Add dedicated handling for before-after-photo scenario
- [ ] Add structured logging for each intake step
- [ ] Add test fixtures for text-only meals
- [ ] Add test fixtures for photo meals
- [ ] Add test fixtures for voice meals
- [ ] Add test fixtures for leftovers
- [ ] Add test fixtures for sharing
- [ ] Add test fixtures for group dishes
- [ ] Add acceptance test for “30 seconds to complete a normal meal log”

## P6 Day Summary and Progress

- [ ] Implement day-summary calorie math
- [ ] Implement `GET /api/day-summary`
- [ ] Implement `POST /api/weights`
- [ ] Implement 7-day average calculation
- [ ] Implement 14-day trend calculation
- [ ] Render progress page charts and target suggestions

## P7 Recommendation and Planning

- [ ] Implement recommendation eligibility filtering
- [ ] Implement recommendation grouping: `最穩`
- [ ] Implement recommendation grouping: `最方便`
- [ ] Implement recommendation grouping: `想吃爽一點`
- [ ] Implement recommendation grouping: `高蛋白優先`
- [ ] Implement recommendation grouping: `聚餐前適合`
- [ ] Implement recommendation grouping: `爆卡後適合`
- [ ] Implement `GET /api/recommendations`
- [ ] Implement day planner with meal budgets and flex calories
- [ ] Implement compensation / pre-allocation planner
- [ ] Implement `POST /api/plans/day`
- [ ] Implement `POST /api/plans/compensation`

## P8 Memory and Bias

- [ ] Implement foods usage count updates
- [ ] Implement favorite and golden-option promotion rules
- [ ] Implement preferences update rules
- [ ] Implement reporting-bias score updates
- [ ] Feed reporting-bias into clarify intensity rules
- [ ] Feed reporting-bias into target-adjustment suggestions
- [ ] Keep bias user-facing copy soft and coaching-oriented

## P9 Hardening

- [ ] Add replay protection and idempotency checks
- [ ] Add request tracing and structured logs
- [ ] Add API tests
- [ ] Add domain-rule tests
- [ ] Add end-to-end smoke tests
- [ ] Add seed data for favorite and golden foods
- [ ] Validate Builder Space deployment requirements against repo output
