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
