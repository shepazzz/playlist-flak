"""Human-readable event journal (spec §18).

Never logs secrets (slskd password, API keys, Spotify secret). Persists to
the `log_entries` table so the UI's log panel survives a backend restart,
and also mirrors to the standard python logger for console visibility.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.models import LogEntry

logger = logging.getLogger("playlist_flac_manager")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Only redact when a credential-ish word is directly followed by what looks
# like an actual value (e.g. "api_key: abc123..." or "X-API-Key=..."), not
# plain prose that merely mentions "password"/"api key" as a setting name
# (e.g. "no username/password configured" must stay readable - it's the
# error message a user needs to diagnose their setup).
_REDACT_PATTERN = re.compile(
    r"(api[_-]?key|x-api-key|password|secret|authorization)\s*[:=]\s*\S{4,}",
    re.IGNORECASE,
)


def _redact(message: str) -> str:
    if _REDACT_PATTERN.search(message):
        return "[log message withheld: appeared to contain a credential]"
    return message


def log_event(db: Session, message: str, track_id: str | None = None) -> None:
    safe_message = _redact(message)
    entry = LogEntry(track_id=track_id, message=safe_message)
    db.add(entry)
    db.commit()
    logger.info(safe_message)
