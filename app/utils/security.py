import hmac
import hashlib
from typing import Optional
from cryptography.fernet import Fernet
from app.config import settings


def get_cipher() -> Fernet:
    """Returns a Fernet cipher instance using the derived encryption key."""
    return Fernet(settings.fernet_key)


def encrypt_token(plain_token: str) -> str:
    """
    Encrypts a sensitive token (such as a Google OAuth refresh token) for durable storage.
    """
    if not plain_token:
        return ""
    cipher = get_cipher()
    encrypted_bytes = cipher.encrypt(plain_token.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypts a previously encrypted token.
    """
    if not encrypted_token:
        return ""
    cipher = get_cipher()
    decrypted_bytes = cipher.decrypt(encrypted_token.encode("utf-8"))
    return decrypted_bytes.decode("utf-8")


def verify_whatsapp_signature(payload_bytes: bytes, signature_header: Optional[str], app_secret: str) -> bool:
    """
    Validates Meta WhatsApp webhook sha256 signature if app_secret is configured.
    Format: sha256=<hex_digest>
    """
    if not app_secret or not signature_header:
        # If no secret configured, signature check is optional
        return True
    
    parts = signature_header.split("=")
    if len(parts) != 2 or parts[0] != "sha256":
        return False
    
    expected = hmac.new(app_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(parts[1], expected)


def verify_pubsub_token(token: Optional[str]) -> bool:
    """
    Validates Pub/Sub verification query or header token if configured in settings.
    """
    if not settings.PUBSUB_VERIFICATION_TOKEN:
        return True
    if not token:
        return False
    return hmac.compare_digest(token, settings.PUBSUB_VERIFICATION_TOKEN)
