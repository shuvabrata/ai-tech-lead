import pytest
from cryptography.fernet import Fernet

from app.common import encryption
from app.settings import settings


def test_encrypt_decrypt_roundtrip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "CONNECTOR_ENCRYPTION_KEY", key)

    plaintext = "super-secret"
    token = encryption.encrypt(plaintext)

    assert token != plaintext
    assert encryption.decrypt(token) == plaintext


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "CONNECTOR_ENCRYPTION_KEY", "")

    with pytest.raises(RuntimeError, match="CONNECTOR_ENCRYPTION_KEY"):
        encryption.encrypt("value")


def test_invalid_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "CONNECTOR_ENCRYPTION_KEY", "not-a-valid-key")

    with pytest.raises(RuntimeError, match="CONNECTOR_ENCRYPTION_KEY"):
        encryption.encrypt("value")


def test_invalid_token_raises(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "CONNECTOR_ENCRYPTION_KEY", key)

    with pytest.raises(ValueError, match="Invalid encryption token"):
        encryption.decrypt("not-a-token")
