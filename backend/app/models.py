from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> dt.datetime:
    return dt.datetime.utcnow()


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(16))  # text | csv | txt | spotify
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    tracks: Mapped[list["Track"]] = relationship(back_populates="playlist", cascade="all, delete-orphan")


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    playlist_id: Mapped[str] = mapped_column(ForeignKey("playlists.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)

    raw_line: Mapped[str] = mapped_column(Text)

    artist: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    album: Mapped[str | None] = mapped_column(String(512), nullable=True)
    album_artist: Mapped[str | None] = mapped_column(String(512), nullable=True)
    version_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    track_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disc_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    isrc: Mapped[str | None] = mapped_column(String(32), nullable=True)
    spotify_url: Mapped[str | None] = mapped_column(String(256), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="IMPORTED")
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    playlist: Mapped[Playlist] = relationship(back_populates="tracks")
    searches: Mapped[list["Search"]] = relationship(back_populates="track", cascade="all, delete-orphan")
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="track", cascade="all, delete-orphan")


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    track_id: Mapped[str] = mapped_column(ForeignKey("tracks.id"))
    provider: Mapped[str] = mapped_column(String(32), default="slskd")
    query_text: Mapped[str] = mapped_column(String(512))
    provider_search_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_response_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    track: Mapped[Track] = relationship(back_populates="searches")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    track_id: Mapped[str] = mapped_column(ForeignKey("tracks.id"))
    search_id: Mapped[str | None] = mapped_column(ForeignKey("searches.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), default="slskd")

    username: Mapped[str] = mapped_column(String(128))
    remote_path: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(512))
    extension: Mapped[str | None] = mapped_column(String(16), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bitrate_kbps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_rate_hz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bit_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_free_upload_slot: Mapped[bool] = mapped_column(Boolean, default=False)
    queue_length: Mapped[int] = mapped_column(Integer, default=0)
    upload_speed_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sibling_file_count: Mapped[int] = mapped_column(Integer, default=1)

    match_score: Mapped[float] = mapped_column(Float, default=0)
    source_score: Mapped[float] = mapped_column(Float, default=0)
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    track: Mapped[Track] = relationship(back_populates="candidates")
    download: Mapped["Download"] = relationship(back_populates="candidate", uselist=False)


class Download(Base):
    __tablename__ = "downloads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))
    provider: Mapped[str] = mapped_column(String(32), default="slskd")
    provider_download_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    state: Mapped[str] = mapped_column(String(32), default="QUEUED")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    queued_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    candidate: Mapped[Candidate] = relationship(back_populates="download")
    file: Mapped["LibraryFile"] = relationship(back_populates="download", uselist=False)


class LibraryFile(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    download_id: Mapped[str] = mapped_column(ForeignKey("downloads.id"))

    local_path: Mapped[str] = mapped_column(Text)
    library_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    verification_state: Mapped[str] = mapped_column(String(16), default="unverified")  # likely_ok | suspicious | invalid | unverified
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    codec: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sample_rate_hz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bit_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    download: Mapped[Download] = relationship(back_populates="file")


class AppSetting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    track_id: Mapped[str | None] = mapped_column(ForeignKey("tracks.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
