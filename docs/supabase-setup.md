# Supabase Setup

## Current Status

- The backend is now Supabase-first.
- SQLAlchemy uses `SUPABASE_DB_URL` for Postgres.
- Attachments upload to Supabase Storage.
- The default storage bucket is `meal-attachments`.
- LINE image/audio downloads and `POST /api/attachments` use the same storage flow.

## Required Env Vars

```env
SUPABASE_DB_URL=postgresql+psycopg://...
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_xxx
SUPABASE_ANON_KEY=ey...
SUPABASE_SERVICE_ROLE_KEY=sb_secret_xxx
SUPABASE_STORAGE_BUCKET=meal-attachments
SUPABASE_SIGNED_URL_TTL_SECONDS=3600
```

## What Each Value Is For

- `SUPABASE_DB_URL`
  - Main Postgres connection used by the backend.
- `SUPABASE_URL`
  - Base URL for Supabase APIs.
- `SUPABASE_PUBLISHABLE_KEY`
  - Safe client-side key for future frontend Supabase usage.
- `SUPABASE_ANON_KEY`
  - Legacy-style anon JWT key kept for compatibility.
- `SUPABASE_SERVICE_ROLE_KEY`
  - Required for server-side Storage operations.
- `SUPABASE_STORAGE_BUCKET`
  - Bucket used for meal attachments.
- `SUPABASE_SIGNED_URL_TTL_SECONDS`
  - Lifetime of generated signed URLs.

## Storage Behavior

- The backend ensures the `meal-attachments` bucket exists.
- Uploaded files are stored under a per-user path:
  - `{line_user_id}/{yyyy}/{mm}/{dd}/{type}/...`
- Draft persistence stores only storage metadata:
  - `storage_provider`
  - `storage_bucket`
  - `storage_path`
  - `mime_type`
  - `size`
  - `uploaded_at`
- Inline base64 is used only during immediate model inference and is not written into the database.

## Validation Steps

1. Start the backend:

```bash
python -m uvicorn backend.app.main:app --reload
```

2. Check the health endpoint:

```bash
curl http://localhost:8000/health
```

3. Upload a test attachment:

```bash
curl -X POST http://localhost:8000/api/attachments ^
  -H "X-Line-User-Id: demo-user" ^
  -F "file=@demo.jpg"
```

4. Confirm you receive:
   - `storage_provider: supabase`
   - `storage_bucket: meal-attachments`
   - a `signed_url`

## Notes

- If `SUPABASE_DB_URL` is missing, the backend falls back to local SQLite.
- If `SUPABASE_SERVICE_ROLE_KEY` is missing, Storage uploads fall back to local disk.
- Because live keys were pasted into chat, rotate them after setup is stable.
