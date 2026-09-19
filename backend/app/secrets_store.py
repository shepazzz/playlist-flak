"""Optional Windows Credential Manager backed secret storage.

Never stores or logs secrets in plaintext anywhere in this repo. `.env` is
the primary secret source (git-ignored); `keyring` is an optional secondary
source so a user can put the slskd API key / Spotify client secret in
Windows Credential Manager instead of a plaintext file.
"""
from __future__ import annotations

SERVICE_NAME = "PlaylistFlacManager"


def get_secret(name: str) -> str | None:
    try:
        import keyring
    except ImportError:
        return None
    try:
        return keyring.get_password(SERVICE_NAME, name)
    except Exception:
        # Keyring backend unavailable (e.g. headless Linux CI) - not fatal,
        # .env remains the source of truth in that case.
        return None


def set_secret(name: str, value: str) -> None:
    import keyring

    keyring.set_password(SERVICE_NAME, name, value)
