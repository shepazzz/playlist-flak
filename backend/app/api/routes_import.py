from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.config import Settings
from app.orchestrator import pipeline
from app.schemas import ImportSpotifyRequest, ImportTextRequest, TrackOut
from app.spotify.client import SpotifyClient, SpotifyError

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/text", response_model=list[TrackOut])
def import_text(payload: ImportTextRequest, db: Session = Depends(get_db)):
    if not payload.text.strip():
        raise HTTPException(400, "Text is empty")
    playlist = pipeline.import_text(db, payload.text)
    tracks = playlist.tracks
    return [TrackOut.model_validate(t) for t in tracks]


@router.post("/file", response_model=list[TrackOut])
async def import_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Uploaded file is empty")
    playlist = pipeline.import_file(db, file.filename or "upload.txt", content)
    return [TrackOut.model_validate(t) for t in playlist.tracks]


@router.post("/spotify", response_model=list[TrackOut])
def import_spotify(payload: ImportSpotifyRequest, db: Session = Depends(get_db), settings: Settings = Depends(get_app_settings)):
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise HTTPException(
            400,
            "Spotify is not configured. Set SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET in .env "
            "(see README for how to create a Spotify app).",
        )
    client = SpotifyClient(settings.spotify_client_id, settings.spotify_client_secret)
    try:
        playlist = pipeline.import_spotify(db, payload.playlist_url, client)
    except SpotifyError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        client.close()
    return [TrackOut.model_validate(t) for t in playlist.tracks]
