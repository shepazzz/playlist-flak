from pathlib import Path

from app.verification.flac_verifier import VerificationResult, _apply_heuristics, verify_file


def test_missing_file_is_invalid(tmp_path):
    result = verify_file(tmp_path / "does_not_exist.flac")
    assert result.state == "invalid"


def test_wrong_extension_is_invalid(tmp_path):
    p = tmp_path / "song.mp3"
    p.write_bytes(b"not real audio")
    result = verify_file(p)
    assert result.state == "invalid"


def test_heuristics_flag_tiny_bitrate_as_suspicious():
    result = VerificationResult(
        codec="flac", sample_rate_hz=44100, bit_depth=16, channels=2,
        duration_sec=200.0, size_bytes=200 * 20_000,  # ~20KB/s, way below plausible FLAC
    )
    _apply_heuristics(result, expected_duration_ms=None)
    assert result.state == "suspicious"


def test_heuristics_pass_plausible_flac():
    result = VerificationResult(
        codec="flac", sample_rate_hz=44100, bit_depth=16, channels=2,
        duration_sec=200.0, size_bytes=200 * 100_000,
    )
    _apply_heuristics(result, expected_duration_ms=200_000)
    assert result.state == "likely_ok"


def test_heuristics_flag_duration_mismatch():
    result = VerificationResult(
        codec="flac", sample_rate_hz=44100, bit_depth=16, channels=2,
        duration_sec=200.0, size_bytes=200 * 100_000,
    )
    _apply_heuristics(result, expected_duration_ms=260_000)
    assert result.state == "suspicious"


def test_non_flac_codec_is_invalid():
    result = VerificationResult(codec="mp3", duration_sec=200.0, size_bytes=5_000_000)
    _apply_heuristics(result, expected_duration_ms=None)
    assert result.state == "invalid"
