# Video Intake Tech Spec

Implementation reference for short meal-video logging, video evidence extraction, async refinement, and how video intake plugs into the existing `intake -> clarify -> confirm -> suggested update` pipeline.

## Goal

Add a `video` intake mode that helps the system estimate calories from short meal clips without inventing a separate logging product.

The design principle is:

- treat video as a richer evidence source, not a separate workflow
- keep first response fast
- use background refinement for slow steps
- reuse the existing confirmation engine
- never silently overwrite a confirmed log

## Product Position

`video intake` is meant for cases where:

- a single photo is not enough
- the user wants to pan across multiple dishes
- portion size is easier to show than describe
- the user wants to talk while filming
- the meal is shared, buffet-style, or visually complex

It is not a continuous tracking system and does not try to infer every bite from long videos.

v1 assumes:

- short clips only
- one meal event at a time
- optional spoken narration by the user
- optional later refinement through async research

## Supported Input Sources

### LINE video message

The user sends a short video clip in the chat.

Backend flow:

- receive webhook event
- fetch LINE content by `messageId`
- upload the raw video to Supabase Storage
- create an intake draft with `source_mode = "video"`

### LIFF video upload

The user uploads a short clip from the `Today` or `Eat` flow.

Backend flow:

- upload video through the existing attachment upload path
- create an intake draft with the uploaded attachment metadata
- optionally include user text such as:
  - `this is what I just ate`
  - `I only ate half`
  - `shared between two people`

## UX Flow

### Fast path

1. User sends a short meal video.
2. System stores the attachment and creates a draft immediately.
3. System returns a quick estimate in about 2 seconds using a heuristic or partial multimodal pass.
4. The draft enters one of the existing confirmation modes:
   - `auto_recordable`
   - `needs_clarification`
   - `needs_confirmation`
   - `correction_preview`

### Slow path

If the clip needs more work, the system creates an async refinement job.

Examples:

- extract clearer keyframes
- transcribe spoken narration
- run OCR on packaging or menu boards
- detect branded menu items
- reconcile the clip with known brand or restaurant information

When the async pass finds a better estimate, the system creates a `suggested_update`. The user can `Apply` or `Dismiss`.

## Core Design

### Video is an evidence source, not a special confirmation system

Video intake still uses the existing confirmation engine. The system does not invent a separate confidence scale just because the source is video.

Video affects:

- source quality
- evidence richness
- ability to resolve portion and multiple items
- chance of using comparison or clarification less often

Video does not bypass:

- confirmation calibration
- clarification budget
- suggested update safety rules

### Two-stage understanding

#### Stage 1: quick estimate

Used for fast response.

Inputs:

- lightweight metadata
- optional user text
- a small number of representative frames
- optional already-available audio transcript

Outputs:

- rough parsed items
- rough portion signals
- rough sharing or leftover clues
- first-pass calorie range
- evidence slots for the confirmation engine

#### Stage 2: async refinement

Used when the clip is complex or brand or menu precision matters.

Inputs:

- full stored video
- extracted keyframes
- transcript
- OCR text
- store or brand hints
- local knowledge pack
- optional external research

Outputs:

- refined parsed items
- tighter calorie range
- store or menu match
- `suggested_update`

## Evidence Model

Video analysis should map into the existing evidence-slot structure, not invent a parallel format.

Important evidence extracted from video:

- `identified_items`
- `portion_signal`
- `rice_portion`
- `leftover_signal`
- `sharing_signal`
- `high_calorie_modifiers`
- `drink_or_dessert_presence`
- `ambiguity_flags`
- `comparison_candidates`

Video-specific signals:

- `keyframe_refs`
- `transcript`
- `ocr_hits`
- `scene_sequence`
  - buffet sweep
  - tray scan
  - before or after sequence
  - drink close-up
- `brand_hints`
- `visual_portion_anchor_hits`

These video-specific signals should live in draft or log metadata, while the normalized evidence continues to feed the confirmation engine.

## Confirmation and Clarification Behavior

Video intake still ends in one of the standard confirmation modes.

### Auto-recordable

Use when:

- the video clearly shows the main items
- portion clues are strong
- there are no unresolved high-impact slots
- `estimation_confidence >= 0.78`

Behavior:

- write the meal log immediately
- still reply with estimate, range, uncertainties, and edit hint

### Needs clarification

Use when:

- the video is rich but key portion or sharing details are still unclear
- there is at least one unresolved high-impact slot

Typical follow-up questions:

- `was this just for you, or shared with someone else?`
- `about how much of the rice did you finish?`
- `did you finish the drink shown in the clip?`

### Needs confirmation

Use when:

- the quick pass is usable
- but async refinement is still pending or the clip remains somewhat ambiguous

Behavior:

- stop asking once the budget is exhausted
- say the system is currently using a generic portion estimate

### Correction preview

Use when:

- the video is sent as a correction to a recent meal
- for example: `that last meal was actually only half`

Behavior:

- build a recalculated preview
- do not create a duplicate meal log
- confirm before overwriting

## Async Refinement

Video intake should use the same persisted-job pattern as the current proactive research system.

Recommended job types:

- `video_extract`
- `video_transcript`
- `video_precision`
- `video_brand_lookup`

Suggested v1 simplification:

- keep the DB `job_type` under existing `search_jobs`
- reuse `search_jobs` instead of building a second job framework

Flow:

1. save the raw clip
2. create draft
3. return quick estimate
4. create async job if refinement is worth it
5. worker processes the job
6. store refined result
7. if meaningfully different, create `suggested_update`
8. notify user once

Rules:

- no silent overwrite
- max retry count stays capped
- keep `last_error`
- retry only for transient failures

## Storage and Data Model

### Storage

Video attachments should use the same Supabase Storage strategy already used for other media.

Recommended metadata:

- `storage_bucket`
- `storage_path`
- `mime_type`
- `size_bytes`
- `duration_seconds`
- `width`
- `height`
- `thumbnail_path`

### Draft metadata additions

Store in `meal_drafts.draft_context`:

- `video_analysis_status`
- `video_duration_seconds`
- `keyframe_refs`
- `transcript`
- `ocr_hits`
- `brand_hints`
- `scene_sequence`
- `async_refinement_job_id`
- `video_refinement_pending`
- `video_source_label`
  - `line_video`
  - `liff_upload`

### Confirmed log metadata additions

Store in `meal_logs.metadata`:

- `video_used`
- `video_duration_seconds`
- `keyframe_refs`
- `transcript`
- `ocr_hits`
- `brand_hints`
- `async_update_reason`
- `async_update_sources`

## API Design

v1 should avoid creating a completely separate intake stack.

### Reuse existing intake API

Preferred path:

- upload the file through the existing attachment flow
- call `POST /api/intake` with:
  - `source_mode = "video"`
  - attachment metadata
  - optional text

This keeps the flow aligned with current intake logic.

### Optional helper route

If the frontend needs a clearer entry point, add:

- `POST /api/intake/video`

But this should still internally call the same intake service and return the same `DraftResponse`.

### Existing route behavior to extend

- `POST /api/intake`
  - accept `source_mode = "video"`
  - accept video attachment refs
  - may return `search_job_id`
- `POST /api/intake/{draft_id}/clarify`
  - follow-up answers after video analysis
- `POST /api/intake/{draft_id}/confirm`
  - confirm the quick estimate or a correction preview
- `GET /api/search-jobs/{job_id}`
  - track async video refinement

## Model Routing

Video should follow the same layered routing strategy already used elsewhere.

### Layer 1

Use for:

- attachment classification
- routing
- frame count policy
- cheap extraction guards

### Layer 2

Use for:

- keyframe understanding
- first-pass meal understanding
- clarification wording
- video-based portion interpretation

### Layer 3

Use for:

- hard brand or menu reconciliation
- multi-dish complex clip refinement
- research-backed precision pass

Fallback rule:

- if the higher layer fails or times out, return the lower-layer estimate
- never block the chat flow waiting for a frontier pass

## Knowledge Pack Integration

Video refinement should use the same local-first knowledge policy already defined for nutrition QA and suggested updates.

Order:

1. local knowledge pack
2. known brand cards
3. portion anchors
4. favorite stores or golden orders
5. targeted external research only when needed

Video-specific knowledge that will matter later:

- buffet heuristics
- hotpot and grill scene interpretation
- convenience-store packaging cues
- bento compartment anchors
- hand, chopsticks, cup, and bowl size anchors

## Execution TODO

### Phase 0: plumbing decision and boundary lock

- keep video on the existing `POST /api/intake` contract
- optionally add `POST /api/intake/video` as a thin wrapper only
- reuse `search_jobs` instead of creating a second worker table
- store video-specific fields inside draft or log metadata first
- do not block the initial response on full video analysis

### Phase 1: attachment classification and request normalization

- classify `video/*` uploads as `type = "video"`
- support video in both:
  - LINE content retrieval
  - LIFF upload flow
- normalize a video request into:
  - `source_mode = "video"`
  - attachment refs
  - `video_source_label`
  - `video_analysis_status = "pending_refinement"`
- make sure the request still passes through the same provider and confirmation engine

### Phase 2: draft and log metadata

- extend `meal_drafts.draft_context` to carry:
  - `video_analysis_status`
  - `video_duration_seconds`
  - `video_dimensions`
  - `keyframe_refs`
  - `transcript`
  - `ocr_hits`
  - `brand_hints`
  - `scene_sequence`
  - `video_refinement_pending`
  - `video_source_label`
- extend `meal_logs.metadata` to carry:
  - `video_used`
  - `video_analysis_status`
  - `video_duration_seconds`
  - `keyframe_refs`
  - `transcript`
  - `ocr_hits`
  - `brand_hints`
  - async update fields after refinement is applied

### Phase 3: quick estimate path

- allow `source_mode = "video"` in the same intake path as text, image, and audio
- pass the stored attachment refs into the provider
- treat video as a higher-information source, but still evidence-based
- keep first response under normal chat latency budget
- continue using:
  - `auto_recordable`
  - `needs_clarification`
  - `needs_confirmation`
  - `correction_preview`

### Phase 4: async video refinement skeleton

- add video-related job types under the existing `search_jobs` framework
- build request payloads for:
  - draft-level refinement
  - confirmed-log refinement
- implement worker handlers that:
  - complete successfully
  - store result payload
  - do not silently rewrite logs
- only create `suggested_update` when later refinement becomes meaningfully better

### Phase 5: route integration

- add `POST /api/intake/video`
- update generic `POST /api/intake` to recognize video attachments
- update LINE webhook to accept video messages
- after draft creation:
  - queue a draft-level refinement job only if the meal is not auto-recorded yet
- after confirm:
  - queue a log-level refinement job that can later produce a `suggested_update`

### Phase 6: frontend and bot surface

- LIFF:
  - video upload entry
  - upload progress
  - pending refinement state
  - async update card
- LINE:
  - normal reply after video submission
  - clarification wording for shared meals or portion uncertainty
  - one notification when a meaningful video refinement finishes

### Phase 7: knowledge integration

- connect video refinement to:
  - local food catalog
  - brand cards
  - portion anchors
  - golden orders
- add future knowledge assets for:
  - buffet sweeps
  - grill and hotpot table scans
  - bento compartments
  - packaged convenience-store meals
  - hand, bowl, cup, and chopsticks size anchors

## Test Plan

- LINE video message creates a draft with `source_mode = "video"`.
- LIFF video upload creates the same kind of draft.
- Quick estimate returns within the normal chat budget and does not wait for full refinement.
- Video evidence maps into the same confirmation engine used by text, image, and audio.
- Complex video can create an async refinement job without blocking the user.
- Async refinement produces a `suggested_update` instead of silently overwriting the log.
- `Apply` updates the original log and stores async update metadata.
- `Dismiss` prevents repeat notification for the same refinement.
- Shared meal clips trigger clarification around sharing ratio instead of overconfident logging.
- Before or after or buffet-like clips can still fall back to `needs_confirmation` if evidence is too weak.

## Non-goals

v1 does not try to do the following:

- continuous eating tracking
- long-form video understanding
- frame-by-frame consumption reconstruction
- passive background recording
- perfect nutrition analysis from visuals alone

## Files Likely Involved

- `backend/app/api/routes.py`
- `backend/app/services/intake.py`
- `backend/app/services/confirmation.py`
- `backend/app/services/background_jobs.py`
- `backend/app/services/storage.py`
- `backend/app/services/proactive.py`
- `backend/app/providers/builderspace.py`
- `backend/app/providers/heuristic.py`
- `frontend/src/App.tsx`
- `docs/conversation-confirmation-tech-spec.md`
- `docs/proactivity-tech-spec.md`
- `docs/knowledge-pack-spec.md`
