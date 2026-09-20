import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_app_settings, get_provider
from app.database import Base, get_db
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


@pytest.fixture()
def client(tmp_path):
    from app.main import app
    from tests.fake_provider import FakeProvider

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    test_settings = Settings(
        library_root=str(tmp_path / "Music"),
        downloads_incoming_dir=str(tmp_path / "incoming"),
        strict_flac_only=True,
        mode="SAFE",
        _env_file=None,
    )
    provider = FakeProvider()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_app_settings] = lambda: test_settings
    app.dependency_overrides[get_provider] = lambda: provider

    with TestClient(app) as c:
        c.fake_provider = provider
        yield c

    app.dependency_overrides.clear()
