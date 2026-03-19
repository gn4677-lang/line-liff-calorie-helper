# Builder Space Deploy

## Current Readiness

- Root `Dockerfile`: ready
- Single process runtime: ready
- Single `PORT` entrypoint: ready
- FastAPI health endpoint: ready
- Frontend static build served by backend: ready
- Supabase Postgres and Storage: ready
- LINE webhook path: ready at `/webhooks/line`

## One Important Limitation

This workstation does not currently have Docker installed in the active shell, so I could not do a local `docker build` verification before deployment.

That does not block Builder Space deployment, but it means the first real image build will happen on the platform.

## Recommended Deploy Order

1. Keep using the temporary webhook URL only for smoke testing.
2. Push this repo to a public GitHub repo.
3. Deploy the repo to Builder Space.
4. Wait for the first successful deploy.
5. Replace the temporary LINE webhook URL with the Builder Space URL.
6. Then create the LIFF app and point it to the deployed URL.

## Env Vars To Set In Builder Space

Set these in the deployment environment:

```env
APP_NAME=LINE LIFF Calorie Helper
ENVIRONMENT=production

SUPABASE_DB_URL=postgresql+psycopg://...
SUPABASE_URL=https://suqmwspfbnrrvnsnqegs.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
SUPABASE_STORAGE_BUCKET=meal-attachments
SUPABASE_SIGNED_URL_TTL_SECONDS=3600

AI_PROVIDER=heuristic
AI_BUILDER_BASE_URL=https://space.ai-builders.com/backend/v1
AI_BUILDER_TOKEN=
BUILDERSPACE_CHAT_MODEL=supermind-agent-v1
BUILDERSPACE_VISION_MODEL=supermind-agent-v1
BUILDERSPACE_TRANSCRIPTION_LANG=zh-TW

DEFAULT_DAILY_CALORIE_TARGET=1800
DEFAULT_USER_ID=demo-user
ALLOWLIST_LINE_USER_ID=

LINE_CHANNEL_ID=2009525591
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...
LIFF_CHANNEL_ID=
```

## Recommended v1 Values

- Keep `AI_PROVIDER=heuristic` for the very first deploy.
- Only switch to `AI_PROVIDER=builderspace` after the app is stably reachable.
- Leave `ALLOWLIST_LINE_USER_ID` empty only if you are okay with anyone who finds the webhook or LIFF opening it.
- For self-use v1, set `ALLOWLIST_LINE_USER_ID` after you know your own LINE user ID.

## What To Click In Builder Space

1. Create a new deployment from your GitHub repo.
2. Keep the build context at repo root.
3. Use the root `Dockerfile`.
4. Do not create a second service for frontend.
5. Set the env vars above.
6. Deploy.

## What Success Looks Like

After deploy, these should work:

- `GET /health`
- `GET /api/day-summary`
- `GET /`

And after you swap LINE webhook URL:

- text messages should create intake drafts
- image and audio messages should upload into Supabase Storage

## After Deploy

Update the LINE webhook URL to:

```text
https://your-builder-space-domain/webhooks/line
```

Then verify:

1. `weight 72.4`
2. `雞胸便當加半碗飯`
3. one image message

## Next Step After Backend Deploy

Create the LIFF app under the LINE Login channel and point its endpoint URL to:

```text
https://your-builder-space-domain/
```
