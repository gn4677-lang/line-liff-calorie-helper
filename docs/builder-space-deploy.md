# Builder Space Deploy

This doc reflects the current post-rollout runtime.

Read these first:

- `docs/production-grade-llm-rollout-report-2026-03-20.md`
- `docs/operator-runtime-registry.md`

## Current Readiness

- Root `Dockerfile`: ready
- Same-origin web app: ready
- Role-based runtime split: ready
- FastAPI serves `frontend/dist`: ready
- Liveness/readiness endpoints: ready
- LINE webhook ingress: ready at `/webhooks/line`
- Worker lease/reclaim model: ready

## Runtime Shape

Current intended production shape:

- same-origin web app
- `APP_RUNTIME_ROLE=web` for the HTTP service
- `APP_RUNTIME_ROLE=worker` for the background worker service
- `AI_PROVIDER=builderspace`

This is not the old single-process heuristic-first shape anymore.

## One Important Limitation

This workstation does not currently have Docker installed in the active shell, so local `docker build` verification was not completed here.

That does not block Builder Space deployment, but it means the first real image build may still happen on the platform.

## Recommended Deploy Order

1. Confirm the canonical public app URL you want to use.
2. Deploy the repo to Builder Space as the web service.
3. Deploy the same repo/image again as the worker service if the platform supports multiple long-running services.
4. Wait for the first healthy deploys.
5. Point the LINE webhook URL to the deployed web service.
6. Point the LIFF endpoint URL to the deployed web root.
7. Run smoke checks on LINE and LIFF.

## Env Vars To Set In Builder Space

Set these in the deployment environment:

```env
APP_NAME=LINE LIFF Calorie Helper
ENVIRONMENT=production
APP_BASE_URL=https://your-app-domain
APP_RUNTIME_ROLE=web
CORS_ALLOWED_ORIGINS=https://your-app-domain

SUPABASE_DB_URL=postgresql+psycopg://...
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
SUPABASE_STORAGE_BUCKET=meal-attachments
SUPABASE_SIGNED_URL_TTL_SECONDS=3600

AI_PROVIDER=builderspace
AI_BUILDER_BASE_URL=https://space.ai-builders.com/backend/v1
AI_BUILDER_TOKEN=...
BUILDERSPACE_CHAT_MODEL=supermind-agent-v1
BUILDERSPACE_VISION_MODEL=supermind-agent-v1
BUILDERSPACE_TRANSCRIPTION_LANG=zh-TW

DEFAULT_DAILY_CALORIE_TARGET=1800
DEFAULT_USER_ID=demo-user
ALLOWLIST_LINE_USER_ID=

LINE_CHANNEL_ID=...
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...
LIFF_CHANNEL_ID=...
GOOGLE_PLACES_API_KEY=...
```

For the worker deployment, use the same env set except:

```env
APP_RUNTIME_ROLE=worker
```

## Runtime Notes

- Production readiness now assumes `AI_PROVIDER=builderspace`.
- Do not create a separate frontend service under the current same-origin topology.
- If the platform cannot run a second long-lived service for the worker, record that gap explicitly in `docs/operator-runtime-registry.md`.
- Treat `ALLOWLIST_LINE_USER_ID` as an operator privacy control, not as a substitute for proper auth decisions.

## What Success Looks Like

After deploy, these should work:

- `GET /healthz`
- `GET /readyz`
- `GET /api/day-summary`
- `GET /`

And after you swap LINE webhook and LIFF URLs:

- text messages create intake drafts
- image and audio messages upload into Supabase Storage
- LIFF Today loads
- LIFF Today video upload creates a video intake draft or log
- worker processes async search/video jobs

## After Deploy

Update the LINE webhook URL to:

```text
https://your-builder-space-domain/webhooks/line
```

Then verify:

1. `weight 72.4`
2. one plain text meal message
3. one image message
4. one audio message
5. one LIFF Today video upload

## Notes

- `/webhooks/line` is the production ingress.
- `/webhooks/line/_legacy_inline` is not the primary production path.
- Before public launch, rotate any BuilderSpace or Google Maps credentials that were exposed in chat or local `.env` history.
