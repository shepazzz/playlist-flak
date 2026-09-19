"""Candidate Matcher (spec §6) + version-mismatch guard (spec §8).

`match_score` (0-100) measures "is this the track the user asked for" —
artist(25) + track(30) + version(15) + album(10) + duration(10) +
file properties(10). It is intentionally kept separate from `source_score`
(matching/source_score.py), which measures "how good is this particular
source", per spec §7.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.parsing.normalizer import NormalizedTrack
from app.providers.base import RawCandidate

# Terms that change the musical identity of a recording. Never let a
# candidate carrying one of these win automatically over what the user
# actually asked for (spec §8).
_DISQUALIFYING_TERMS = (
    "remix",
    "live",
    "instrumental",
    "radio edit",
    "remaster",
    "remastered",
    "cover",
    "karaoke",
    "acoustic",
    "demo",
    "extended",
    "vip mix",
)

_VARIOUS_ARTISTS_RE = re.compile(r"\bva\b|various\s+artists", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9']+")


@dataclass
class ScoredCandidate:
    candidate: RawCandidate
    artist_score: float
    track_score: float
    version_score: float
    album_score: float
    duration_score: float
    file_score: float
    match_score: float
    review_required: bool
    review_reason: str | None = None
    notes: list[str] = field(default_factory=list)


def _normalize_text(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def _path_text(candidate: RawCandidate) -> str:
    return _normalize_text(candidate.remote_path.replace("\\", "/"))


def _bucket(ratio: float, exact_at: float, exact_score: float, close_at: float, close_score: float) -> float:
    if ratio >= exact_at:
        return exact_score
    if ratio >= close_at:
        return close_score
    if ratio <= 0:
        return 0.0
    return round(close_score * (ratio / close_at), 1)


def _score_artist(track_artist: str, path_text: str) -> tuple[float, list[str]]:
    notes = []
    if not track_artist:
        return 5.0, notes
    ratio = fuzz.partial_ratio(track_artist, path_text)
    if ratio < 80 and _VARIOUS_ARTISTS_RE.search(path_text):
        notes.append("compilation / Various Artists source")
        return 10.0, notes
    return _bucket(ratio, exact_at=92, exact_score=25, close_at=78, close_score=20), notes


def _score_track(track_title: str, path_text: str) -> float:
    if not track_title:
        return 5.0
    ratio = fuzz.partial_ratio(track_title, path_text)
    return _bucket(ratio, exact_at=92, exact_score=30, close_at=78, close_score=25)


def _detected_terms(text: str) -> set[str]:
    return {t for t in _DISQUALIFYING_TERMS if t in text}


def _score_version(requested_version: str | None, path_text: str) -> tuple[float, bool, str | None]:
    candidate_terms = _detected_terms(path_text)

    if not requested_version:
        if not candidate_terms:
            return 15.0, False, None
        return (
            0.0,
            True,
            f"User requested the standard version but this file appears to be a "
            f"{'/'.join(sorted(candidate_terms))} version.",
        )

    requested_terms = _detected_terms(requested_version)
    if requested_terms and requested_terms.issubset(candidate_terms):
        return 15.0, False, None

    conflicting = candidate_terms - requested_terms
    if conflicting:
        return (
            0.0,
            True,
            f"User requested '{requested_version}' but this file appears to be a "
            f"{'/'.join(sorted(conflicting))} version instead.",
        )

    # No version markers found in the filename at all - ambiguous, could be
    # an unlabeled match for the exact requested version, or could not be.
    return 7.0, True, f"Could not confirm this file is the requested '{requested_version}' version."


def _score_album(track_album: str | None, path_text: str) -> float:
    if not track_album:
        return 5.0
    ratio = fuzz.partial_ratio(track_album, path_text)
    return _bucket(ratio, exact_at=90, exact_score=10, close_at=70, close_score=6)


def _score_duration(expected_ms: int | None, candidate_sec: float | None) -> tuple[float, str | None]:
    if not expected_ms or not candidate_sec:
        return 5.0, None
    expected_sec = expected_ms / 1000.0
    delta = abs(expected_sec - candidate_sec)
    if delta <= 2:
        return 10.0, None
    if delta <= 5:
        return 7.0, None
    if delta <= 15:
        return 2.0, f"Duration differs by {delta:.0f}s from Spotify metadata - suspicious."
    return 0.0, f"Duration differs by {delta:.0f}s from Spotify metadata."


def _score_file_properties(candidate: RawCandidate, strict_flac_only: bool) -> tuple[float, str | None]:
    is_flac = (candidate.extension or "").lower() == "flac"
    if strict_flac_only and not is_flac:
        return 0.0, "Not a FLAC file (strict FLAC mode is on)."
    if is_flac:
        return 10.0, None
    return 3.0, "Not a FLAC file."


def score_candidate(
    track: NormalizedTrack,
    candidate: RawCandidate,
    *,
    expected_duration_ms: int | None = None,
    strict_flac_only: bool = True,
) -> ScoredCandidate:
    path_text = _path_text(candidate)
    notes: list[str] = []

    artist_score, artist_notes = _score_artist(track.artist, path_text)
    notes.extend(artist_notes)

    track_score = _score_track(track.title, path_text)
    version_score, version_review, version_reason = _score_version(track.version, path_text)
    album_score = _score_album(track.album, path_text)
    duration_score, duration_note = _score_duration(expected_duration_ms, candidate.duration_sec)
    file_score, file_note = _score_file_properties(candidate, strict_flac_only)

    for n in (duration_note, file_note):
        if n:
            notes.append(n)

    total = artist_score + track_score + version_score + album_score + duration_score + file_score
    total = max(0.0, min(100.0, total))

    review_required = version_review
    review_reason = version_reason

    return ScoredCandidate(
        candidate=candidate,
        artist_score=artist_score,
        track_score=track_score,
        version_score=version_score,
        album_score=album_score,
        duration_score=duration_score,
        file_score=file_score,
        match_score=round(total, 1),
        review_required=review_required,
        review_reason=review_reason,
        notes=notes,
    )


def flag_ambiguous(scored: list[ScoredCandidate], margin: float = 4.0) -> None:
    """If the top two candidates are within `margin` points of each other,
    force REVIEW_REQUIRED rather than silently auto-picking one (spec §8)."""
    ranked = sorted(scored, key=lambda s: s.match_score, reverse=True)
    if len(ranked) < 2:
        return
    best, second = ranked[0], ranked[1]
    if best.match_score - second.match_score <= margin and best.match_score > 0:
        if not best.review_required:
            best.review_required = True
            best.review_reason = (
                f"Top match ({best.match_score}) is close to the next candidate "
                f"({second.match_score}) - review required to avoid picking the wrong source."
            )
