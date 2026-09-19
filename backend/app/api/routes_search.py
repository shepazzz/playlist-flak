from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db, get_provider
from app.config import Settings
from app.orchestrator import pipeline
from app.providers.base import MusicSourceProvider
from app.schemas import TrackOut

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("/{track_id}", response_model=TrackOut)
def search_track(
    track_id: str,
    db: Session = Depends(get_db),
    provider: MusicSourceProvider = Depends(get_provider),
    settings: Settings = Depends(get_app_settings),
):
    try:
        track = pipeline.search_track(db, track_id, provider, settings)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return TrackOut.model_validate(track)
