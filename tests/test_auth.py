from unittest.mock import patch
from app.utils.security import encrypt_token, decrypt_token
from app.utils.logging import SensitiveDataFilter


def test_token_encryption_roundtrip():
    secret_token = "1//04_abcdef1234567890_refresh_token_very_secret"
    encrypted = encrypt_token(secret_token)
    assert encrypted != secret_token
    assert len(encrypted) > len(secret_token)

    decrypted = decrypt_token(encrypted)
    assert decrypted == secret_token


def test_log_sanitizer():
    raw_log = "Error sending message with access_token=EAABwz123456789 and Bearer ya29.a0ARrdaM123456789"
    sanitized = SensitiveDataFilter.sanitize(raw_log)
    assert "EAABwz123456789" not in sanitized
    assert "ya29.a0ARrdaM123456789" not in sanitized
    assert "[REDACTED_TOKEN]" in sanitized


@patch("app.routes.auth.GmailService.get_authorization_url")
def test_google_login_endpoint(mock_get_url, client):
    mock_get_url.return_value = ("https://accounts.google.com/o/oauth2/auth?client_id=test", "state_123")
    response = client.get("/auth/google/login")
    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert "accounts.google.com" in data["authorization_url"]
