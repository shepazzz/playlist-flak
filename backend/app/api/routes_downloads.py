from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Download
from app.schemas import DownloadOut

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.get("", response_model=list[DownloadOut])
def list_downloads(db: Session = Depends(get_db)):
    downloads = db.query(Download).order_by(Download.queued_at.desc()).all()
    return [DownloadOut.model_validate(d) for d in downloads]
