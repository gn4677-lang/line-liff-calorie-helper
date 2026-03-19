# LINE Setup

## What You Need In LINE Developers

Create:

- a `Messaging API` channel
- a `LIFF` app

Collect these values:

- `LINE_CHANNEL_ID`
- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LIFF_CHANNEL_ID`
- your own LINE `userId` if you want to keep v1 allowlisted

## Required `.env` Values

```env
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

AI_PROVIDER=heuristic
```

If you want Builder Space for image/audio understanding:

```env
AI_PROVIDER=builderspace
AI_BUILDER_TOKEN=...
BUILDERSPACE_CHAT_MODEL=supermind-agent-v1
BUILDERSPACE_VISION_MODEL=supermind-agent-v1
BUILDERSPACE_TRANSCRIPTION_LANG=zh-TW
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

## LIFF URL

Use either:

- your frontend dev URL
- or the backend-served frontend root after `npm run build`

Examples:

- `https://your-frontend-domain/`
- `https://your-public-url/`

## Current Attachment Flow

- LINE image/audio content is fetched by the backend.
- The backend uploads that binary to Supabase Storage.
- The default bucket is `meal-attachments`.
- Drafts store storage metadata, not local file paths.

## Quick Checks

1. Send `weight 72.4` in LINE.
2. Send a plain text meal description.
3. Send an image.
4. Confirm the backend replies without signature errors.
5. Check Supabase Storage for uploaded objects.

## Notes

- `ALLOWLIST_LINE_USER_ID` is the simplest way to keep v1 private.
- `LINE_CHANNEL_ID` is not the same thing as `LIFF_CHANNEL_ID`.
- If webhook verification fails, check `LINE_CHANNEL_SECRET`.
- If replies fail, check `LINE_CHANNEL_ACCESS_TOKEN`.
- If image/audio uploads fail, check `SUPABASE_SERVICE_ROLE_KEY`.
