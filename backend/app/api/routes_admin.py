"""Admin/utility endpoints - not part of the original spec's API list, but
needed for local testing/iteration: a way to wipe imported tracks, search
results, downloads and logs without touching already-organized library
files on disk (those are left alone; this only clears app-tracked records).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.logging_utils import log_event
from app.models import Candidate, Download, LibraryFile, LogEntry, Playlist, Search, Track

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/reset")
def reset_all(db: Session = Depends(get_db)):
    counts = {
        "files": db.query(LibraryFile).delete(),
        "downloads": db.query(Download).delete(),
        "candidates": db.query(Candidate).delete(),
        "searches": db.query(Search).delete(),
        "tracks": db.query(Track).delete(),
        "playlists": db.query(Playlist).delete(),
        "logs": db.query(LogEntry).delete(),
    }
    db.commit()
    log_event(db, "All imported tracks, searches, downloads and logs were reset by the user.")
    return {"cleared": counts}
