from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import routes_admin, routes_downloads, routes_import, routes_library, routes_logs, routes_search, routes_settings, routes_tracks
from app.api.deps import get_provider
from app.config import get_settings
from app.database import init_db
from app.orchestrator.queue_worker import BackgroundWorker

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    provider = get_provider()
    worker = BackgroundWorker(provider, settings)
    await worker.start()
    app.state.worker = worker
    try:
        yield
    finally:
        await worker.stop()


app = FastAPI(title="Playlist FLAC Manager", lifespan=lifespan)

app.include_router(routes_import.router)
app.include_router(routes_tracks.router)
app.include_router(routes_search.router)
app.include_router(routes_downloads.router)
app.include_router(routes_library.router)
app.include_router(routes_settings.router)
app.include_router(routes_logs.router)
app.include_router(routes_admin.router)

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
