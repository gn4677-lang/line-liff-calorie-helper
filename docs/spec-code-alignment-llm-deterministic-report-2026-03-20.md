# Spec-Code Alignment Report: LLM vs Deterministic Split

Date: 2026-03-20

## Scope

This audit answers one question:

What LLM vs deterministic split does the product actually want when the core specs are read together, and how does the current codebase compare?

Reviewed source-of-truth specs:

- `docs/product-spec-v1.md`
- `docs/conversation-confirmation-tech-spec.md`
- `docs/memory-schema-spec.md`
- `docs/memory-onboarding-v2.md`
- `docs/knowledge-pack-spec.md`
- `docs/proactivity-tech-spec.md`
- `docs/video-intake-tech-spec.md`
- `docs/liff-implementable-spec.md`
- `docs/surface-interaction-spec.md`
- `docs/evals-observability-tech-spec.md`
- `docs/architecture.md`

Reviewed historical implementation reports for recent intent drift:

- `docs/builderspace-optimization-report-2026-03-20.md`
- `docs/llm-integration-coverage-report-2026-03-20.md`
- `docs/three-pillar-final-report-2026-03-20.md`
- `docs/three_pillar_assessment.md`

## Bottom Line

The original product intent is not "maximize deterministic behavior".

It is also not "let the LLM own everything".

The product is designed as:

- deterministic system for state, math, thresholds, persistence, and bounded candidate generation
- LLM system for understanding, ambiguity handling, clarification choice, personalization, semantic reranking, and cautious synthesis

In other words:

`deterministic core + LLM policy layer`

That is the product's intended architecture across the specs.

## What The Specs Consistently Say

### 1. LLM should own language and ambiguity

Across the product and memory specs, the LLM is meant to handle:

- ambiguous food understanding
- minimum useful clarification question generation
- semantic normalization
- recommendation and planning rationale
- bounded memory synthesis

This is explicit in:

- `product-spec-v1.md`
- `memory-onboarding-v2.md`
- `memory-schema-spec.md`

### 2. Deterministic logic should own accounting and irreversible control

Across the confirmation, planning, and architecture specs, deterministic code is meant to own:

- calorie arithmetic
- daily and weekly budget math
- confirmation thresholds
- clarification budget
- source precedence in memory
- filtering, counting, and decay
- state machine transitions

This is explicit in:

- `conversation-confirmation-tech-spec.md`
- `memory-onboarding-v2.md`
- `architecture.md`

### 3. Retrieval should be structured before it reaches the model

The knowledge and memory specs repeatedly reject "dump all history into the prompt".

They want:

- compact `knowledge_packet`
- task-specific memory packets
- local-first retrieval
- small bounded context passed into the model

This is explicit in:

- `knowledge-pack-spec.md`
- `memory-schema-spec.md`
- `memory-onboarding-v2.md`

### 4. Recommendation is not supposed to be pure free-form generation

The specs frame recommendation as:

- bounded by kcal and context
- informed by memory and location
- explainable
- surfaced mainly on `Eat`

That means candidate retrieval should stay bounded and explainable, while the LLM can improve ranking, diversity, and rationale.

This is explicit in:

- `product-spec-v1.md`
- `surface-interaction-spec.md`
- `liff-implementable-spec.md`
- `proactivity-tech-spec.md`

### 5. Confirmation is intentionally not LLM-owned

The confirmation spec is very clear:

- four confirmation modes
- evidence-based confidence
- separate confirmation calibration
- clarification budget
- stop gracefully instead of guessing

This design is fundamentally deterministic, though LLM signals can help it.

This is explicit in:

- `conversation-confirmation-tech-spec.md`
- `video-intake-tech-spec.md`

### 6. Proactivity is hybrid, not model-maximal

The proactivity spec explicitly defines a model stack and fallback ladder:

- light routing on cheaper models
- meal understanding and wording on the main model
- complex synthesis on a higher-tier model
- deterministic fallback when higher tiers fail

This is explicit in:

- `proactivity-tech-spec.md`

## Alignment Matrix

| Area | Spec intent | Current code | Alignment | Recommended owner |
| --- | --- | --- | --- | --- |
| Intent routing | cheap classifier or light LLM routing for ambiguous text; user should not feel router internals | chat routing is still regex-first in `routes.py` | partial | more LLM than today |
| Intake understanding | LLM-led, grounded by knowledge packet and small memory packet | `estimate_meal(...)` now receives `knowledge_packet`, `memory_packet`, and `communication_profile` | good | LLM-led |
| Clarification choice | ask one highest-value question; phrasing can be model-assisted | confirmation engine is deterministic but now consumes LLM review hints | good | hybrid |
| Confirmation gate | evidence-based gate, budget, safety, stop reason | deterministic confirmation with optional LLM greenlight and slot targeting | strong | deterministic-led |
| Memory retrieval | task-specific bounded packets | intake/recommendation/planning packets now exist and are wired | good | hybrid |
| Memory write precedence | `user_corrected > user_stated > behavior_inferred > model_hypothesis` | code follows explicit preference writes and bounded model hypotheses | good | deterministic-led |
| Recommendation candidate generation | bounded by kcal, dislikes, stores, location, saved places | still deterministic shortlist generation | good | deterministic-led |
| Recommendation policy | reasons, semantic ordering, diversity, contextual preference | rerank and smart-chip selection now use LLM on bounded shortlist | good | hybrid leaning LLM |
| Nearby recommendation | memory-first then external search then refinement | deterministic discovery plus LLM rerank | good | hybrid |
| Day planning | deterministic budget math, soft rationale/personalization from LLM | base allocations deterministic, final personalization LLM-assisted | good | hybrid |
| Compensation planning | deterministic options, soft recommendation and wording from LLM | option set deterministic, final choice/message LLM-assisted | good | hybrid |
| Video intake | video is richer evidence, not a separate control system | async video refinement uses model estimate plus review, then same confirmation engine | good | hybrid |
| Weekly summary / drift math | deterministic | deterministic | strong | deterministic |
| Observability | separate LLM quality from deterministic failures | API routes mostly covered; LINE webhook path still less instrumented than ideal | partial | deterministic instrumentation |

## Where The Current App Is Still Too Deterministic

These are the main places where the current app is still below the spec's intended LLM usage.

### 1. Chat intent routing

The current LINE chat entry still depends heavily on `_route_text_task(...)` regex routing.

That is weaker than the intent described in:

- `product-spec-v1.md`
- `surface-interaction-spec.md`
- `proactivity-tech-spec.md`

Recommendation:

- keep deterministic fast paths for obvious commands and confirmations
- add an LLM classifier for ambiguous and mixed-intent turns

### 2. Recommendation strategy

The current recommendation system is much healthier than before, but the deepest strategy is still mostly deterministic.

That means the app can rank and filter well, but may still underuse LLM for:

- novelty vs familiarity tradeoff
- comfort vs protein tradeoff under context
- more human-feeling cross-signal prioritization

Recommendation:

- keep bounded deterministic retrieval
- increase LLM weight in shortlist policy and explanation

### 3. Memory read-side relevance

Packets are wired, but retrieval is still mostly score-and-limit style.

The specs imply the LLM should help decide:

- which memories matter for this task now
- which signals are weak or stale
- when a hypothesis should stay soft instead of influencing behavior strongly

Recommendation:

- keep write precedence deterministic
- increase LLM use in packet summarization or task-level relevance selection

### 4. Chat handoff quality

The specs repeatedly say chat should know when to hand off to Today, Eat, or Progress without exposing internal routing logic.

Current code handles this, but still more literally than semantically in the LINE path.

Recommendation:

- use LLM more for handoff phrasing and handoff decision in ambiguous cases

## Where The Current App Should Stay Deterministic

These areas should not be handed over to LLM ownership if the product wants to stay production-grade.

### 1. State machine and persistence

Do not let the model decide:

- whether a draft is duplicated
- whether a log is overwritten
- whether an async update is applied
- whether a correction becomes durable state

### 2. Calorie and overlay math

Do not let the model own:

- daily target math
- weekly drift math
- recovery overlay arithmetic
- body-goal calibration math

The LLM can explain or personalize these. It should not own the ledger.

### 3. Final confirmation thresholds

The LLM can provide:

- confidence delta
- suggested slot
- suggested follow-up
- soft greenlight

But the final auto-record gate should remain deterministic and calibrated.

### 4. Hard filters and external retrieval

Do not let the model invent:

- stores
- distances
- location facts
- brand nutrition facts that were not grounded

This is consistent across knowledge, proactivity, and video specs.

## Recommended Split

If the goal is "best fit to the product's own specs", the recommended split is:

### LLM-led

- meal understanding
- ambiguous multimodal interpretation
- clarification question wording and target suggestion
- ambiguous intent routing
- recommendation rerank on bounded shortlist
- memory synthesis
- plan explanation and personalization

### Hybrid

- confirmation
- memory retrieval
- nearby recommendation
- async refinement review
- surface handoff decisions

### Deterministic-led

- auth and signature verification
- event dedupe and job orchestration
- draft and log state transitions
- calorie arithmetic and overlays
- source precedence in memory
- hard retrieval filters
- observability and degraded-success logging

## Ratio Judgment

If described as a rough operating ratio by decision weight:

- around `60-70%` deterministic ownership for control, state, arithmetic, and guardrails
- around `30-40%` LLM ownership for understanding, personalization, bounded reranking, and synthesis

If described by user-perceived intelligence:

- the user should feel the app is strongly LLM-shaped
- but the invisible control plane should remain mostly deterministic

That is the important distinction.

The current implementation used to be too deterministic.

After the recent LLM wiring work, it is much closer to the intended design, but it still underuses LLM in:

- ambiguous chat routing
- memory read-side relevance
- richer recommendation policy

## Final Answer To The Product Question

The best design for this app is not:

- "make everything deterministic"

and not:

- "let the LLM do all the judgment"

It is:

- let the LLM decide what things mean
- let deterministic code decide what the system is allowed to do

That is the split most consistent with the actual spec set.
