"""Runtime-adjustable settings (spec §6/§16). These apply immediately for
the running process; persistent defaults still come from `.env` (they
reset to the `.env` values on restart - this is a documented MVP
simplification, see README).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.config import Settings
from app.logging_utils import log_event
from app.schemas import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])

_VALID_MODES = {"SAFE", "ASSISTED"}
_VALID_DUP_POLICIES = {"SKIP", "COMPARE", "KEEP_BOTH"}


@router.get("", response_model=SettingsOut)
def get_settings_(settings: Settings = Depends(get_app_settings)):
    return SettingsOut(
        strict_flac_only=settings.strict_flac_only,
        mode=settings.mode,
        duplicate_policy=settings.duplicate_policy,
        rewrite_metadata=settings.rewrite_metadata,
        search_rate_limit_per_minute=settings.search_rate_limit_per_minute,
    )


@router.put("", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db), settings: Settings = Depends(get_app_settings)):
    if payload.mode is not None:
        if payload.mode not in _VALID_MODES:
            payload.mode = None
        else:
            settings.mode = payload.mode
    if payload.duplicate_policy is not None and payload.duplicate_policy in _VALID_DUP_POLICIES:
        settings.duplicate_policy = payload.duplicate_policy
    if payload.strict_flac_only is not None:
        settings.strict_flac_only = payload.strict_flac_only
    if payload.rewrite_metadata is not None:
        settings.rewrite_metadata = payload.rewrite_metadata
    if payload.search_rate_limit_per_minute is not None and payload.search_rate_limit_per_minute > 0:
        settings.search_rate_limit_per_minute = payload.search_rate_limit_per_minute

    log_event(db, f"Settings updated: mode={settings.mode}, strict_flac_only={settings.strict_flac_only}, duplicate_policy={settings.duplicate_policy}")
    return SettingsOut(
        strict_flac_only=settings.strict_flac_only,
        mode=settings.mode,
        duplicate_policy=settings.duplicate_policy,
        rewrite_metadata=settings.rewrite_metadata,
        search_rate_limit_per_minute=settings.search_rate_limit_per_minute,
    )
