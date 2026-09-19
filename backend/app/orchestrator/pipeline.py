"""Per-track pipeline: import -> search -> match -> approve -> download ->
verify -> organize. This module is pure DB + provider orchestration logic
so it's testable with a fake MusicSourceProvider (no real slskd needed).

Status machine (spec §14):
IMPORTED -> SEARCHING -> MATCHED | REVIEW_REQUIRED | NOT_FOUND | LOCAL_MATCH
MATCHED/REVIEW_REQUIRED -(user approves)-> QUEUED -> DOWNLOADING -> VERIFYING
-> COMPLETED | FAILED
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.library.metadata_writer import MetadataFields, rewrite_metadata
from app.library.organizer import TrackForLibrary, place_file
from app.logging_utils import log_event
from app.matching.scorer import flag_ambiguous, score_candidate
from app.matching.source_score import score_source
from app.models import Candidate, Download, LibraryFile, Playlist, Search, Track
from app.parsing.normalizer import normalize_track
from app.parsing.track_parser import RawTrackLine, parse_csv_or_txt, parse_text
from app.providers.base import DownloadHandle, MusicSourceProvider, RawCandidate
from app.search.query_builder import build_queries
from app.spotify.client import SpotifyClient
from app.verification.flac_verifier import verify_file


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def _track_from_raw(playlist_id: str, position: int, line: RawTrackLine) -> Track:
    has_artist_title = bool(line.artist and line.title)
    status = "IMPORTED" if has_artist_title else "REVIEW_REQUIRED"
    reason = None if has_artist_title else "Could not split this line into Artist/Track - edit it manually."
    version_tag = None
    if has_artist_title:
        version_tag = normalize_track(line.artist, line.title).version

    return Track(
        playlist_id=playlist_id,
        position=position,
        raw_line=line.raw_line,
        artist=line.artist,
        title=line.title,
        album=line.album,
        version_tag=version_tag,
        status=status,
        status_reason=reason,
    )


def import_text(db: Session, text: str) -> Playlist:
    lines = parse_text(text)
    playlist = Playlist(source="text", source_ref=None)
    db.add(playlist)
    db.flush()
    for i, line in enumerate(lines):
        db.add(_track_from_raw(playlist.id, i, line))
    db.commit()
    log_event(db, f"Imported {len(lines)} track(s) from pasted text.")
    return playlist


def import_file(db: Session, filename: str, content: bytes) -> Playlist:
    lines = parse_csv_or_txt(filename, content)
    source = "csv" if filename.lower().endswith(".csv") else "txt"
    playlist = Playlist(source=source, source_ref=filename)
    db.add(playlist)
    db.flush()
    for i, line in enumerate(lines):
        db.add(_track_from_raw(playlist.id, i, line))
    db.commit()
    log_event(db, f"Imported {len(lines)} track(s) from {filename}.")
    return playlist


def import_spotify(db: Session, playlist_url: str, spotify_client: SpotifyClient) -> Playlist:
    tracks_meta = spotify_client.get_playlist_tracks(playlist_url)
    playlist = Playlist(source="spotify", source_ref=playlist_url)
    db.add(playlist)
    db.flush()

    for i, m in enumerate(tracks_meta):
        version_tag = normalize_track(m.artist, m.title).version
        db.add(
            Track(
                playlist_id=playlist.id,
                position=i,
                raw_line=f"{m.artist} - {m.title}",
                artist=m.artist,
                title=m.title,
                album=m.album,
                album_artist=m.album_artist,
                version_tag=version_tag,
                release_year=m.release_year,
                track_number=m.track_number,
                disc_number=m.disc_number,
                duration_ms=m.duration_ms,
                isrc=m.isrc,
                spotify_url=m.spotify_url,
                status="IMPORTED",
            )
        )
    db.commit()
    log_event(db, f"Imported {len(tracks_meta)} track(s) from Spotify playlist.")
    return playlist


# ---------------------------------------------------------------------------
# Duplicate detection (spec §17)
# ---------------------------------------------------------------------------


def find_local_match(db: Session, track: Track) -> Track | None:
    norm = normalize_track(track.artist, track.title, track.album)
    others = (
        db.query(Track)
        .filter(Track.status == "COMPLETED", Track.id != track.id)
        .all()
    )
    for other in others:
        other_norm = normalize_track(other.artist, other.title, other.album)
        if other_norm.artist != norm.artist or other_norm.title != norm.title:
            continue
        if track.duration_ms and other.duration_ms and abs(track.duration_ms - other.duration_ms) > 5000:
            continue
        return other
    return None


# ---------------------------------------------------------------------------
# Search + match
# ---------------------------------------------------------------------------


def search_track(db: Session, track_id: str, provider: MusicSourceProvider, settings: Settings) -> Track:
    track = db.get(Track, track_id)
    if track is None:
        raise ValueError(f"Track {track_id} not found")

    local = find_local_match(db, track)
    if local is not None:
        track.status = "LOCAL_MATCH"
        track.status_reason = f"Already present in the library (matches track {local.id})."
        db.commit()
        log_event(db, "Already in local library - skipping Soulseek search.", track_id=track.id)
        return track

    if not track.artist or not track.title:
        track.status = "REVIEW_REQUIRED"
        track.status_reason = track.status_reason or "Missing artist/title - cannot search."
        db.commit()
        return track

    track.status = "SEARCHING"
    db.commit()
    log_event(db, "Searching Soulseek...", track_id=track.id)

    norm = normalize_track(track.artist, track.title, track.album)
    queries = build_queries(norm, settings.strict_flac_only)

    scored_pairs: list[tuple[Candidate, "ScoredCandidate"]] = []  # noqa: F821
    used_query = None

    for query in queries:
        try:
            handle = provider.search(query)
            search_row = Search(track_id=track.id, provider=provider.name, query_text=query, provider_search_id=handle)
            db.add(search_row)
            db.flush()

            raw_candidates: list[RawCandidate] = provider.get_candidates(handle)
        except Exception as e:  # noqa: BLE001 - never leave a track stuck in SEARCHING on a provider error
            db.rollback()
            track.status = "FAILED"
            track.status_reason = f"Search failed: {e}"
            db.commit()
            log_event(db, f"Search failed: {e}", track_id=track.id)
            return track

        search_row.raw_response_count = len(raw_candidates)

        if settings.strict_flac_only:
            raw_candidates = [c for c in raw_candidates if (c.extension or "").lower() == "flac"]

        if not raw_candidates:
            db.commit()
            continue

        used_query = query
        log_event(db, f"{len(raw_candidates)} candidate(s) found for query '{query}'.", track_id=track.id)

        for rc in raw_candidates:
            scored = score_candidate(
                norm, rc, expected_duration_ms=track.duration_ms, strict_flac_only=settings.strict_flac_only
            )
            src_score = score_source(norm, rc)
            cand_row = Candidate(
                track_id=track.id,
                search_id=search_row.id,
                provider=provider.name,
                username=rc.username,
                remote_path=rc.remote_path,
                filename=rc.filename,
                extension=rc.extension,
                size_bytes=rc.size_bytes,
                bitrate_kbps=rc.bitrate_kbps,
                sample_rate_hz=rc.sample_rate_hz,
                bit_depth=rc.bit_depth,
                duration_sec=rc.duration_sec,
                is_free_upload_slot=rc.is_free_upload_slot,
                queue_length=rc.queue_length,
                upload_speed_bps=rc.upload_speed_bps,
                sibling_file_count=rc.sibling_file_count,
                match_score=scored.match_score,
                source_score=src_score,
                review_required=scored.review_required,
                review_reason=scored.review_reason,
            )
            db.add(cand_row)
            scored_pairs.append((cand_row, scored))
        db.commit()
        break  # first query variant that yields usable candidates wins (spec §3)

    if not scored_pairs:
        track.status = "NOT_FOUND"
        track.status_reason = (
            "No FLAC candidates found after trying all search variants."
            if settings.strict_flac_only
            else "No candidates found after trying all search variants."
        )
        db.commit()
        log_event(db, "No candidates found.", track_id=track.id)
        return track

    scored_only = [s for _, s in scored_pairs]
    flag_ambiguous(scored_only)
    for cand_row, scored in scored_pairs:
        cand_row.review_required = scored.review_required
        cand_row.review_reason = scored.review_reason

    best_row, best_scored = max(scored_pairs, key=lambda pair: pair[1].match_score)
    log_event(db, f"Best match {best_scored.match_score:.0f}% for query '{used_query}'.", track_id=track.id)

    if best_scored.review_required:
        track.status = "REVIEW_REQUIRED"
        track.status_reason = best_scored.review_reason
    else:
        track.status = "MATCHED"
        track.status_reason = None

    db.commit()
    return track


# ---------------------------------------------------------------------------
# Approval + download
# ---------------------------------------------------------------------------


def approve_candidate(db: Session, track_id: str, candidate_id: str, provider: MusicSourceProvider) -> Download:
    track = db.get(Track, track_id)
    candidate = db.get(Candidate, candidate_id)
    if track is None or candidate is None or candidate.track_id != track.id:
        raise ValueError("Track/candidate mismatch")

    raw_candidate = RawCandidate(
        provider=candidate.provider,
        username=candidate.username,
        remote_path=candidate.remote_path,
        filename=candidate.filename,
        extension=candidate.extension,
        size_bytes=candidate.size_bytes,
        bitrate_kbps=candidate.bitrate_kbps,
        sample_rate_hz=candidate.sample_rate_hz,
        bit_depth=candidate.bit_depth,
        duration_sec=candidate.duration_sec,
        is_free_upload_slot=candidate.is_free_upload_slot,
        queue_length=candidate.queue_length,
        upload_speed_bps=candidate.upload_speed_bps,
        sibling_file_count=candidate.sibling_file_count,
    )

    handle = provider.request_download(raw_candidate)
    download = Download(
        candidate_id=candidate.id,
        provider=provider.name,
        provider_download_id=handle.provider_download_id,
        state="QUEUED",
    )
    db.add(download)
    track.status = "QUEUED"
    track.status_reason = None
    db.commit()
    log_event(db, f"Approved candidate from '{candidate.username}'; handed off to {provider.name}.", track_id=track.id)
    return download


# ---------------------------------------------------------------------------
# Download polling + verification + library placement
# ---------------------------------------------------------------------------


def _locate_downloaded_file(root: Path, filename: str) -> Path | None:
    if not root.exists():
        return None
    matches = [p for p in root.rglob("*") if p.is_file() and p.name.lower() == filename.lower()]
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _finalize_download(db: Session, download: Download, candidate: Candidate, track: Track | None, settings: Settings) -> None:
    incoming_root = Path(settings.downloads_incoming_dir)
    local_file = _locate_downloaded_file(incoming_root, candidate.filename)

    if local_file is None:
        log_event(
            db,
            f"Could not locate downloaded file '{candidate.filename}' under {incoming_root} - "
            "check that this matches slskd's configured download directory.",
            track_id=track.id if track else None,
        )
        if track:
            track.status = "FAILED"
            track.status_reason = "Downloaded file not found on disk for verification."
            db.commit()
        return

    expected_ms = track.duration_ms if track else None
    verification = verify_file(local_file, expected_duration_ms=expected_ms)

    file_row = LibraryFile(
        download_id=download.id,
        local_path=str(local_file),
        verification_state=verification.state,
        verification_notes="; ".join(verification.notes) or None,
        codec=verification.codec,
        sample_rate_hz=verification.sample_rate_hz,
        bit_depth=verification.bit_depth,
        channels=verification.channels,
        duration_sec=verification.duration_sec,
        size_bytes=verification.size_bytes,
    )
    db.add(file_row)
    db.commit()
    log_event(db, f"FLAC verification: {verification.state.upper()}.", track_id=track.id if track else None)

    if verification.state == "invalid":
        if track:
            track.status = "FAILED"
            track.status_reason = "; ".join(verification.notes) or "File failed FLAC verification."
            db.commit()
        return

    if track and settings.rewrite_metadata:
        try:
            fields = MetadataFields(
                artist=track.artist,
                album_artist=track.album_artist,
                title=track.title,
                album=track.album,
                date=str(track.release_year) if track.release_year else None,
                track_number=track.track_number,
                disc_number=track.disc_number,
            )
            rewrite_metadata(local_file, fields, backup=True)
            log_event(db, "Metadata normalized (original backed up as .orig).", track_id=track.id)
        except Exception as e:  # noqa: BLE001 - metadata rewrite is best-effort, never fatal
            log_event(db, f"Metadata rewrite failed: {e}", track_id=track.id)

    if track:
        lib_track = TrackForLibrary(
            artist=track.artist or candidate.username,
            title=track.title or candidate.filename,
            album=track.album,
            album_artist=track.album_artist,
            release_year=track.release_year,
            track_number=track.track_number,
        )
    else:
        lib_track = TrackForLibrary(
            artist=candidate.username, title=candidate.filename, album=None, album_artist=None,
            release_year=None, track_number=None,
        )

    placement = place_file(local_file, Path(settings.library_root), lib_track, settings.duplicate_policy)
    file_row.library_path = str(placement.library_path) if placement.library_path else None
    db.commit()
    log_event(db, placement.message, track_id=track.id if track else None)

    if track:
        track.status = "COMPLETED"
        db.commit()
        log_event(db, "Added to library.", track_id=track.id)


def poll_downloads(db: Session, provider: MusicSourceProvider, settings: Settings) -> None:
    active = db.query(Download).filter(Download.state.in_(["QUEUED", "DOWNLOADING"])).all()

    for download in active:
        candidate = db.get(Candidate, download.candidate_id)
        if candidate is None:
            continue
        track = db.get(Track, candidate.track_id)

        handle = DownloadHandle(
            provider=download.provider,
            username=candidate.username,
            remote_path=candidate.remote_path,
            provider_download_id=download.provider_download_id,
        )
        try:
            status = provider.status(handle)
        except Exception as e:  # noqa: BLE001 - transient provider errors shouldn't crash the poller
            log_event(db, f"Status check failed, will retry: {e}", track_id=track.id if track else None)
            continue

        if status.state != download.state:
            download.state = status.state
            if track:
                if status.state == "DOWNLOADING":
                    track.status = "DOWNLOADING"
                elif status.state == "COMPLETED":
                    track.status = "VERIFYING"
                elif status.state in ("FAILED", "CANCELLED"):
                    track.status = "FAILED"
                    track.status_reason = status.error
            db.commit()
            log_event(db, f"Download {status.state.lower()}.", track_id=track.id if track else None)

        if status.state == "COMPLETED" and download.completed_at is None:
            download.completed_at = dt.datetime.utcnow()
            db.commit()
            _finalize_download(db, download, candidate, track, settings)
