from app.models import LogEntry, Track
from app.orchestrator import pipeline


def test_reset_all_clears_tracks_and_logs(client):
    client.post("/api/import/text", json={"text": "Vitalic - Poison Lips\n"})
    assert len(client.get("/api/tracks").json()) == 1
    assert len(client.get("/api/logs").json()) > 0

    resp = client.post("/api/admin/reset")
    assert resp.status_code == 200
    assert resp.json()["cleared"]["tracks"] == 1

    assert client.get("/api/tracks").json() == []
    # the reset itself logs one new entry, so logs aren't necessarily empty,
    # but none of the old track-scoped entries should survive
    for entry in client.get("/api/logs").json():
        assert "Imported" not in entry["message"]
