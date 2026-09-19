from app.parsing.normalizer import normalize_track


def test_basic_normalization():
    n = normalize_track("Vitalic", "Poison Lips")
    assert n.artist == "vitalic"
    assert n.title == "poison lips"
    assert n.version is None


def test_radio_edit_kept_as_version():
    n = normalize_track("Vitalic", "Poison Lips (Radio Edit)")
    assert n.title == "poison lips"
    assert n.version == "radio edit"


def test_extended_mix_kept():
    n = normalize_track("Artist", "Track [Extended Mix]")
    assert n.version == "extended mix"
    assert n.title == "track"


def test_flac_and_lossless_stripped_not_treated_as_version():
    n = normalize_track("Artist", "Track [FLAC] (Lossless)")
    assert n.version is None
    assert "flac" not in n.title
    assert "lossless" not in n.title


def test_bitrate_and_cd_markers_stripped():
    n = normalize_track("Artist", "Track (320kbps) (CD1)")
    assert n.version is None
    assert "320" not in n.title
    assert "cd1" not in n.title.replace(" ", "")


def test_double_spaces_and_punctuation_collapsed():
    n = normalize_track("Vitalic!!", "  Poison   Lips...")
    assert n.artist == "vitalic"
    assert n.title == "poison lips"


def test_unknown_bracket_content_preserved():
    n = normalize_track("Artist", "Track (feat. Someone)")
    assert "feat" in n.title
    assert "someone" in n.title
