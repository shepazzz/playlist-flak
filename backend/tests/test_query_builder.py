from app.parsing.normalizer import NormalizedTrack
from app.search.query_builder import build_queries


def test_basic_queries():
    t = NormalizedTrack(artist="vitalic", title="poison lips", version=None)
    qs = build_queries(t)
    assert "vitalic poison lips" in qs
    assert "vitalic - poison lips" in qs
    assert "vitalic poison lips FLAC" in qs


def test_album_and_version_variants_added():
    t = NormalizedTrack(artist="vitalic", title="poison lips", version="radio edit", album="flashmob")
    qs = build_queries(t)
    assert any("flashmob" in q for q in qs)
    assert any("radio edit" in q for q in qs)


def test_no_duplicates():
    t = NormalizedTrack(artist="a", title="b", version=None)
    qs = build_queries(t, strict_flac_only=False)
    assert len(qs) == len(set(q.lower() for q in qs))


def test_missing_artist_or_title_returns_empty():
    t = NormalizedTrack(artist="", title="", version=None)
    assert build_queries(t) == []
