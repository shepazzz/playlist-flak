"""File Validator (spec §9) + suspicious-transcode heuristics (spec §10).

Never claims a .flac extension alone means the file is genuinely lossless.
Uses `ffprobe` when available (more reliable stream inspection), falling
back to `mutagen` if ffprobe isn't on PATH. Classifies as one of:
`likely_ok`, `suspicious`, `invalid` — never a stronger claim than that,
since definitively proving a lossy->FLAC transcode is out of scope
(spec §10 explicitly disclaims this).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_COMMON_SAMPLE_RATES = {44100, 48000, 88200, 96000, 176400, 192000}
_COMMON_BIT_DEPTHS = {16, 24, 32}
_MIN_PLAUSIBLE_BYTES_PER_SEC = 40_000  # ~320kbps equivalent; genuine 16/44.1 FLAC is usually 80-150 KB/s


@dataclass
class VerificationResult:
    codec: str | None = None
    sample_rate_hz: int | None = None
    bit_depth: int | None = None
    channels: int | None = None
    duration_sec: float | None = None
    size_bytes: int | None = None
    state: str = "invalid"  # likely_ok | suspicious | invalid
    notes: list[str] = field(default_factory=list)


def _probe_with_ffprobe(path: Path) -> dict | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _from_ffprobe(data: dict, path: Path) -> VerificationResult:
    streams = data.get("streams") or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format") or {}

    if not audio:
        return VerificationResult(state="invalid", notes=["ffprobe found no audio stream"])

    codec = audio.get("codec_name")
    sample_rate = int(audio["sample_rate"]) if audio.get("sample_rate") else None
    bit_depth = audio.get("bits_per_raw_sample") or audio.get("bits_per_sample")
    bit_depth = int(bit_depth) if bit_depth else None
    channels = audio.get("channels")
    duration = float(fmt.get("duration")) if fmt.get("duration") else None
    size = int(fmt.get("size")) if fmt.get("size") else path.stat().st_size if path.exists() else None

    return VerificationResult(
        codec=codec,
        sample_rate_hz=sample_rate,
        bit_depth=bit_depth,
        channels=channels,
        duration_sec=duration,
        size_bytes=size,
    )


def _from_mutagen(path: Path) -> VerificationResult:
    try:
        from mutagen.flac import FLAC, FLACNoHeaderError
    except ImportError as e:  # pragma: no cover - mutagen is a hard dependency
        return VerificationResult(state="invalid", notes=[f"mutagen unavailable: {e}"])

    try:
        audio = FLAC(str(path))
    except FLACNoHeaderError:
        return VerificationResult(state="invalid", notes=["File has no valid FLAC header (not FLAC, or corrupted)."])
    except Exception as e:  # noqa: BLE001 - any decode/parsing failure means invalid
        return VerificationResult(state="invalid", notes=[f"Failed to parse as FLAC: {e}"])

    info = audio.info
    size = path.stat().st_size if path.exists() else None

    return VerificationResult(
        codec="flac",
        sample_rate_hz=getattr(info, "sample_rate", None),
        bit_depth=getattr(info, "bits_per_sample", None),
        channels=getattr(info, "channels", None),
        duration_sec=getattr(info, "length", None),
        size_bytes=size,
    )


def _apply_heuristics(result: VerificationResult, expected_duration_ms: int | None) -> None:
    if result.state == "invalid" and result.notes:
        # Already flagged as a hard failure upstream (e.g. no audio stream).
        return

    suspicious_notes: list[str] = []

    if result.codec and result.codec.lower() != "flac":
        result.state = "invalid"
        result.notes.append(f"Codec is '{result.codec}', not FLAC.")
        return

    if result.duration_sec and result.size_bytes:
        bytes_per_sec = result.size_bytes / result.duration_sec
        if bytes_per_sec < _MIN_PLAUSIBLE_BYTES_PER_SEC:
            suspicious_notes.append(
                f"Unusually small for FLAC (~{bytes_per_sec / 1000:.0f} KB/s) - "
                "possible transcode from a lossy source."
            )

    if result.sample_rate_hz and result.sample_rate_hz not in _COMMON_SAMPLE_RATES:
        suspicious_notes.append(f"Unusual sample rate: {result.sample_rate_hz} Hz.")

    if result.bit_depth and result.bit_depth not in _COMMON_BIT_DEPTHS:
        suspicious_notes.append(f"Unusual bit depth: {result.bit_depth}-bit.")

    if result.channels and result.channels not in (1, 2):
        suspicious_notes.append(f"Unusual channel count: {result.channels}.")

    if expected_duration_ms and result.duration_sec:
        delta = abs(expected_duration_ms / 1000.0 - result.duration_sec)
        if delta > 5:
            suspicious_notes.append(
                f"Duration differs from source metadata by {delta:.0f}s - "
                "file may not match the expected track."
            )

    if not result.duration_sec or result.duration_sec <= 0:
        result.state = "invalid"
        result.notes.append("Could not determine a valid duration for this file.")
        return

    if suspicious_notes:
        result.state = "suspicious"
        result.notes.extend(suspicious_notes)
    else:
        result.state = "likely_ok"


def verify_file(path: Path, expected_duration_ms: int | None = None) -> VerificationResult:
    path = Path(path)
    if not path.exists():
        return VerificationResult(state="invalid", notes=[f"File not found: {path}"])

    if path.suffix.lower() != ".flac":
        return VerificationResult(state="invalid", notes=[f"Expected a .flac file, got '{path.suffix}'."])

    ffprobe_data = _probe_with_ffprobe(path)
    result = _from_ffprobe(ffprobe_data, path) if ffprobe_data else _from_mutagen(path)

    if result.state == "invalid" and result.notes:
        return result

    _apply_heuristics(result, expected_duration_ms)
    return result
