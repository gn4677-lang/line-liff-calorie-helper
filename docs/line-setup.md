# LINE Setup

Read these first:

- `docs/operator-runtime-registry.md`
- `docs/builder-space-deploy.md`

## What You Need In LINE Developers

Create:

- a `Messaging API` channel
- a `LIFF` app

Collect these values:

- `LINE_CHANNEL_ID`
- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LIFF_CHANNEL_ID`
- your own LINE `userId` if you want to keep early rollout access allowlisted

## Required `.env` Values

```env
APP_BASE_URL=https://your-app-domain
APP_RUNTIME_ROLE=web
CORS_ALLOWED_ORIGINS=https://your-app-domain

LINE_CHANNEL_ID=...
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...
LIFF_CHANNEL_ID=...
ALLOWLIST_LINE_USER_ID=your-line-user-id

SUPABASE_DB_URL=postgresql+psycopg://...
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_xxx
SUPABASE_ANON_KEY=ey...
SUPABASE_SERVICE_ROLE_KEY=sb_secret_xxx
SUPABASE_STORAGE_BUCKET=meal-attachments

AI_PROVIDER=builderspace
AI_BUILDER_TOKEN=...
BUILDERSPACE_CHAT_MODEL=supermind-agent-v1
BUILDERSPACE_VISION_MODEL=supermind-agent-v1
BUILDERSPACE_TRANSCRIPTION_LANG=zh-TW
GOOGLE_PLACES_API_KEY=...
```

## Local Run

Backend:

```bash
python -m uvicorn backend.app.main:app --reload
```

Frontend:

```bash
cd frontend
npm run dev
```

## Expose The Backend To LINE

Use ngrok or another tunnel:

```bash
ngrok http 8000
```

Set the Messaging API webhook URL to:

```text
https://your-public-url/webhooks/line
```

Treat `/webhooks/line` as the production ingress.
`/webhooks/line/_legacy_inline` is only a fallback/debug route and should not be used as the main webhook URL.

## LIFF URL

Under the current same-origin deployment model, the LIFF endpoint should point to the deployed web root:

```text
https://your-public-url/
```

## Current LIFF Endpoint Recorded In Repo Docs

The repo currently records this Builder Space web app domain:

- `https://gn4677-calorie-helper.ai-builders.space/`

This value is recorded from local docs and should be re-confirmed against the active deployment and LINE console before making production claims.

## Current Attachment Flow

- LINE image/audio content is fetched by the backend.
- The backend uploads that binary to Supabase Storage.
- The default bucket is `meal-attachments`.
- Drafts store storage metadata, not local file paths.

## Quick Checks

1. Send `weight 72.4`.
2. Send a plain text meal description.
3. Send an image.
4. Send an audio message.
5. Check that the backend replies without signature errors.
6. Check Supabase Storage for uploaded objects.
7. Check `GET /healthz` and `GET /readyz`.

## Notes

- `ALLOWLIST_LINE_USER_ID` is the simplest way to keep an early rollout private.
- `LINE_CHANNEL_ID` is not the same thing as `LIFF_CHANNEL_ID`.
- If webhook verification fails, check `LINE_CHANNEL_SECRET`.
- If replies fail, check `LINE_CHANNEL_ACCESS_TOKEN`.
- If image/audio uploads fail, check `SUPABASE_SERVICE_ROLE_KEY`.
- For current operator-known and operator-unknown runtime facts, also read `docs/operator-runtime-registry.md`.
