# Launch Checklist

Use this before calling the app public-production ready.

## Runtime And Deploy

- [ ] Confirm canonical public app URL
- [ ] Confirm whether a separate staging/canary URL exists
- [ ] Confirm deployment tier: local-only / self-use canary / staging / public production
- [ ] Confirm same-origin deployment is still the active topology
- [ ] Confirm both `APP_RUNTIME_ROLE=web` and `APP_RUNTIME_ROLE=worker` are deployed
- [ ] Confirm `GET /healthz` returns healthy on the deployed web service
- [ ] Confirm `GET /readyz` returns ready on the deployed web service

## Secrets And Rotation

- [ ] Confirm secret manager / env source of truth
- [ ] Confirm `AI_BUILDER_TOKEN` is set in deployment, not only locally
- [ ] Confirm `LINE_CHANNEL_SECRET` is set in deployment
- [ ] Confirm `LINE_CHANNEL_ACCESS_TOKEN` is set in deployment
- [ ] Confirm `LIFF_CHANNEL_ID` is set in deployment
- [ ] Confirm `SUPABASE_URL` is set in deployment
- [ ] Confirm `SUPABASE_SERVICE_ROLE_KEY` is set in deployment
- [ ] Confirm `GOOGLE_PLACES_API_KEY` is set in deployment
- [ ] Confirm BuilderSpace key rotation is complete if the key was ever exposed
- [ ] Confirm Google Maps key rotation is complete if the key was ever exposed

## BuilderSpace Runtime

- [ ] Confirm `AI_PROVIDER=builderspace`
- [ ] Confirm BuilderSpace router path works from app runtime
- [ ] Confirm BuilderSpace main text estimate path works from app runtime without falling back
- [ ] Confirm observability records `provider_name`, `model_name`, `fallback_reason`, and `llm_usage`
- [ ] Confirm quota/spend expectations for BuilderSpace are documented
- [ ] Confirm alerting exists for BuilderSpace quota/spend if needed

## LINE And LIFF

- [ ] Confirm actual LINE Messaging API webhook URL
- [ ] Confirm webhook URL points to `/webhooks/line`
- [ ] Confirm `/_legacy_inline` is not being used as the primary webhook
- [ ] Confirm actual LIFF endpoint URL
- [ ] Confirm LIFF endpoint points to the deployed web root
- [ ] Confirm allowlist / rollout access policy is correct for the current tier

## Supabase And Storage

- [ ] Confirm DB connectivity from deployed web service
- [ ] Confirm DB connectivity from deployed worker service
- [ ] Confirm attachment uploads succeed into Supabase Storage
- [ ] Confirm signed attachment URLs work

## Product Smoke Tests

- [ ] Send `weight 72.4`
- [ ] Send one plain text meal log in LINE
- [ ] Send one image meal log in LINE
- [ ] Send one audio meal log in LINE
- [ ] Send one video meal log in LINE or LIFF Today
- [ ] Confirm LIFF Today loads
- [ ] Confirm Eat page loads recommendations
- [ ] Confirm nearby recommendation flow works
- [ ] Confirm Progress page loads weekly coaching
- [ ] Confirm async suggested update apply/dismiss works

## Agentic Quality Gates

- [ ] Confirm kill switches exist for chat capture / eat policy / weekly coach
- [ ] Confirm canary traffic is tagged and sliceable
- [ ] Confirm canary transcript review is being performed
- [ ] Confirm capability evals pass for current rollout target
- [ ] Confirm regression evals pass for current rollout target
- [ ] Confirm degraded-success paths remain observable

## Operator Decisions Still To Record

- [ ] Record production base URL in `docs/operator-runtime-registry.md`
- [ ] Record staging/canary base URL in `docs/operator-runtime-registry.md`
- [ ] Record actual LINE webhook URL in `docs/operator-runtime-registry.md`
- [ ] Record actual LIFF URL in `docs/operator-runtime-registry.md`
- [ ] Record BuilderSpace workspace / ownership details in `docs/operator-runtime-registry.md`
- [ ] Record whether `tesseract` is optional or required in production
- [ ] Record whether dual deploy remains deferred or is now required
