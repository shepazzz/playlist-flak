"""Human-readable event journal (spec §18).

Never logs secrets (slskd password, API keys, Spotify secret). Persists to
the `log_entries` table so the UI's log panel survives a backend restart,
and also mirrors to the standard python logger for console visibility.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import LogEntry

logger = logging.getLogger("playlist_flac_manager")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_REDACT_MARKERS = ("api_key", "apikey", "password", "secret", "x-api-key")


def _redact(message: str) -> str:
    lowered = message.lower()
    if any(marker in lowered for marker in _REDACT_MARKERS):
        return "[log message withheld: appeared to contain a credential]"
    return message


def log_event(db: Session, message: str, track_id: str | None = None) -> None:
    safe_message = _redact(message)
    entry = LogEntry(track_id=track_id, message=safe_message)
    db.add(entry)
    db.commit()
    logger.info(safe_message)
