from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import logging
import sys
import threading
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .api.observability_routes import router as observability_router
from .api.routes import router
from .config import settings
from .database import Base, engine, get_session_factory
from .schema_sync import ensure_runtime_schema
from .services.background_jobs import start_background_worker, stop_background_worker
from .services.knowledge import prewarm_knowledge_layer


logger = logging.getLogger(__name__)


def _prewarm_knowledge_background() -> None:
    try:
        prewarm_knowledge_layer()
    except Exception:
        logger.exception("Failed to prewarm knowledge layer during startup.")


def _startup_engine(app: FastAPI):
    testing_factory = getattr(app.state, "_testing_session_factory", None)
    if testing_factory is not None:
        bind = getattr(testing_factory, "kw", {}).get("bind")
        if bind is not None:
            return bind
    session_factory = get_session_factory()
    bind = getattr(session_factory, "kw", {}).get("bind")
    return bind or engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_engine = _startup_engine(app)
    Base.metadata.create_all(bind=startup_engine)
    ensure_runtime_schema(startup_engine)
    threading.Thread(target=_prewarm_knowledge_background, daemon=True).start()

    should_run_background_worker = "pytest" not in sys.modules
    if should_run_background_worker:
        start_background_worker()

    try:
        yield
    finally:
        if should_run_background_worker:
            stop_background_worker()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(observability_router)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
    request.state.trace_id = trace_id
    response: Response = await call_next(request)
    response.headers["x-trace-id"] = trace_id
    return response


frontend_dist = Path(settings.frontend_dist_dir)
if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    def spa_entry(full_path: str):
        requested = frontend_dist / full_path
        if full_path and requested.exists() and requested.is_file():
            return FileResponse(requested)
        return FileResponse(frontend_dist / "index.html")
