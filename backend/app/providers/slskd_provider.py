"""SlskdProvider: the first MusicSourceProvider implementation (spec §21).

Translates slskd's raw JSON (peer search responses + file lists) into the
provider-agnostic RawCandidate/DownloadHandle/DownloadStatus dataclasses.
No other module in the app should import slskd_client directly.
"""
from __future__ import annotations

import posixpath
from typing import Any

from app.config import Settings
from app.providers.base import DownloadHandle, DownloadStatus, MusicSourceProvider, RawCandidate
from app.providers.slskd_client import SlskdClient, SlskdError

_TERMINAL_STATES = {"completed", "succeeded", "errored", "failed", "cancelled", "canceled", "rejected"}


def _first(d: dict[str, Any], *keys: str, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _remote_dir(remote_path: str) -> str:
    normalized = remote_path.replace("\\", "/")
    return posixpath.dirname(normalized)


def _file_to_candidate(provider: str, peer: dict[str, Any], file: dict[str, Any], sibling_count: int) -> RawCandidate:
    filename_full = _first(file, "filename", "fileName", default="")
    base_name = filename_full.replace("\\", "/").rsplit("/", 1)[-1]
    extension = _first(file, "extension") or (base_name.rsplit(".", 1)[-1] if "." in base_name else None)

    return RawCandidate(
        provider=provider,
        username=_first(peer, "username", default=""),
        remote_path=filename_full,
        filename=base_name,
        extension=extension.lower() if extension else None,
        size_bytes=_first(file, "size", "fileSize"),
        bitrate_kbps=_first(file, "bitRate", "bitrate"),
        sample_rate_hz=_first(file, "sampleRate"),
        bit_depth=_first(file, "bitDepth"),
        duration_sec=_first(file, "length", "duration"),
        is_free_upload_slot=bool(_first(peer, "hasFreeUploadSlot", "freeUploadSlots", default=False)),
        queue_length=int(_first(peer, "queueLength", default=0) or 0),
        upload_speed_bps=_first(peer, "uploadSpeed"),
        sibling_file_count=sibling_count,
        raw={"peer": peer, "file": file},
    )


class SlskdProvider(MusicSourceProvider):
    name = "slskd"

    def __init__(self, settings: Settings, client: SlskdClient | None = None):
        self._settings = settings
        self._client = client or SlskdClient(settings)

    def search(self, query: str) -> str:
        return self._client.search(query)

    def get_candidates(self, handle: str) -> list[RawCandidate]:
        self._client.wait_for_search(handle, timeout_sec=8.0)
        responses = self._client.get_search_results(handle)

        candidates: list[RawCandidate] = []
        for peer in responses:
            files = peer.get("files") or []
            dir_counts: dict[str, int] = {}
            for f in files:
                d = _remote_dir(_first(f, "filename", "fileName", default=""))
                dir_counts[d] = dir_counts.get(d, 0) + 1
            for f in files:
                d = _remote_dir(_first(f, "filename", "fileName", default=""))
                candidates.append(_file_to_candidate(self.name, peer, f, dir_counts.get(d, 1)))
        return candidates

    def request_download(self, candidate: RawCandidate) -> DownloadHandle:
        file_payload = {"filename": candidate.remote_path, "size": candidate.size_bytes or 0}
        self._client.enqueue_authorized_file(candidate.username, [file_payload])

        transfer_id = self._find_transfer_id(candidate.username, candidate.remote_path)
        return DownloadHandle(
            provider=self.name,
            username=candidate.username,
            remote_path=candidate.remote_path,
            provider_download_id=transfer_id,
        )

    def _find_transfer_id(self, username: str, remote_path: str) -> str | None:
        try:
            downloads = self._client.get_downloads(username=username, include_removed=True)
        except SlskdError:
            return None
        for group in downloads:
            for d in group.get("directories", [group]) if isinstance(group, dict) else []:
                for f in d.get("files", []) if isinstance(d, dict) else []:
                    if _first(f, "filename", "fileName") == remote_path:
                        return _first(f, "id")
        return None

    def status(self, download: DownloadHandle) -> DownloadStatus:
        if not download.provider_download_id:
            download.provider_download_id = self._find_transfer_id(download.username, download.remote_path)
        if not download.provider_download_id:
            return DownloadStatus(state="QUEUED")

        try:
            data = self._client.get_download_status(download.username, download.provider_download_id)
        except SlskdError as e:
            return DownloadStatus(state="FAILED", error=str(e))

        raw_state = str(_first(data, "state", default="")).lower()
        if "completed" in raw_state and "succeeded" in raw_state or raw_state == "completed,succeeded":
            state = "COMPLETED"
        elif "completed" in raw_state and ("errored" in raw_state or "failed" in raw_state):
            state = "FAILED"
        elif "cancel" in raw_state:
            state = "CANCELLED"
        elif "inprogress" in raw_state or "downloading" in raw_state:
            state = "DOWNLOADING"
        else:
            state = "QUEUED"

        return DownloadStatus(
            state=state,
            bytes_transferred=_first(data, "bytesTransferred"),
            total_bytes=_first(data, "size"),
            local_path=_first(data, "filename"),
            error=_first(data, "exception"),
        )

    def cancel(self, download: DownloadHandle) -> None:
        if download.provider_download_id:
            self._client.cancel_download(download.username, download.provider_download_id, remove=True)
