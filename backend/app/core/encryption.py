
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


fernet = Fernet(
    settings.FIELD_ENCRYPTION_KEY.encode()
)


def encrypt_value(value: str) -> str:
    """Encrypt a sensitive field before database storage."""

    if not value:
        raise ValueError("Cannot encrypt an empty value")

    return fernet.encrypt(
        value.encode("utf-8")
    ).decode("utf-8")


def decrypt_value(encrypted_value: str) -> str:
    """Decrypt a previously encrypted field."""

    try:
        return fernet.decrypt(
            encrypted_value.encode("utf-8")
        ).decode("utf-8")

    except InvalidToken as exc:
        raise ValueError(
            "Could not decrypt stored field"
        ) from exc
