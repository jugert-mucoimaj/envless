"""Encryption for stored values, and hashing for issued access tokens.

Values are encrypted at rest with a single Fernet key so that a dump of the
`variables` table is useless on its own. Access tokens are shown once at
creation and then only kept as a SHA-256 hash, the same way an SSH key or an
API key is handled.
"""

import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

TOKEN_PREFIX = "envless_"


def _fernet() -> Fernet:
    key = get_settings().envless_master_key
    if not key:
        raise RuntimeError(
            "ENVLESS_MASTER_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # A value written under a different master key can no longer be read.
        return ""


def mask(value: str) -> str:
    """A stand-in shown in lists so secrets are not sprayed across the screen."""
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:3]}{'•' * 8}{value[-2:]}"


def new_access_token() -> tuple[str, str, str]:
    """Return (plaintext, prefix, hash) for a freshly minted access token."""
    body = secrets.token_urlsafe(32)
    plaintext = f"{TOKEN_PREFIX}{body}"
    return plaintext, plaintext[: len(TOKEN_PREFIX) + 6], hash_token(plaintext)


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()
