# LINE LIFF Calorie Helper

AI 減脂操作系統的可跑 MVP。

目前這個 repo 直接提供：

- FastAPI backend
- React + Vite frontend
- 單體部署模式，backend 直接提供 build 後的 frontend
- intake / clarify / confirm / summary / recommendations / weight logging / basic planning API
- LINE webhook 骨架
- Builder Space provider 接口
- 本地 heuristic provider，方便在沒有模型金鑰時也能直接開發與測試
- Supabase-first database configuration，沒有 Supabase 連線時才退回本地 SQLite

## Repo Layout

- `backend/`: FastAPI, domain logic, persistence, tests
- `frontend/`: Vite React cockpit
- `docs/product-spec-v1.md`: 你的原始 spec snapshot
- `docs/architecture.md`: 5-layer 架構說明
- `TODO.md`: implementation checklist

## Quick Start

### 1. Install backend dependencies

```bash
python -m pip install -r backend/requirements.txt
```

### 2. Install frontend dependencies

```bash
cd frontend
npm install
```

### 3. Run backend

```bash
python -m uvicorn backend.app.main:app --reload
```

預設跑在 `http://localhost:8000`。

### 4. Run frontend dev server

```bash
cd frontend
npm run dev
```

預設跑在 `http://localhost:5173`，Vite 已經 proxy `/api`、`/health`、`/webhooks` 到 backend。

## Environment

複製 `.env.example` 成 `.env`，再填你要的值。

重要欄位：

- `SUPABASE_DB_URL`
  - Supabase Postgres pooler / session 連線字串
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `AI_PROVIDER=heuristic`
  - 本地測試預設值
- `AI_PROVIDER=builderspace`
  - 啟用 Builder Space provider
- `AI_BUILDER_TOKEN`
- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LIFF_CHANNEL_ID`
- `ALLOWLIST_LINE_USER_ID`

## Tests

```bash
pytest backend/tests -q
```

## Frontend Build

```bash
cd frontend
npm run build
```

build 後，backend 會自動從 `frontend/dist` 提供 SPA。

## Docker

root `Dockerfile` 已經是單一 process / 單一 port 形式：

```bash
docker build -t line-liff-calorie-helper .
docker run -p 8000:8000 --env-file .env line-liff-calorie-helper
```

## Notes

- 現在資料層預設優先吃 `SUPABASE_DB_URL`
- 如果沒填 Supabase 連線字串，才會退回 `backend/data/app.db`
- LINE 圖片與音訊訊息要有正式 channel token 才能抓內容
- 沒有模型金鑰時，文字 intake 會走 heuristic provider
