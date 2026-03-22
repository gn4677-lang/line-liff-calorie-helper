FROM node:24-bookworm-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app-runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_RUNTIME_ROLE=web

COPY backend/requirements.txt /app/backend/requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY docs/ /app/docs/
COPY TODO.md /app/TODO.md
COPY .env.example /app/.env.example
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

EXPOSE 8000
CMD sh -c "if [ \"$APP_RUNTIME_ROLE\" = \"worker\" ]; then python -m backend.app.worker; else uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}; fi"
