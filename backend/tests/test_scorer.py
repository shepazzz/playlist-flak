from app.matching.scorer import flag_ambiguous, score_candidate
from app.matching.source_score import score_source
from app.parsing.normalizer import NormalizedTrack
from app.providers.base import RawCandidate


def _candidate(remote_path: str, **kwargs) -> RawCandidate:
    defaults = dict(
        provider="slskd",
        username="peer1",
        remote_path=remote_path,
        filename=remote_path.rsplit("/", 1)[-1],
        extension="flac",
        size_bytes=30_000_000,
        duration_sec=257.0,
        is_free_upload_slot=True,
        queue_length=0,
        upload_speed_bps=2_000_000,
        sibling_file_count=10,
    )
    defaults.update(kwargs)
    return RawCandidate(**defaults)


def test_exact_match_scores_high_and_no_review():
    track = NormalizedTrack(artist="vitalic", title="poison lips", version=None)
    cand = _candidate("music/Vitalic/Flashmob/Vitalic - Poison Lips.flac")
    scored = score_candidate(track, cand, expected_duration_ms=257_000)
    assert scored.match_score >= 90
    assert scored.review_required is False


def test_remix_not_auto_preferred_when_original_requested():
    track = NormalizedTrack(artist="vitalic", title="poison lips", version=None)
    cand = _candidate("music/Vitalic/Vitalic - Poison Lips (Someone Remix).flac")
    scored = score_candidate(track, cand, expected_duration_ms=257_000)
    assert scored.review_required is True
    assert "remix" in scored.review_reason.lower()
    assert scored.version_score == 0


def test_requested_extended_mix_matches_extended_mix_file():
    track = NormalizedTrack(artist="artist", title="track", version="extended mix")
    cand = _candidate("music/Artist - Track (Extended Mix).flac")
    scored = score_candidate(track, cand, expected_duration_ms=None)
    assert scored.version_score == 15
    assert scored.review_required is False


def test_requested_extended_mix_but_file_is_live_flags_review():
    track = NormalizedTrack(artist="artist", title="track", version="extended mix")
    cand = _candidate("music/Artist - Track (Live).flac")
    scored = score_candidate(track, cand, expected_duration_ms=None)
    assert scored.review_required is True


def test_non_flac_scores_zero_file_points_in_strict_mode():
    track = NormalizedTrack(artist="artist", title="track", version=None)
    cand = _candidate("music/Artist - Track.mp3", extension="mp3")
    scored = score_candidate(track, cand, strict_flac_only=True)
    assert scored.file_score == 0


def test_duration_mismatch_penalized():
    track = NormalizedTrack(artist="artist", title="track", version=None)
    cand = _candidate("music/Artist - Track.flac", duration_sec=400.0)
    scored = score_candidate(track, cand, expected_duration_ms=257_000)
    assert scored.duration_score == 0


def test_flag_ambiguous_marks_close_top_two():
    track = NormalizedTrack(artist="artist", title="track", version=None)
    c1 = score_candidate(track, _candidate("music/Artist - Track.flac"))
    c2 = score_candidate(track, _candidate("music/Various/Artist - Track.flac", sibling_file_count=1))
    flag_ambiguous([c1, c2], margin=100)  # force ambiguity for the test
    assert c1.review_required is True


def test_source_score_rewards_free_slot_and_speed():
    track = NormalizedTrack(artist="artist", title="track", version=None)
    good = _candidate("music/Artist - Track.flac")
    bad = _candidate(
        "music/Artist - Track.flac",
        is_free_upload_slot=False,
        queue_length=20,
        upload_speed_bps=1000,
        sibling_file_count=1,
    )
    assert score_source(track, good) > score_source(track, bad)
