from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class TrackOut(BaseModel):
    id: str
    playlist_id: str
    position: int
    raw_line: str
    artist: str | None
    title: str | None
    album: str | None
    album_artist: str | None
    version_tag: str | None
    release_year: int | None
    track_number: int | None
    disc_number: int | None
    duration_ms: int | None
    isrc: str | None
    spotify_url: str | None
    status: str
    status_reason: str | None
    best_match_score: float | None = None
    best_source_score: float | None = None
    best_format: str | None = None
    best_size_bytes: int | None = None

    model_config = {"from_attributes": True}


class CandidateOut(BaseModel):
    id: str
    track_id: str
    username: str
    filename: str
    remote_path: str
    extension: str | None
    size_bytes: int | None
    bitrate_kbps: int | None
    sample_rate_hz: int | None
    bit_depth: int | None
    duration_sec: float | None
    is_free_upload_slot: bool
    queue_length: int
    upload_speed_bps: int | None
    sibling_file_count: int
    match_score: float
    source_score: float
    review_required: bool
    review_reason: str | None

    model_config = {"from_attributes": True}


class DownloadOut(BaseModel):
    id: str
    candidate_id: str
    state: str
    error: str | None
    queued_at: dt.datetime
    completed_at: dt.datetime | None

    model_config = {"from_attributes": True}


class LibraryFileOut(BaseModel):
    id: str
    download_id: str
    local_path: str
    library_path: str | None
    verification_state: str
    verification_notes: str | None
    codec: str | None
    sample_rate_hz: int | None
    bit_depth: int | None
    channels: int | None
    duration_sec: float | None
    size_bytes: int | None

    model_config = {"from_attributes": True}


class ImportTextRequest(BaseModel):
    text: str


class ImportSpotifyRequest(BaseModel):
    playlist_url: str


class ApproveRequest(BaseModel):
    candidate_id: str


class LogEntryOut(BaseModel):
    id: str
    track_id: str | None
    message: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class SettingsOut(BaseModel):
    strict_flac_only: bool
    mode: str
    duplicate_policy: str
    rewrite_metadata: bool
    search_rate_limit_per_minute: int


class SettingsUpdate(BaseModel):
    strict_flac_only: bool | None = None
    mode: str | None = None
    duplicate_policy: str | None = None
    rewrite_metadata: bool | None = None
    search_rate_limit_per_minute: int | None = None
