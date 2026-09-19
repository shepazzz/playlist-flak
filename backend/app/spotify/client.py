"""Spotify Web API client — METADATA ONLY.

This module never requests, streams, downloads, or caches Spotify audio.
It only calls the Playlists endpoint to read track metadata (artist,
title, album, album artist, release year, track/disc number, ISRC,
duration, Spotify URL) as explicitly scoped by the project brief.

Uses the Client Credentials flow (app-only auth), which is sufficient for
public/unlisted playlists. Private playlists would require the
Authorization Code flow (a documented future extension - see
IMPLEMENTATION_PLAN.md).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"

_PLAYLIST_URL_RE = re.compile(r"playlist[:/]([a-zA-Z0-9]{22})")


class SpotifyError(RuntimeError):
    pass


@dataclass
class SpotifyTrackMetadata:
    spotify_id: str
    artist: str
    title: str
    album: str | None
    album_artist: str | None
    release_year: int | None
    track_number: int | None
    disc_number: int | None
    duration_ms: int | None
    isrc: str | None
    spotify_url: str | None


def extract_playlist_id(playlist_url: str) -> str:
    match = _PLAYLIST_URL_RE.search(playlist_url.strip())
    if not match:
        raise SpotifyError(f"Could not extract a playlist id from: {playlist_url}")
    return match.group(1)


class SpotifyClient:
    def __init__(self, client_id: str, client_secret: str, http: httpx.Client | None = None):
        if not client_id or not client_secret:
            raise SpotifyError("Spotify client id/secret not configured (set SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET)")
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=15.0)
        self._token: str | None = None
        self._token_expiry: float = 0.0

    def _ensure_token(self) -> str:
        if self._token and time.monotonic() < self._token_expiry:
            return self._token
        resp = self._http.post(
            _TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._client_id, self._client_secret),
        )
        if resp.status_code >= 400:
            raise SpotifyError(f"Spotify auth failed: {resp.status_code} {resp.text}")
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.monotonic() + data.get("expires_in", 3600) - 30
        return self._token

    def _get(self, path: str, params: dict | None = None) -> dict:
        token = self._ensure_token()
        resp = self._http.get(
            f"{_API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        if resp.status_code >= 400:
            raise SpotifyError(f"Spotify API error: {resp.status_code} {resp.text[:300]}")
        return resp.json()

    def get_playlist_tracks(self, playlist_url: str) -> list[SpotifyTrackMetadata]:
        playlist_id = extract_playlist_id(playlist_url)
        results: list[SpotifyTrackMetadata] = []

        path = f"/playlists/{playlist_id}/tracks"
        params = {
            "limit": 100,
            "fields": (
                "next,items(track(id,name,duration_ms,track_number,disc_number,"
                "external_ids,external_urls,artists(name),"
                "album(name,release_date,artists(name))))"
            ),
        }

        while path:
            data = self._get(path, params=params if path.startswith("/playlists") else None)
            for item in data.get("items", []):
                track = item.get("track")
                if not track or not track.get("id"):
                    continue  # local file / unavailable track - skip
                results.append(self._to_metadata(track))

            next_url = data.get("next")
            if next_url:
                path = next_url.replace(_API_BASE, "")
                params = None
            else:
                path = ""

        return results

    @staticmethod
    def _to_metadata(track: dict) -> SpotifyTrackMetadata:
        artists = track.get("artists") or []
        album = track.get("album") or {}
        album_artists = album.get("artists") or []
        release_date = album.get("release_date") or ""
        release_year = None
        if release_date[:4].isdigit():
            release_year = int(release_date[:4])

        return SpotifyTrackMetadata(
            spotify_id=track["id"],
            artist=", ".join(a["name"] for a in artists) if artists else "",
            title=track.get("name") or "",
            album=album.get("name"),
            album_artist=album_artists[0]["name"] if album_artists else None,
            release_year=release_year,
            track_number=track.get("track_number"),
            disc_number=track.get("disc_number"),
            duration_ms=track.get("duration_ms"),
            isrc=(track.get("external_ids") or {}).get("isrc"),
            spotify_url=(track.get("external_urls") or {}).get("spotify"),
        )

    def close(self) -> None:
        self._http.close()
