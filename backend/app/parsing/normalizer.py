"""Metadata Normalizer (spec §2).

Builds a canonical representation for search + matching: strips noise
(track numbers, punctuation, ".flac", "[FLAC]", "(Lossless)", bitrate/CD-rip
markers) while preserving musically significant version markers (Remix,
Extended, Edit, Live, Instrumental, Remaster, Version, Mix).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

VERSION_KEYWORDS = (
    "remix",
    "extended",
    "edit",
    "live",
    "instrumental",
    "remaster",
    "remastered",
    "version",
    "mix",
)

# Bracket/paren contents that are pure noise and should be dropped entirely,
# never treated as a version marker.
_NOISE_GROUP_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"flac",
        r"lossless",
        r"\d+\s?kbps",
        r"\d{1,2}[- ]?bit",
        r"\d{2,3}(\.\d+)?\s?k?hz",
        r"^cd\s?\d*$",
        r"^web$",
        r"^vinyl$",
        r"^rip$",
        r"^cdm$",
    )
]

_BRACKET_GROUP = re.compile(r"[\(\[]([^\)\]]+)[\)\]]")

_GLOBAL_NOISE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\.flac\b",
        r"\bflac\b",
        r"\blossless\b",
        r"\d+\s?kbps",
        r"\b\d{1,2}[- ]?bit\b",
        r"\b\d{2,3}(\.\d+)?\s?k?hz\b",
        r"\bcd\s?rip\b",
        r"\bweb\s?rip\b",
    )
]

_PUNCT_TO_SPACE = re.compile(r"[^\w\s']", re.UNICODE)
_MULTI_SPACE = re.compile(r"\s+")


@dataclass
class NormalizedTrack:
    artist: str
    title: str
    version: str | None
    album: str | None = None


def _is_noise_group(content: str) -> bool:
    stripped = content.strip()
    return any(p.search(stripped) for p in _NOISE_GROUP_PATTERNS)


def _contains_version_keyword(content: str) -> bool:
    lowered = content.lower()
    return any(kw in lowered for kw in VERSION_KEYWORDS)


def _extract_version_and_clean(text: str) -> tuple[str, str | None]:
    version: str | None = None

    def _replace(match: re.Match) -> str:
        nonlocal version
        content = match.group(1).strip()
        if _is_noise_group(content):
            return " "
        if _contains_version_keyword(content):
            if version is None:
                version = content
            return " "
        # Unknown bracketed content (e.g. "(feat. Someone)") - keep it in
        # the text; it may be musically meaningful and we don't drop data
        # we can't classify.
        return match.group(0)

    cleaned = _BRACKET_GROUP.sub(_replace, text)
    return cleaned, version


def _strip_global_noise(text: str) -> str:
    result = text
    for pattern in _GLOBAL_NOISE_PATTERNS:
        result = pattern.sub(" ", result)
    return result


def _canonicalize(text: str) -> str:
    text = _PUNCT_TO_SPACE.sub(" ", text)
    text = _MULTI_SPACE.sub(" ", text).strip().lower()
    return text


def normalize_track(artist: str | None, title: str | None, album: str | None = None) -> NormalizedTrack:
    artist = artist or ""
    title = title or ""

    title_wo_noise = _strip_global_noise(title)
    title_wo_brackets, version = _extract_version_and_clean(title_wo_noise)

    norm_artist = _canonicalize(_strip_global_noise(artist))
    norm_title = _canonicalize(title_wo_brackets)
    norm_album = _canonicalize(_strip_global_noise(album)) if album else None
    norm_version = _canonicalize(version) if version else None

    return NormalizedTrack(artist=norm_artist, title=norm_title, version=norm_version, album=norm_album)
