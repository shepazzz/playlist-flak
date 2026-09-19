"""slskd HTTP adapter — the ONLY place in this project that talks to slskd.

Endpoints confirmed against slskd `master` source (SearchesController.cs,
TransfersController.cs, UsersController.cs) and cross-checked with the
third-party `slskd-api` Python client and slskd's own docs/config.md
(auth). See ARCHITECTURE.md §1 for citations and the version-skew note on
the downloads/uploads path.

Auth: `X-API-Key` header (preferred, configured in slskd's
`web.authentication.api_keys`) or username/password -> `POST /session` ->
bearer token (used when no API key is configured).

All parsing here is defensive (`dict.get`) since exact field availability
depends on the peer client and the slskd version.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from app.config import Settings


class SlskdError(RuntimeError):
    pass


class SlskdClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self._settings = settings
        self._client = client or httpx.Client(timeout=20.0)
        self._bearer_token: str | None = None

    # -- internal helpers -------------------------------------------------

    def _url(self, path: str) -> str:
        return self._settings.slskd_api_url(path)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._settings.slskd_api_key:
            headers["X-API-Key"] = self._settings.slskd_api_key
        elif self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    def _ensure_session(self) -> None:
        if self._settings.slskd_api_key or self._bearer_token:
            return
        if not (self._settings.slskd_username and self._settings.slskd_password):
            raise SlskdError(
                "No slskd API key and no username/password configured; "
                "set SLSKD_API_KEY or SLSKD_USERNAME/SLSKD_PASSWORD in .env"
            )
        resp = self._client.post(
            self._url("/session"),
            json={"username": self._settings.slskd_username, "password": self._settings.slskd_password},
        )
        if resp.status_code >= 400:
            raise SlskdError(f"slskd login failed: {resp.status_code} {resp.text}")
        data = resp.json()
        self._bearer_token = data.get("token") or data.get("access_token")

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        self._ensure_session()
        resp = self._client.request(method, self._url(path), headers=self._headers(), **kwargs)
        if resp.status_code >= 400:
            raise SlskdError(f"slskd {method} {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp

    # -- searches -----------------------------------------------------------

    def search(self, query: str, search_id: str | None = None) -> str:
        """Start a search. Returns the search id."""
        search_id = search_id or str(uuid.uuid4())
        self._request(
            "POST",
            self._settings.slskd_searches_path,
            json={"id": search_id, "searchText": query},
        )
        return search_id

    def get_search(self, search_id: str) -> dict[str, Any]:
        resp = self._request("GET", f"{self._settings.slskd_searches_path}/{search_id}")
        return resp.json()

    def get_search_results(self, search_id: str) -> list[dict[str, Any]]:
        """Return the list of per-peer search responses for a search id."""
        resp = self._request("GET", f"{self._settings.slskd_searches_path}/{search_id}/responses")
        data = resp.json()
        return data if isinstance(data, list) else data.get("responses", [])

    def wait_for_search(self, search_id: str, timeout_sec: float = 8.0, poll_interval: float = 0.5) -> dict[str, Any]:
        """Poll until slskd reports the search as no longer running, or timeout."""
        deadline = time.monotonic() + timeout_sec
        state: dict[str, Any] = {}
        while time.monotonic() < deadline:
            state = self.get_search(search_id)
            if str(state.get("state", "")).lower() not in ("inprogress", "in_progress", "pending", ""):
                break
            time.sleep(poll_interval)
        return state

    def cancel_search(self, search_id: str) -> None:
        self._request("PUT", f"{self._settings.slskd_searches_path}/{search_id}")

    def delete_search(self, search_id: str) -> None:
        self._request("DELETE", f"{self._settings.slskd_searches_path}/{search_id}")

    # -- users ----------------------------------------------------------------

    def get_user_status(self, username: str) -> dict[str, Any]:
        resp = self._request("GET", f"{self._settings.slskd_users_path}/{username}/status")
        return resp.json()

    # -- transfers / downloads --------------------------------------------------

    def enqueue_authorized_file(self, username: str, files: list[dict[str, Any]]) -> dict[str, Any]:
        """Hand off one or more files the user explicitly approved to slskd.

        `files` items are the raw file dicts from a search response
        (must include at least `filename` and `size`), per slskd's own
        documented usage ("a list of files ... obtained from search
        responses").
        """
        resp = self._request(
            "POST",
            f"{self._settings.slskd_downloads_path}/{username}",
            json=files,
        )
        return {"status_code": resp.status_code}

    def get_downloads(self, username: str | None = None, include_removed: bool = False) -> list[dict[str, Any]]:
        path = self._settings.slskd_downloads_path
        if username:
            path = f"{path}/{username}"
        resp = self._request("GET", path, params={"includeRemoved": str(include_removed).lower()})
        data = resp.json()
        return data if isinstance(data, list) else [data]

    def get_download_status(self, username: str, transfer_id: str) -> dict[str, Any]:
        resp = self._request("GET", f"{self._settings.slskd_downloads_path}/{username}/{transfer_id}")
        return resp.json()

    def cancel_download(self, username: str, transfer_id: str, remove: bool = False) -> None:
        self._request(
            "DELETE",
            f"{self._settings.slskd_downloads_path}/{username}/{transfer_id}",
            params={"remove": str(remove).lower()},
        )

    def retry_download(self, username: str, transfer_id: str, file: dict[str, Any]) -> dict[str, Any]:
        """slskd has no native "retry" endpoint; we cancel+remove the failed
        transfer and re-enqueue the same file."""
        try:
            self.cancel_download(username, transfer_id, remove=True)
        except SlskdError:
            pass
        return self.enqueue_authorized_file(username, [file])

    def close(self) -> None:
        self._client.close()
