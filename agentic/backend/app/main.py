from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import get_settings
from .database import engine, init_db
from .routes import router
from .worker import start_worker, stop_worker


settings = get_settings()


def runtime_role() -> str:
    return settings.app_runtime_role


def _readiness_errors() -> list[str]:
    errors: list[str] = []
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        errors.append(f"database:{type(exc).__name__}")
    if settings.app_runtime_role == "web" and not settings.frontend_dist_path.exists():
        errors.append("frontend_dist_missing")
    return errors


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.app_runtime_role == "worker":
        start_worker()
    try:
        yield
    finally:
        if settings.app_runtime_role == "worker":
            stop_worker()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment != "production" else [],
    allow_credentials=settings.environment != "production",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
    request.state.trace_id = trace_id
    response: Response = await call_next(request)
    response.headers["x-trace-id"] = trace_id
    return response


@app.get("/readyz")
def readyz() -> dict[str, object]:
    errors = _readiness_errors()
    if errors:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "errors": errors})
    return {"status": "ready", "role": runtime_role()}


frontend_dist = settings.frontend_dist_path
if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_entry(full_path: str):
        if full_path in {"", "/"}:
            return FileResponse(frontend_dist / "index.html")
        if full_path == "readyz":
            errors = _readiness_errors()
            if errors:
                return JSONResponse({"detail": {"status": "not_ready", "errors": errors}}, status_code=503)
            return JSONResponse({"status": "ready", "role": runtime_role()})
        requested = frontend_dist / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(requested)
        return FileResponse(frontend_dist / "index.html")
