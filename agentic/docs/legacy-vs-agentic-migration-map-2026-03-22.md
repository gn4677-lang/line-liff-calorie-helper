# Legacy vs Agentic Migration Map (2026-03-22)

This repo currently contains two application trees:

- legacy root app
- new agentic mainline

They coexist on purpose during the rewrite and canary period.

## Current Repo Layout

### Legacy root app

These paths are the pre-rewrite system and are intentionally still present:

- [backend](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/backend)
- [frontend](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/frontend)
- [docs](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs)

Role of the legacy root app:
- rollback target
- implementation reference
- shared deterministic logic source
- legacy production behavior reference

The legacy root app is frozen as the old system shape.
It should not be treated as the place for new product capabilities.

### Agentic mainline

These paths are the new rewrite:

- [agentic/backend](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/agentic/backend)
- [agentic/frontend](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/agentic/frontend)
- [agentic/docs](/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/agentic/docs)

Role of the agentic tree:
- new Agent Core
- new LIFF shell
- new worker/proactive runtime
- new rollout, observability, and shadow/canary logic

All new product evolution should happen under `agentic/`.

## Git Preservation

In addition to keeping the legacy files in the workspace, the old system is also preserved in git:

- local tag: `pre-agentic-rewrite-2026-03-21`
- local branch: `codex/agentic-rewrite`

Meaning:
- the old code is still physically present in the repo
- there is also a git checkpoint for the pre-rewrite state

## Migration Intent

The intended operating model is:

1. Keep root legacy app intact during rewrite and canary
2. Build new behavior in `agentic/`
3. Run same-origin, shared-DB canary against the agentic path
4. Keep legacy available for rollback during rollout
5. Retire legacy from the mainline only after cutover is complete

## Practical Reading Guide

If you are trying to answer "where should I edit this?":

- If the change is new assistant behavior, new rollout logic, or new LIFF behavior:
  - edit `agentic/`
- If the change is only a legacy rollback fix, reference lookup, or shared deterministic adapter:
  - inspect root `backend/` or `frontend/`

If you are trying to answer "which one is the future product line?":

- the answer is `agentic/`

If you are trying to answer "where is the old system?":

- the answer is the repo root `backend/` and `frontend/`

## Shared Components Caveat

Some deterministic logic is still intentionally shared or mirrored from the legacy system.
That does not make the root app the future architecture.
The future architecture remains the agentic tree, with legacy kept only as:

- rollback support
- compatibility reference
- deterministic logic source where reuse is safer than re-deriving behavior

## Status Summary

Current status on 2026-03-22:

- root legacy app: preserved
- agentic tree: active mainline for rewrite
- rollout target: canary-ready first, not public-wide by default

