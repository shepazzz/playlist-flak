from __future__ import annotations

from app.providers.base import DownloadHandle, DownloadStatus, MusicSourceProvider, RawCandidate


class FakeProvider(MusicSourceProvider):
    """In-memory MusicSourceProvider for tests - no network involved."""

    name = "fake"

    def __init__(self):
        self.responses: dict[str, list[RawCandidate]] = {}
        self.download_states: dict[str, str] = {}
        self._next_search_id = 0

    def add_response(self, query: str, candidates: list[RawCandidate]) -> None:
        self.responses[query] = candidates

    def search(self, query: str) -> str:
        self._next_search_id += 1
        handle = f"search-{self._next_search_id}:{query}"
        return handle

    def get_candidates(self, handle: str) -> list[RawCandidate]:
        _, _, query = handle.partition(":")
        return self.responses.get(query, [])

    def request_download(self, candidate: RawCandidate) -> DownloadHandle:
        key = f"{candidate.username}:{candidate.remote_path}"
        self.download_states[key] = "QUEUED"
        return DownloadHandle(provider=self.name, username=candidate.username, remote_path=candidate.remote_path, provider_download_id=key)

    def status(self, download: DownloadHandle) -> DownloadStatus:
        state = self.download_states.get(download.provider_download_id, "QUEUED")
        return DownloadStatus(state=state)

    def cancel(self, download: DownloadHandle) -> None:
        self.download_states[download.provider_download_id] = "CANCELLED"

    def set_state(self, download_id: str, state: str) -> None:
        self.download_states[download_id] = state
