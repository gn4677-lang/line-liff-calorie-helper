from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import settings
from .database import Base, engine
from .schema_sync import ensure_runtime_schema


app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)


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
