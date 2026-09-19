from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_provider
from app.models import Candidate, LibraryFile, Download, Track
from app.orchestrator import pipeline
from app.providers.base import MusicSourceProvider
from app.schemas import ApproveRequest, CandidateOut, DownloadOut, TrackOut

router = APIRouter(prefix="/api/tracks", tags=["tracks"])


def _best_candidate(db: Session, track_id: str) -> Candidate | None:
    return (
        db.query(Candidate)
        .filter(Candidate.track_id == track_id)
        .order_by(Candidate.match_score.desc())
        .first()
    )


def _track_to_out(db: Session, track: Track) -> TrackOut:
    out = TrackOut.model_validate(track)
    best = _best_candidate(db, track.id)
    if best:
        out.best_match_score = best.match_score
        out.best_source_score = best.source_score
        out.best_format = f"FLAC {best.bit_depth or '?'}/{round((best.sample_rate_hz or 0) / 1000, 1) or '?'}" if best.extension == "flac" else (best.extension or "").upper()
        out.best_size_bytes = best.size_bytes

        # Prefer the verified file's actual measured properties once available.
        download = db.query(Download).filter(Download.candidate_id == best.id).first()
        if download:
            file_row = db.query(LibraryFile).filter(LibraryFile.download_id == download.id).first()
            if file_row and file_row.codec:
                sr = f"{(file_row.sample_rate_hz or 0) / 1000:g}" if file_row.sample_rate_hz else "?"
                out.best_format = f"{file_row.codec.upper()} {file_row.bit_depth or '?'}/{sr}"
                out.best_size_bytes = file_row.size_bytes or out.best_size_bytes
    return out


@router.get("", response_model=list[TrackOut])
def list_tracks(db: Session = Depends(get_db)):
    tracks = db.query(Track).order_by(Track.created_at).all()
    return [_track_to_out(db, t) for t in tracks]


@router.get("/{track_id}/candidates", response_model=list[CandidateOut])
def get_candidates(track_id: str, db: Session = Depends(get_db)):
    track = db.get(Track, track_id)
    if track is None:
        raise HTTPException(404, "Track not found")
    candidates = (
        db.query(Candidate)
        .filter(Candidate.track_id == track_id)
        .order_by(Candidate.match_score.desc())
        .all()
    )
    return [CandidateOut.model_validate(c) for c in candidates]


@router.post("/{track_id}/approve", response_model=DownloadOut)
def approve(track_id: str, payload: ApproveRequest, db: Session = Depends(get_db), provider: MusicSourceProvider = Depends(get_provider)):
    try:
        download = pipeline.approve_candidate(db, track_id, payload.candidate_id, provider)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return DownloadOut.model_validate(download)
