"""Rate-limited background worker (spec §3/§14): automatically searches
newly imported tracks (never more than `search_rate_limit_per_minute`
searches/minute against slskd) and polls in-flight downloads. Runs as an
asyncio task started from the FastAPI app lifespan.
"""
from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.database import SessionLocal
from app.models import Track
from app.orchestrator import pipeline
from app.providers.base import MusicSourceProvider

logger = logging.getLogger("playlist_flac_manager.worker")


class BackgroundWorker:
    def __init__(self, provider: MusicSourceProvider, settings: Settings):
        self._provider = provider
        self._settings = settings
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._search_loop(), name="search-loop"),
            asyncio.create_task(self._download_poll_loop(), name="download-poll-loop"),
        ]

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass

    async def _search_loop(self) -> None:
        while not self._stop.is_set():
            min_interval = 60.0 / max(1, self._settings.search_rate_limit_per_minute)
            db = SessionLocal()
            track = None
            try:
                track = db.query(Track).filter(Track.status == "IMPORTED").order_by(Track.created_at).first()
                if track is not None:
                    try:
                        pipeline.search_track(db, track.id, self._provider, self._settings)
                    except Exception:  # noqa: BLE001 - one bad track must not kill the worker
                        logger.exception("search_track failed for track %s", track.id)
            finally:
                db.close()
            await asyncio.sleep(min_interval if track is not None else 2.0)

    async def _download_poll_loop(self) -> None:
        while not self._stop.is_set():
            db = SessionLocal()
            try:
                pipeline.poll_downloads(db, self._provider, self._settings)
            except Exception:  # noqa: BLE001
                logger.exception("poll_downloads failed")
            finally:
                db.close()
            await asyncio.sleep(self._settings.download_status_poll_seconds)
