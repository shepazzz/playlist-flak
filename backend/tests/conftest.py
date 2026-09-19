import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.config import Settings


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    from app import models  # noqa: F401 register tables

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        database_url="sqlite:///:memory:",
        library_root=str(tmp_path / "Music"),
        downloads_incoming_dir=str(tmp_path / "incoming"),
        strict_flac_only=True,
        mode="SAFE",
        duplicate_policy="SKIP",
        rewrite_metadata=False,
        _env_file=None,
    )
