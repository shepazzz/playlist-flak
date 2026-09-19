"""Library organizer (spec §11): places verified FLAC files into

    Music/Artist/Year - Album/NN - Track.flac

or, for compilations:

    Music/Various Artists/Year - Album/NN - Artist - Track.flac

Never silently overwrites an existing file - the three explicit policies
from spec §11 (SKIP / COMPARE / KEEP_BOTH) are the only ways a collision is
resolved.
"""
from __future__ import annotations

import filecmp
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

_ILLEGAL_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TRAILING_DOTS_SPACES = re.compile(r"[. ]+$")

_VARIOUS_ARTISTS = "Various Artists"


@dataclass
class TrackForLibrary:
    artist: str
    title: str
    album: str | None
    album_artist: str | None
    release_year: int | None
    track_number: int | None


@dataclass
class PlacementResult:
    library_path: Path | None
    action: str  # MOVED | SKIP | KEEP_BOTH | COMPARE_IDENTICAL | COMPARE_DIFFERENT
    message: str


def sanitize_component(name: str, fallback: str = "Unknown") -> str:
    name = name.strip() if name else ""
    name = _ILLEGAL_WINDOWS_CHARS.sub("_", name)
    name = _TRAILING_DOTS_SPACES.sub("", name)
    return name or fallback


def is_compilation(track: TrackForLibrary) -> bool:
    album_artist = (track.album_artist or "").strip().lower()
    return album_artist in ("various artists", "various", "va")


def build_library_path(library_root: Path, track: TrackForLibrary) -> Path:
    year = track.release_year or 0
    album = sanitize_component(track.album or "Unknown Album")
    track_no = f"{track.track_number:02d}" if track.track_number else "00"
    title = sanitize_component(track.title or "Unknown Title")

    year_album = f"{year} - {album}" if year else album

    if is_compilation(track):
        artist = sanitize_component(track.artist or "Unknown Artist")
        filename = f"{track_no} - {artist} - {title}.flac"
        return library_root / _VARIOUS_ARTISTS / year_album / filename

    artist_dir = sanitize_component(track.album_artist or track.artist or "Unknown Artist")
    filename = f"{track_no} - {title}.flac"
    return library_root / artist_dir / year_album / filename


def _keep_both_path(target: Path) -> Path:
    counter = 1
    candidate = target
    while candidate.exists():
        candidate = target.with_name(f"{target.stem} ({counter}){target.suffix}")
        counter += 1
    return candidate


def place_file(source_path: Path, library_root: Path, track: TrackForLibrary, duplicate_policy: str = "SKIP") -> PlacementResult:
    source_path = Path(source_path)
    target = build_library_path(Path(library_root), track)

    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(target))
        return PlacementResult(target, "MOVED", f"Added to library at {target}")

    if duplicate_policy == "SKIP":
        return PlacementResult(None, "SKIP", f"Skipped: {target} already exists.")

    if duplicate_policy == "KEEP_BOTH":
        new_target = _keep_both_path(target)
        new_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(new_target))
        return PlacementResult(new_target, "KEEP_BOTH", f"Existing file kept; new file saved as {new_target}")

    if duplicate_policy == "COMPARE":
        identical = filecmp.cmp(str(source_path), str(target), shallow=False)
        if identical:
            return PlacementResult(target, "COMPARE_IDENTICAL", "Downloaded file is identical to the existing library file; nothing changed.")
        new_target = _keep_both_path(target)
        new_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(new_target))
        return PlacementResult(
            new_target,
            "COMPARE_DIFFERENT",
            f"Existing file differs from the new download. Existing file kept at {target}; "
            f"new file saved separately at {new_target} for manual comparison.",
        )

    raise ValueError(f"Unknown duplicate_policy: {duplicate_policy}")
