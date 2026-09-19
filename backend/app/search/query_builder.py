"""Search Manager: generate ordered, deduplicated query variants (spec §3).

The caller (queue_worker) tries these in order and stops at the first
variant that yields a usable candidate, so we don't fire every variant for
every track.
"""
from __future__ import annotations

from app.parsing.normalizer import NormalizedTrack


def build_queries(track: NormalizedTrack, strict_flac_only: bool = True) -> list[str]:
    artist = track.artist.strip()
    title = track.title.strip()

    if not artist or not title:
        return []

    queries: list[str] = [
        f"{artist} {title}",
        f"{artist} - {title}",
    ]

    if strict_flac_only:
        queries.append(f"{artist} {title} FLAC")

    if track.album:
        queries.append(f"{artist} {title} {track.album}")

    if track.version:
        queries.append(f"{artist} {title} {track.version}")

    seen: set[str] = set()
    deduped: list[str] = []
    for q in queries:
        q = " ".join(q.split()).strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            deduped.append(q)
    return deduped
