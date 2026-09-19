from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import LogEntry
from app.schemas import LogEntryOut

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=list[LogEntryOut])
def list_logs(db: Session = Depends(get_db), limit: int = 200):
    entries = db.query(LogEntry).order_by(LogEntry.created_at.desc()).limit(limit).all()
    return [LogEntryOut.model_validate(e) for e in reversed(entries)]
