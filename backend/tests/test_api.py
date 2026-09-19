import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_app_settings, get_provider
from app.config import Settings
from app.database import Base, get_db
from app.main import app
from tests.fake_provider import FakeProvider


@pytest.fixture()
def client(tmp_path):
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


def test_full_mvp_flow(client):
    # 1. import
    resp = client.post("/api/import/text", json={"text": "Vitalic - Poison Lips\n"})
    assert resp.status_code == 200
    tracks = resp.json()
    assert len(tracks) == 1
    track_id = tracks[0]["id"]

    # 2. configure fake provider with a FLAC candidate
    from app.providers.base import RawCandidate

    client.fake_provider.add_response(
        "vitalic poison lips",
        [
            RawCandidate(
                provider="fake", username="peer1", remote_path="music/Vitalic - Poison Lips.flac",
                filename="Vitalic - Poison Lips.flac", extension="flac", size_bytes=30_000_000,
                duration_sec=257.0, is_free_upload_slot=True, queue_length=0,
                upload_speed_bps=2_000_000, sibling_file_count=5,
            )
        ],
    )

    # 3. trigger search
    resp = client.post(f"/api/search/{track_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "MATCHED"

    # 4. list candidates
    resp = client.get(f"/api/tracks/{track_id}/candidates")
    candidates = resp.json()
    assert len(candidates) == 1
    candidate_id = candidates[0]["id"]

    # 5. approve
    resp = client.post(f"/api/tracks/{track_id}/approve", json={"candidate_id": candidate_id})
    assert resp.status_code == 200
    assert resp.json()["state"] == "QUEUED"

    # 6. downloads list shows it
    resp = client.get("/api/downloads")
    assert len(resp.json()) == 1

    # 7. tracks list reflects state
    resp = client.get("/api/tracks")
    assert resp.json()[0]["status"] == "QUEUED"

    # 8. settings round-trip
    resp = client.get("/api/settings")
    assert resp.json()["mode"] == "SAFE"
    resp = client.put("/api/settings", json={"mode": "ASSISTED"})
    assert resp.json()["mode"] == "ASSISTED"

    # 9. logs were recorded
    resp = client.get("/api/logs")
    assert len(resp.json()) > 0
