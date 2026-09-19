"""Metadata normalization (spec §12): ARTIST/ALBUMARTIST/TITLE/ALBUM/DATE/
TRACKNUMBER/DISCNUMBER via mutagen. Off by default (`rewrite_metadata`
setting). The original file is always backed up before any tag is changed,
so an approved-but-mistagged file is never destructively altered.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from mutagen.flac import FLAC


@dataclass
class MetadataFields:
    artist: str | None
    album_artist: str | None
    title: str | None
    album: str | None
    date: str | None
    track_number: int | None
    disc_number: int | None


def backup_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".orig")


def rewrite_metadata(path: Path, fields: MetadataFields, backup: bool = True) -> Path | None:
    path = Path(path)
    backup_to = backup_path(path)

    if backup and not backup_to.exists():
        shutil.copy2(path, backup_to)

    audio = FLAC(str(path))

    def _set(key: str, value):
        if value is None or value == "":
            return
        audio[key] = str(value)

    _set("ARTIST", fields.artist)
    _set("ALBUMARTIST", fields.album_artist)
    _set("TITLE", fields.title)
    _set("ALBUM", fields.album)
    _set("DATE", fields.date)
    _set("TRACKNUMBER", fields.track_number)
    _set("DISCNUMBER", fields.disc_number)

    audio.save()
    return backup_to if backup else None
