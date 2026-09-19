from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.split("///", 1)[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(settings.database_url, connect_args={"check_same_thread": False})
    return create_engine(settings.database_url)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    from app import models  # noqa: F401 ensure models are registered

    Base.metadata.create_all(bind=engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
