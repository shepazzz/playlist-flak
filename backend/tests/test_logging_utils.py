from app.logging_utils import _redact


def test_plain_error_mentioning_password_setting_is_not_redacted():
    msg = "Search failed: no username/password configured; set SLSKD_API_KEY in .env"
    assert _redact(msg) == msg


def test_actual_key_value_pair_is_redacted():
    msg = "using api_key: sk-abcdef1234567890"
    assert _redact(msg) != msg
    assert "withheld" in _redact(msg)


def test_authorization_header_value_is_redacted():
    msg = "sent Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    assert "withheld" in _redact(msg)
