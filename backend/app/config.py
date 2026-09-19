"""Application configuration.

Secrets (slskd API key, Spotify client secret) are never hardcoded and never
committed. They are read from environment variables / a local `.env` file
first, falling back to the OS credential store (Windows Credential Manager
via `keyring`) when available. See secrets_store.py.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.secrets_store import get_secret

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), env_prefix="", extra="ignore")

    # --- slskd connection ---
    slskd_base_url: str = "http://localhost:5030"
    # slskd's API root has moved historically; keep it configurable instead
    # of hardcoding a path we can't verify against the user's exact version.
    slskd_api_base_path: str = "/api/v0"
    slskd_api_key: str | None = None
    slskd_username: str | None = None
    slskd_password: str | None = None
    # slskd's transfers routes have moved between "/downloads" and
    # "/transfers/downloads" across versions/forks; keep the segment
    # configurable rather than guessing (spec §24: never invent endpoints).
    # Default matches the route table read directly from slskd's
    # TransfersController.cs on `master` at research time — verify against
    # your instance's /swagger and adjust if it differs.
    slskd_downloads_path: str = "/downloads"
    slskd_uploads_path: str = "/uploads"
    slskd_searches_path: str = "/searches"
    slskd_users_path: str = "/users"

    # --- Spotify (metadata only, Client Credentials flow) ---
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None

    # --- storage ---
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'app.db'}"
    library_root: str = str(PROJECT_ROOT / "data" / "Music")
    downloads_incoming_dir: str = str(PROJECT_ROOT / "data" / "incoming")

    # --- behaviour ---
    strict_flac_only: bool = True
    mode: str = "SAFE"  # SAFE | ASSISTED
    duplicate_policy: str = "SKIP"  # SKIP | COMPARE | KEEP_BOTH
    rewrite_metadata: bool = False
    search_rate_limit_per_minute: int = 12
    download_status_poll_seconds: int = 5

    def slskd_api_url(self, path: str) -> str:
        return f"{self.slskd_base_url.rstrip('/')}{self.slskd_api_base_path}{path}"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Fall back to keyring (Windows Credential Manager) for secrets that
    # were not supplied via environment/.env.
    if not settings.slskd_api_key:
        settings.slskd_api_key = get_secret("slskd_api_key")
    if not settings.spotify_client_secret:
        settings.spotify_client_secret = get_secret("spotify_client_secret")
    return settings
