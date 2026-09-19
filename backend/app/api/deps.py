from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.database import get_db  # noqa: F401 re-exported for routers
from app.providers.base import MusicSourceProvider
from app.providers.slskd_client import SlskdClient
from app.providers.slskd_provider import SlskdProvider


@lru_cache
def get_provider() -> MusicSourceProvider:
    settings = get_settings()
    return SlskdProvider(settings, SlskdClient(settings))


def get_app_settings() -> Settings:
    return get_settings()
