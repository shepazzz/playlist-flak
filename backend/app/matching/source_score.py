"""Source Score (spec §7): how good is this particular source, independent
of whether it's the right track (that's match_score, scorer.py). Never
blended into match_score — the UI shows both separately.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from app.parsing.normalizer import NormalizedTrack
from app.providers.base import RawCandidate

_BYTES_PER_SEC_16_44 = 100_000  # ~800 kbps typical CD-quality FLAC


def _slot_and_queue_score(candidate: RawCandidate) -> tuple[float, float]:
    slot_score = 20.0 if candidate.is_free_upload_slot else 5.0
    queue_score = max(0.0, 15.0 - min(candidate.queue_length, 15))
    return slot_score, queue_score


def _speed_score(candidate: RawCandidate) -> float:
    if not candidate.upload_speed_bps:
        return 5.0
    # 1 MB/s (8 Mbps) or better -> full marks, scaled linearly below that.
    ref = 1_000_000
    return round(min(15.0, 15.0 * candidate.upload_speed_bps / ref), 1)


def _size_sanity_score(candidate: RawCandidate) -> float:
    if not candidate.size_bytes or not candidate.duration_sec:
        return 7.0  # neutral - can't evaluate
    expected = candidate.duration_sec * _BYTES_PER_SEC_16_44
    if expected <= 0:
        return 7.0
    ratio = candidate.size_bytes / expected
    if 0.5 <= ratio <= 2.2:
        return 15.0
    if 0.3 <= ratio <= 3.0:
        return 8.0
    return 0.0


def _folder_completeness_score(candidate: RawCandidate) -> float:
    if candidate.sibling_file_count >= 8:
        return 15.0
    if candidate.sibling_file_count >= 3:
        return 8.0
    return 3.0


def _naming_score(track: NormalizedTrack, candidate: RawCandidate) -> float:
    expected = f"{track.artist} {track.title}".strip()
    if not expected:
        return 10.0
    ratio = fuzz.token_set_ratio(expected, candidate.filename.lower())
    return round(20.0 * ratio / 100.0, 1)


def score_source(track: NormalizedTrack, candidate: RawCandidate) -> float:
    slot_score, queue_score = _slot_and_queue_score(candidate)
    speed_score = _speed_score(candidate)
    size_score = _size_sanity_score(candidate)
    folder_score = _folder_completeness_score(candidate)
    naming_score = _naming_score(track, candidate)

    total = slot_score + queue_score + speed_score + size_score + folder_score + naming_score
    return round(max(0.0, min(100.0, total)), 1)
