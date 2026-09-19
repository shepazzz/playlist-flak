import pytest

from app.spotify.client import SpotifyError, extract_playlist_id


def test_extract_from_open_spotify_url():
    url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc123"
    assert extract_playlist_id(url) == "37i9dQZF1DXcBWIGoYBM5M"


def test_extract_from_uri():
    assert extract_playlist_id("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M") == "37i9dQZF1DXcBWIGoYBM5M"


def test_invalid_url_raises():
    with pytest.raises(SpotifyError):
        extract_playlist_id("https://example.com/not-spotify")
