"""Fernet-based encryption utilities for connector credentials."""

from cryptography.fernet import Fernet, InvalidToken

from app.settings import settings


_KEY_HELP = (
    "CONNECTOR_ENCRYPTION_KEY is not set or invalid. "
    "Generate one with: python -c \"from cryptography.fernet import Fernet; "
    "print(Fernet.generate_key().decode())\""
)


def _get_fernet() -> Fernet:
    key = settings.CONNECTOR_ENCRYPTION_KEY
    if not key:
        raise RuntimeError(_KEY_HELP)
    try:
        return Fernet(key.encode())
    except Exception as exc:  # pragma: no cover - depends on cryptography internals
        raise RuntimeError(_KEY_HELP) from exc


def encrypt(value: str) -> str:
    if value is None:
        raise ValueError("encrypt() requires a non-null string")
    fernet = _get_fernet()
    return fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if value is None:
        raise ValueError("decrypt() requires a non-null string")
    fernet = _get_fernet()
    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Invalid encryption token") from exc
