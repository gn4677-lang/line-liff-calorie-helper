# Operator Runtime Registry

Date: 2026-03-21

This file records runtime and deployment facts that a new agent cannot safely infer from code alone.

Use this together with:

- `docs/production-grade-llm-rollout-report-2026-03-20.md`
- `docs/builder-space-deploy.md`
- `docs/line-setup.md`
- `AGENTS.md`

## Verified Current Facts

| Item | Status | Notes |
| --- | --- | --- |
| Remote LLM provider | known | BuilderSpace is the active intended provider. App runtime should only be treated as remote-LLM-enabled when `AI_PROVIDER=builderspace` and `AI_BUILDER_TOKEN` is present. |
| Deployment topology | known | Current implemented topology is same-origin. FastAPI serves `frontend/dist`, and `VITE_API_BASE_URL=''` is the intended production shape. |
| Runtime roles | known | The same image supports `APP_RUNTIME_ROLE=web` and `APP_RUNTIME_ROLE=worker`. |
| Primary webhook ingress | known | `/webhooks/line` is the production ingress and should be treated as `verify -> dedupe -> enqueue -> ACK`. |
| Legacy inline webhook | known | `/webhooks/line/_legacy_inline` exists only as a fallback/debug path. |
| Background work model | known | `inbound_events` and `search_jobs` both use Postgres-backed lease/reclaim semantics. |
| Health endpoints | known | `/healthz` is liveness and `/readyz` is readiness. |
| Recommendation policy outputs | known | Recommendation responses now include `coach_message`, `hero_reason`, and `strategy_label`. |
| Planning copy layer | known | Planning now separates bounded LLM selection/allocation from a dedicated final copywriter pass. |
| Observability eval export | known | `/api/observability/eval-export` exposes webhook ingress/worker and planning-copy slices. |
| Full backend suite status | known | Local verification completed with `91 passed`. |
| Agentic gate status | known | `.\scripts\run_agentic_checks.ps1 -IncludeFrontend` passes locally with remote LLM runtime `ready`. |
| Current web domain in docs | partially known | `docs/line-setup.md` records `https://gn4677-calorie-helper.ai-builders.space/` as the LIFF web app domain. This is recorded from docs and still needs operator confirmation. |

## Unknown Or Not Yet Confirmed

These items still require operator confirmation. New agents should not infer them from the repo.

| Item | Status | What is missing |
| --- | --- | --- |
| Production base URL | unknown | Confirm the canonical public app URL used for real users. |
| Staging/canary base URL | unknown | Confirm whether a separate non-production deploy exists. |
| Actual LINE webhook URL in LINE Developers | unknown | Confirm the URL currently configured in the Messaging API console. |
| Actual LIFF endpoint URL in LINE Developers | unknown | Confirm the URL currently configured for the LIFF app. |
| Deployment tier | unknown | Confirm whether the currently deployed environment is local-only, staging, self-use canary, or public production. |
| Secrets source of truth | unknown | Confirm whether BuilderSpace/Google Maps/LINE/Supabase secrets now live in a platform secret manager, and which platform is authoritative. |
| Key rotation status | unknown | BuilderSpace and Google Maps keys were exposed in chat/local history; confirm whether they have already been rotated. |
| BuilderSpace workspace/ownership details | unknown | Confirm which workspace/project owns the running deployment and quotas. |
| BuilderSpace quota/spend expectations | unknown | Confirm usage/spend limits and whether alerts exist. |
| Tesseract production policy | unknown | Confirm whether `tesseract` should remain optional or be installed in production for better OCR/video refinement. |
| Phase C dual deploy decision | unknown | Confirm whether dual deploy remains deferred or is now an active architectural requirement. |

## Immediate Operator Checklist

When someone takes over this app, fill these fields first:

1. Public app URL:
   - value: `UNKNOWN`
2. Staging app URL:
   - value: `UNKNOWN`
3. LINE webhook URL in console:
   - value: `UNKNOWN`
4. LIFF endpoint URL in console:
   - value: `UNKNOWN`
5. Deployment tier:
   - value: `UNKNOWN`
6. Secret manager / env source of truth:
   - value: `UNKNOWN`
7. BuilderSpace key rotated after exposure:
   - value: `UNKNOWN`
8. Google Maps key rotated after exposure:
   - value: `UNKNOWN`
9. Tesseract required in production:
   - value: `UNKNOWN`
10. Dual deploy now required:
   - value: `UNKNOWN`

## Current Source Files To Check

- Runtime/config:
  - `backend/app/config.py`
  - `backend/app/main.py`
  - `backend/app/worker.py`
- Webhook/worker control plane:
  - `backend/app/api/routes.py`
  - `backend/app/services/background_jobs.py`
- `backend/app/services/inbound_events.py`
- LLM rollout:
  - `backend/app/services/llm_support.py`
  - `backend/app/services/planning.py`
  - `backend/app/services/recommendations.py`
  - `docs/production-grade-llm-rollout-report-2026-03-20.md`
  - `docs/phase-c-dual-deploy-analysis-2026-03-21.md`

## Notes

- This file intentionally does not store any secret values.
- If an operator confirms one of the unknown items above, update this file instead of leaving that information only in chat history.
