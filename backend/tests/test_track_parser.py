from app.parsing.track_parser import parse_line, parse_text


def test_basic_hyphen():
    r = parse_line("Vitalic - Poison Lips")
    assert r.artist == "Vitalic"
    assert r.title == "Poison Lips"


def test_em_dash():
    r = parse_line("Vitalic — Poison Lips (Radio Edit)")
    assert r.artist == "Vitalic"
    assert r.title == "Poison Lips (Radio Edit)"


def test_en_dash():
    r = parse_line("Vitalic – Poison Lips")
    assert r.artist == "Vitalic"
    assert r.title == "Poison Lips"


def test_pipe():
    r = parse_line("Acid Arab | Gul l'Abi")
    assert r.artist == "Acid Arab"
    assert r.title == "Gul l'Abi"


def test_slash():
    r = parse_line("The Chemical Brothers / Star Guitar")
    assert r.artist == "The Chemical Brothers"
    assert r.title == "Star Guitar"


def test_leading_track_number():
    r = parse_line("01. Vitalic - Poison Lips (Extended Mix)")
    assert r.artist == "Vitalic"
    assert r.title == "Poison Lips (Extended Mix)"


def test_unparseable_line_kept_without_artist():
    r = parse_line("Some Weird Line With No Separator")
    assert r.artist is None
    assert r.title == "Some Weird Line With No Separator"


def test_parse_text_skips_blank_lines():
    lines = parse_text("Vitalic - Poison Lips\n\nAcid Arab - Gul l'Abi\n")
    assert len(lines) == 2


def test_dof_example_set():
    text = (
        "Vitalic - Poison Lips\n"
        "Acid Arab - Gul l'Abi\n"
        "The Chemical Brothers - Star Guitar\n"
    )
    lines = parse_text(text)
    assert len(lines) == 3
    assert [l.artist for l in lines] == ["Vitalic", "Acid Arab", "The Chemical Brothers"]
