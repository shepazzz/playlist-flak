from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import LibraryFile
from app.schemas import LibraryFileOut

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("", response_model=list[LibraryFileOut])
def list_library(db: Session = Depends(get_db)):
    files = (
        db.query(LibraryFile)
        .filter(LibraryFile.library_path.is_not(None))
        .order_by(LibraryFile.created_at.desc())
        .all()
    )
    return [LibraryFileOut.model_validate(f) for f in files]
