"""Import: text / CSV / TXT -> RawTrackLine.

Supports the separator styles from spec §1A: "Artist - Track",
"Artist — Track" (em dash), "Artist – Track" (en dash), "Artist | Track",
"Artist / Track".
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

# Order matters: try the more specific/unambiguous separators first so we
# never split a hyphenated artist or track name at the wrong point.
_SEPARATOR_PATTERN = re.compile(r"\s+(?:-|—|–|\||/)\s+")

_LEADING_TRACK_NUMBER = re.compile(r"^\s*\d{1,3}[.)]?\s*[-.)]?\s+")


@dataclass
class RawTrackLine:
    raw_line: str
    artist: str | None
    title: str | None
    album: str | None = None


def _strip_leading_track_number(line: str) -> str:
    return _LEADING_TRACK_NUMBER.sub("", line, count=1)


def parse_line(line: str) -> RawTrackLine | None:
    original = line.strip()
    if not original:
        return None

    cleaned = _strip_leading_track_number(original)
    parts = _SEPARATOR_PATTERN.split(cleaned, maxsplit=1)

    if len(parts) == 2:
        artist, title = parts[0].strip(), parts[1].strip()
        if artist and title:
            return RawTrackLine(raw_line=original, artist=artist, title=title)

    # No recognizable separator: keep the raw line so the user can see it
    # was imported, but leave artist/title unset -> REVIEW_REQUIRED/NOT_FOUND
    # rather than guessing wrong.
    return RawTrackLine(raw_line=original, artist=None, title=cleaned or None)


def parse_text(text: str) -> list[RawTrackLine]:
    lines = [ln for ln in text.splitlines()]
    parsed = []
    for ln in lines:
        result = parse_line(ln)
        if result is not None:
            parsed.append(result)
    return parsed


def parse_csv_or_txt(filename: str, content: bytes) -> list[RawTrackLine]:
    text = content.decode("utf-8-sig", errors="replace")

    if filename.lower().endswith(".csv"):
        return _parse_csv(text)
    return parse_text(text)


def _parse_csv(text: str) -> list[RawTrackLine]:
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    fieldnames = [f.lower().strip() for f in (reader.fieldnames or [])]

    has_headers = any(f in fieldnames for f in ("artist", "track", "title"))

    results: list[RawTrackLine] = []

    if has_headers:
        reader.fieldnames = fieldnames
        for row in reader:
            artist = (row.get("artist") or "").strip() or None
            title = (row.get("title") or row.get("track") or "").strip() or None
            album = (row.get("album") or "").strip() or None
            raw = ",".join(v or "" for v in row.values())
            if artist or title:
                results.append(RawTrackLine(raw_line=raw, artist=artist, title=title, album=album))
        return results

    # No usable header row: treat every line (including the first) as a
    # plain "Artist - Track" style line, same as TXT import.
    return parse_text(text)
