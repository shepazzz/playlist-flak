"""Plugin interface (spec §21): the app is never permanently coupled to
Soulseek. Everything above this boundary (matcher, scoring, orchestration,
API routes) only knows about these dataclasses + the abstract interface —
never a slskd-specific type.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawCandidate:
    """One remote file a provider found for a search query."""

    provider: str
    username: str
    remote_path: str
    filename: str
    extension: str | None
    size_bytes: int | None
    bitrate_kbps: int | None = None
    sample_rate_hz: int | None = None
    bit_depth: int | None = None
    duration_sec: float | None = None
    is_free_upload_slot: bool = False
    queue_length: int = 0
    upload_speed_bps: int | None = None
    sibling_file_count: int = 1
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DownloadHandle:
    provider: str
    username: str
    remote_path: str
    provider_download_id: str | None = None


@dataclass
class DownloadStatus:
    state: str  # QUEUED | DOWNLOADING | COMPLETED | FAILED | CANCELLED
    bytes_transferred: int | None = None
    total_bytes: int | None = None
    error: str | None = None
    local_path: str | None = None


class MusicSourceProvider(ABC):
    """A source the app can search and (with authorization) download from."""

    name: str

    @abstractmethod
    def search(self, query: str) -> str:
        """Start a search, return an opaque handle/id."""

    @abstractmethod
    def get_candidates(self, handle: str) -> list[RawCandidate]:
        """Return the (possibly partial) results for a prior search()."""

    @abstractmethod
    def request_download(self, candidate: RawCandidate) -> DownloadHandle:
        """Enqueue an authorized download for a candidate the user approved."""

    @abstractmethod
    def status(self, download: DownloadHandle) -> DownloadStatus:
        """Poll the current state of a previously requested download."""

    @abstractmethod
    def cancel(self, download: DownloadHandle) -> None:
        """Cancel a queued/in-progress download."""
