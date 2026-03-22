# Launch Checklist Status

Date: 2026-03-21

This is the repo-backed status inventory for [launch-checklist.md](C:/Users/exsaf/Documents/Playground/apps/line-liff-calorie-helper/docs/launch-checklist.md).

Status labels used here:

- `locally verified`: confirmed from repo plus a local runtime or test execution
- `repo-confirmed`: confirmed from code/docs/tests, but not from a live deployed environment
- `partial`: there is repo evidence or a recorded candidate value, but operator confirmation is still required
- `unknown`: must be confirmed by the operator outside the repo

## Runtime And Deploy

| Checklist item | Status | Notes |
| --- | --- | --- |
| Confirm canonical public app URL | unknown | Repo does not record an operator-confirmed canonical production URL. |
| Confirm whether a separate staging/canary URL exists | unknown | No operator-confirmed staging/canary URL is recorded. |
| Confirm deployment tier: local-only / self-use canary / staging / public production | unknown | `docs/operator-runtime-registry.md` explicitly leaves this open. |
| Confirm same-origin deployment is still the active topology | repo-confirmed | Documented in `docs/builder-space-deploy.md` and `docs/production-grade-llm-rollout-report-2026-03-20.md`. |
| Confirm both `APP_RUNTIME_ROLE=web` and `APP_RUNTIME_ROLE=worker` are deployed | unknown | Code supports both roles, but actual deploy status is operator-owned. |
| Confirm `GET /healthz` returns healthy on the deployed web service | repo-confirmed | Route exists and is test-covered locally; deployed endpoint still needs operator confirmation. |
| Confirm `GET /readyz` returns ready on the deployed web service | repo-confirmed | Route exists and is test-covered locally; deployed readiness still needs operator confirmation. |

## Secrets And Rotation

| Checklist item | Status | Notes |
| --- | --- | --- |
| Confirm secret manager / env source of truth | unknown | Explicitly still open in `docs/operator-runtime-registry.md`. |
| Confirm `AI_BUILDER_TOKEN` is set in deployment, not only locally | unknown | Local runtime has a token; deploy-side source of truth is not recorded. |
| Confirm `LINE_CHANNEL_SECRET` is set in deployment | unknown | Required by production config, but deploy-side value is not operator-confirmed. |
| Confirm `LINE_CHANNEL_ACCESS_TOKEN` is set in deployment | unknown | Required by production config, but deploy-side value is not operator-confirmed. |
| Confirm `LIFF_CHANNEL_ID` is set in deployment | unknown | Required by production config, but deploy-side value is not operator-confirmed. |
| Confirm `SUPABASE_URL` is set in deployment | unknown | Required by production config, but deploy-side value is not operator-confirmed. |
| Confirm `SUPABASE_SERVICE_ROLE_KEY` is set in deployment | unknown | Required by production config, but deploy-side value is not operator-confirmed. |
| Confirm `GOOGLE_PLACES_API_KEY` is set in deployment | unknown | Repo expects it; deploy-side presence is not recorded. |
| Confirm BuilderSpace key rotation is complete if the key was ever exposed | unknown | Docs explicitly require out-of-band confirmation before public launch. |
| Confirm Google Maps key rotation is complete if the key was ever exposed | unknown | Docs explicitly require out-of-band confirmation before public launch. |

## BuilderSpace Runtime

| Checklist item | Status | Notes |
| --- | --- | --- |
| Confirm `AI_PROVIDER=builderspace` | locally verified | Verified from local runtime config and enforced by production config checks. |
| Confirm BuilderSpace router path works from app runtime | locally verified | `scripts/check_builderspace_runtime.py --mode probe` succeeded on 2026-03-21 with `deepseek`. |
| Confirm BuilderSpace main text estimate path works from app runtime without falling back | locally verified | `scripts/check_builderspace_runtime.py --mode probe` succeeded on 2026-03-21 with `supermind-agent-v1`; `estimate_path_sample.route_target=builderspace`, `route_reason=ungrounded_text`. |
| Confirm observability records `provider_name`, `model_name`, `fallback_reason`, and `llm_usage` | repo-confirmed | Route summaries and observability console already expose these fields; tests cover trace/eval export paths. |
| Confirm quota/spend expectations for BuilderSpace are documented | unknown | `docs/operator-runtime-registry.md` still marks quota/spend expectations as unknown. |
| Confirm alerting exists for BuilderSpace quota/spend if needed | unknown | No operator-confirmed spend alert policy is recorded. |

## LINE And LIFF

| Checklist item | Status | Notes |
| --- | --- | --- |
| Confirm actual LINE Messaging API webhook URL | unknown | Must be read from LINE Developers console. |
| Confirm webhook URL points to `/webhooks/line` | repo-confirmed | Docs and code agree this is the production ingress. Console value still needs operator confirmation. |
| Confirm `/_legacy_inline` is not being used as the primary webhook | repo-confirmed | Code and docs mark it as fallback/debug only; actual console value still needs operator confirmation. |
| Confirm actual LIFF endpoint URL | partial | Repo records a candidate web domain and LIFF share URL, but console-configured endpoint remains unconfirmed. |
| Confirm LIFF endpoint points to the deployed web root | repo-confirmed | This is the intended same-origin model in `docs/line-setup.md`; actual console value still needs operator confirmation. |
| Confirm allowlist / rollout access policy is correct for the current tier | partial | `ALLOWLIST_LINE_USER_ID` exists and docs describe it, but the current rollout tier and allowlist policy are not operator-confirmed. |

## Supabase And Storage

| Checklist item | Status | Notes |
| --- | --- | --- |
| Confirm DB connectivity from deployed web service | unknown | Local/test coverage exists, but deployed connectivity is not operator-confirmed. |
| Confirm DB connectivity from deployed worker service | unknown | Code supports worker role, but actual deployed connectivity is not operator-confirmed. |
| Confirm attachment uploads succeed into Supabase Storage | partial | Upload flow is implemented and rollout docs say it works post-rollout; deployed smoke confirmation is still required. |
| Confirm signed attachment URLs work | partial | Signed URL support exists in repo, but deployed runtime verification is still required. |

## Product Smoke Tests

| Checklist item | Status | Notes |
| --- | --- | --- |
| Send `weight 72.4` | unknown | Must be verified in live LINE or deployed app. |
| Send one plain text meal log in LINE | unknown | Must be verified in live LINE or deployed app. |
| Send one image meal log in LINE | unknown | Must be verified in live LINE or deployed app. |
| Send one audio meal log in LINE | unknown | Must be verified in live LINE or deployed app. |
| Send one video meal log in LINE or LIFF Today | unknown | Must be verified in live LINE or deployed app. |
| Confirm LIFF Today loads | unknown | Must be checked against the deployed web root / LIFF app. |
| Confirm Eat page loads recommendations | unknown | Must be checked against the deployed web root / LIFF app. |
| Confirm nearby recommendation flow works | unknown | Must be checked against the deployed web root / LIFF app. |
| Confirm Progress page loads weekly coaching | unknown | Must be checked against the deployed web root / LIFF app. |
| Confirm async suggested update apply/dismiss works | unknown | Must be checked against the deployed app and worker. |

## Agentic Quality Gates

| Checklist item | Status | Notes |
| --- | --- | --- |
| Confirm kill switches exist for chat capture / eat policy / weekly coach | repo-confirmed | Config flags exist and are wired through routes. |
| Confirm canary traffic is tagged and sliceable | repo-confirmed | `is_canary` and `traffic_class` are in models, observability filters, and eval export. |
| Confirm canary transcript review is being performed | unknown | This is a process requirement, not something the repo can confirm. |
| Confirm capability evals pass for current rollout target | partial | Local agentic suites pass, but the actual rollout target is still unknown. |
| Confirm regression evals pass for current rollout target | partial | Local agentic suites pass, but the actual rollout target is still unknown. |
| Confirm degraded-success paths remain observable | repo-confirmed | Observability docs and tests cover fallback/degraded-success markers and summaries. |

## Operator Decisions Still To Record

| Checklist item | Status | Notes |
| --- | --- | --- |
| Record production base URL in `docs/operator-runtime-registry.md` | unknown | Still missing. |
| Record staging/canary base URL in `docs/operator-runtime-registry.md` | unknown | Still missing. |
| Record actual LINE webhook URL in `docs/operator-runtime-registry.md` | unknown | Still missing. |
| Record actual LIFF URL in `docs/operator-runtime-registry.md` | unknown | Still missing. |
| Record BuilderSpace workspace / ownership details in `docs/operator-runtime-registry.md` | unknown | Still missing. |
| Record whether `tesseract` is optional or required in production | unknown | Still missing. |
| Record whether dual deploy remains deferred or is now required | unknown | Still missing. |

## Most Important Known vs Unknown Summary

### Already solid from repo or local runtime

- BuilderSpace is the intended remote provider.
- Same-origin deployment is the intended production topology.
- `/webhooks/line` is the primary ingress.
- `/_legacy_inline` is fallback/debug only.
- `healthz` and `readyz` exist and are test-covered.
- Loop kill switches exist.
- Canary tagging and observability slicing exist.
- Local BuilderSpace runtime probe now succeeds for:
  - `router -> deepseek`
  - `text estimate -> supermind-agent-v1`

### Still blocked on operator confirmation

- real production URL
- whether a staging/canary deploy exists
- actual LINE webhook URL in console
- actual LIFF endpoint URL in console
- deployment tier
- deploy-time secret source of truth
- key rotation status
- BuilderSpace quota/spend policy
- deployed DB/storage/smoke-test status
- whether canary transcript review is actually being performed
