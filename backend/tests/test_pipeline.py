from pathlib import Path

from app.models import Candidate, Download, Track
from app.orchestrator import pipeline
from app.providers.base import RawCandidate
from tests.fake_provider import FakeProvider


def _flac_candidate(path: str, **kwargs) -> RawCandidate:
    defaults = dict(
        provider="fake", username="peer1", remote_path=path, filename=path.rsplit("/", 1)[-1],
        extension="flac", size_bytes=30_000_000, duration_sec=257.0, is_free_upload_slot=True,
        queue_length=0, upload_speed_bps=2_000_000, sibling_file_count=5,
    )
    defaults.update(kwargs)
    return RawCandidate(**defaults)


def test_import_text_creates_tracks(db_session):
    playlist = pipeline.import_text(
        db_session,
        "Vitalic - Poison Lips\nAcid Arab - Gul l'Abi\nThe Chemical Brothers - Star Guitar\n",
    )
    tracks = db_session.query(Track).filter_by(playlist_id=playlist.id).order_by(Track.position).all()
    assert len(tracks) == 3
    assert tracks[0].artist == "Vitalic"
    assert tracks[0].status == "IMPORTED"


def test_search_track_finds_and_scores_candidate(db_session, settings):
    playlist = pipeline.import_text(db_session, "Vitalic - Poison Lips\n")
    track = db_session.query(Track).filter_by(playlist_id=playlist.id).first()

    provider = FakeProvider()
    provider.add_response(
        "vitalic poison lips",
        [_flac_candidate("music/Vitalic/Flashmob/Vitalic - Poison Lips.flac")],
    )

    result = pipeline.search_track(db_session, track.id, provider, settings)
    assert result.status == "MATCHED"

    candidates = db_session.query(Candidate).filter_by(track_id=track.id).all()
    assert len(candidates) == 1
    assert candidates[0].match_score > 80


def test_search_track_no_candidates_is_not_found(db_session, settings):
    playlist = pipeline.import_text(db_session, "Unknown Artist - Unknown Track\n")
    track = db_session.query(Track).filter_by(playlist_id=playlist.id).first()

    provider = FakeProvider()  # no responses configured -> nothing found
    result = pipeline.search_track(db_session, track.id, provider, settings)
    assert result.status == "NOT_FOUND"


def test_search_track_filters_non_flac_in_strict_mode(db_session, settings):
    playlist = pipeline.import_text(db_session, "Vitalic - Poison Lips\n")
    track = db_session.query(Track).filter_by(playlist_id=playlist.id).first()

    provider = FakeProvider()
    provider.add_response(
        "vitalic poison lips",
        [_flac_candidate("music/Vitalic - Poison Lips.mp3", extension="mp3")],
    )
    result = pipeline.search_track(db_session, track.id, provider, settings)
    assert result.status == "NOT_FOUND"


def test_search_track_remix_flags_review_required(db_session, settings):
    playlist = pipeline.import_text(db_session, "Vitalic - Poison Lips\n")
    track = db_session.query(Track).filter_by(playlist_id=playlist.id).first()

    provider = FakeProvider()
    provider.add_response(
        "vitalic poison lips",
        [_flac_candidate("music/Vitalic - Poison Lips (Someone Remix).flac")],
    )
    result = pipeline.search_track(db_session, track.id, provider, settings)
    assert result.status == "REVIEW_REQUIRED"


def test_search_track_provider_error_sets_failed_not_stuck_searching(db_session, settings):
    playlist = pipeline.import_text(db_session, "Vitalic - Poison Lips\n")
    track = db_session.query(Track).filter_by(playlist_id=playlist.id).first()

    class ExplodingProvider(FakeProvider):
        def search(self, query: str) -> str:
            raise RuntimeError("slskd unreachable")

    result = pipeline.search_track(db_session, track.id, ExplodingProvider(), settings)
    assert result.status == "FAILED"
    assert "slskd unreachable" in result.status_reason


def test_approve_candidate_creates_download(db_session, settings):
    playlist = pipeline.import_text(db_session, "Vitalic - Poison Lips\n")
    track = db_session.query(Track).filter_by(playlist_id=playlist.id).first()
    provider = FakeProvider()
    provider.add_response("vitalic poison lips", [_flac_candidate("music/Vitalic - Poison Lips.flac")])
    pipeline.search_track(db_session, track.id, provider, settings)
    candidate = db_session.query(Candidate).filter_by(track_id=track.id).first()

    download = pipeline.approve_candidate(db_session, track.id, candidate.id, provider)
    db_session.refresh(track)
    assert track.status == "QUEUED"
    assert download.state == "QUEUED"


def test_full_flow_download_verify_and_library_placement(db_session, settings):
    playlist = pipeline.import_text(db_session, "Vitalic - Poison Lips\n")
    track = db_session.query(Track).filter_by(playlist_id=playlist.id).first()

    provider = FakeProvider()
    provider.add_response("vitalic poison lips", [_flac_candidate("music/Vitalic - Poison Lips.flac")])
    pipeline.search_track(db_session, track.id, provider, settings)
    candidate = db_session.query(Candidate).filter_by(track_id=track.id).first()

    download = pipeline.approve_candidate(db_session, track.id, candidate.id, provider)

    # Simulate slskd having finished the transfer and dropped the file on disk.
    incoming = Path(settings.downloads_incoming_dir) / "peer1"
    incoming.mkdir(parents=True)
    fake_flac = incoming / "Vitalic - Poison Lips.flac"
    fake_flac.write_bytes(b"not a real flac stream")

    key = f"{candidate.username}:{candidate.remote_path}"
    provider.set_state(key, "COMPLETED")

    pipeline.poll_downloads(db_session, provider, settings)

    db_session.refresh(track)
    db_session.refresh(download)
    # Our fake bytes aren't a real FLAC stream, so verification must call it
    # invalid rather than pretend success - this proves the pipeline wires
    # verification failures through to track status instead of blindly
    # marking things COMPLETED.
    assert track.status == "FAILED"
