from pathlib import Path

from app.library.organizer import TrackForLibrary, build_library_path, place_file, sanitize_component


def _track(**kwargs) -> TrackForLibrary:
    defaults = dict(artist="Vitalic", title="Poison Lips", album="Flashmob", album_artist="Vitalic", release_year=2005, track_number=3)
    defaults.update(kwargs)
    return TrackForLibrary(**defaults)


def test_sanitize_strips_illegal_windows_chars():
    assert sanitize_component('Artist: "Bad" / Name?') == "Artist_ _Bad_ _ Name_"


def test_build_path_regular_artist(tmp_path):
    p = build_library_path(tmp_path, _track())
    assert p == tmp_path / "Vitalic" / "2005 - Flashmob" / "03 - Poison Lips.flac"


def test_build_path_compilation(tmp_path):
    p = build_library_path(tmp_path, _track(album_artist="Various Artists"))
    assert p == tmp_path / "Various Artists" / "2005 - Flashmob" / "03 - Vitalic - Poison Lips.flac"


def test_place_file_moves_when_no_conflict(tmp_path):
    src = tmp_path / "incoming.flac"
    src.write_bytes(b"AAAA")
    result = place_file(src, tmp_path / "Music", _track(), duplicate_policy="SKIP")
    assert result.action == "MOVED"
    assert result.library_path.exists()
    assert not src.exists()


def test_place_file_skip_does_not_overwrite(tmp_path):
    library_root = tmp_path / "Music"
    existing = build_library_path(library_root, _track())
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"ORIGINAL")

    src = tmp_path / "incoming.flac"
    src.write_bytes(b"NEW DATA")

    result = place_file(src, library_root, _track(), duplicate_policy="SKIP")
    assert result.action == "SKIP"
    assert existing.read_bytes() == b"ORIGINAL"
    assert src.exists()  # never deleted the incoming file either


def test_place_file_keep_both(tmp_path):
    library_root = tmp_path / "Music"
    existing = build_library_path(library_root, _track())
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"ORIGINAL")

    src = tmp_path / "incoming.flac"
    src.write_bytes(b"NEW DATA")

    result = place_file(src, library_root, _track(), duplicate_policy="KEEP_BOTH")
    assert result.action == "KEEP_BOTH"
    assert existing.read_bytes() == b"ORIGINAL"
    assert result.library_path.read_bytes() == b"NEW DATA"
    assert result.library_path != existing


def test_place_file_compare_identical(tmp_path):
    library_root = tmp_path / "Music"
    existing = build_library_path(library_root, _track())
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"SAME")

    src = tmp_path / "incoming.flac"
    src.write_bytes(b"SAME")

    result = place_file(src, library_root, _track(), duplicate_policy="COMPARE")
    assert result.action == "COMPARE_IDENTICAL"


def test_place_file_compare_different_keeps_both(tmp_path):
    library_root = tmp_path / "Music"
    existing = build_library_path(library_root, _track())
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"ORIGINAL")

    src = tmp_path / "incoming.flac"
    src.write_bytes(b"DIFFERENT")

    result = place_file(src, library_root, _track(), duplicate_policy="COMPARE")
    assert result.action == "COMPARE_DIFFERENT"
    assert existing.read_bytes() == b"ORIGINAL"
