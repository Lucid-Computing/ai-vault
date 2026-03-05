"""AES-256-GCM encryption for vault resource values.

Adapted from lucid-verifier's encryption module. Provides authenticated
encryption with associated data (AEAD) for secret values stored in the vault.

Wire format::

    base64( b"aesgcm1:" | nonce[12 bytes] | ciphertext + auth_tag[16 bytes] )

Key derivation uses HKDF-SHA256 with context info ``b"ai-vault-resource"``.
The encryption key is read from the ``AI_VAULT_ENCRYPTION_KEY`` env var.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_AES_GCM_NONCE_SIZE = 12  # 96-bit nonce (NIST recommended)
_AES_GCM_TAG = b"aesgcm1:"  # Prefix to identify AES-GCM encrypted data
_HKDF_INFO = b"ai-vault-resource"


class EncryptionError(Exception):
    """Base encryption error."""


class EncryptionNotConfiguredError(EncryptionError):
    """Raised when encryption key is not set."""


class DecryptionError(EncryptionError):
    """Raised when decryption fails (wrong key, tampered data, etc.)."""


def _get_encryption_key() -> str:
    """Read the encryption key from environment."""
    key = os.environ.get("AI_VAULT_ENCRYPTION_KEY")
    if not key:
        raise EncryptionNotConfiguredError(
            "AI_VAULT_ENCRYPTION_KEY environment variable is not set. "
            "Run 'ai-vault init' to generate one."
        )
    return key


def derive_key(
    secret: str,
    *,
    info: bytes = _HKDF_INFO,
    salt: Optional[bytes] = None,
) -> bytes:
    """Derive a 256-bit key from a secret string using HKDF-SHA256.

    Args:
        secret: Raw secret string to derive key from.
        info: Context info binding the derived key to a specific usage.
        salt: Optional salt for key derivation.

    Returns:
        32-byte derived key.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    )
    return hkdf.derive(secret.encode())


def encrypt(plaintext: str, key: Optional[str] = None) -> str:
    """Encrypt a plaintext string using AES-256-GCM.

    Args:
        plaintext: UTF-8 string to encrypt.
        key: Encryption key. If None, reads from environment.

    Returns:
        URL-safe base64-encoded encrypted payload.
    """
    key_secret = key or _get_encryption_key()
    derived = derive_key(key_secret)
    aesgcm = AESGCM(derived)
    nonce = os.urandom(_AES_GCM_NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    payload = _AES_GCM_TAG + nonce + ciphertext
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def decrypt(encrypted: str, key: Optional[str] = None) -> str:
    """Decrypt an AES-256-GCM encrypted payload.

    Args:
        encrypted: Base64-encoded encrypted payload.
        key: Encryption key. If None, reads from environment.

    Returns:
        Decrypted UTF-8 plaintext.

    Raises:
        DecryptionError: If decryption fails.
    """
    key_secret = key or _get_encryption_key()
    try:
        raw = base64.urlsafe_b64decode(encrypted.encode("utf-8"))
    except Exception as e:
        raise DecryptionError(f"Invalid base64 data: {e}") from e

    if not raw.startswith(_AES_GCM_TAG):
        raise DecryptionError("Not AES-256-GCM encrypted data (missing tag)")

    raw = raw[len(_AES_GCM_TAG):]
    if len(raw) < _AES_GCM_NONCE_SIZE + 16:  # nonce + minimum auth tag
        raise DecryptionError("Encrypted data too short (truncated)")

    nonce = raw[:_AES_GCM_NONCE_SIZE]
    ciphertext = raw[_AES_GCM_NONCE_SIZE:]

    derived = derive_key(key_secret)
    aesgcm = AESGCM(derived)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as e:
        raise DecryptionError(f"Decryption failed: {e}") from e

    return plaintext.decode("utf-8")


def encrypt_value(data: dict[str, Any], key: Optional[str] = None) -> str:
    """Encrypt a dict value (JSON-serialized) for storage.

    Args:
        data: Dictionary to encrypt.
        key: Encryption key. If None, reads from environment.

    Returns:
        Encrypted string suitable for database storage.
    """
    plaintext = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return encrypt(plaintext, key=key)


def decrypt_value(encrypted: str, key: Optional[str] = None) -> dict[str, Any]:
    """Decrypt a stored value back to a dict.

    Args:
        encrypted: Encrypted string from database.
        key: Encryption key. If None, reads from environment.

    Returns:
        Decrypted dictionary.

    Raises:
        DecryptionError: If decryption or JSON parsing fails.
    """
    plaintext = decrypt(encrypted, key=key)
    try:
        return json.loads(plaintext)
    except json.JSONDecodeError as e:
        raise DecryptionError(f"Decrypted data is not valid JSON: {e}") from e


def generate_encryption_key() -> str:
    """Generate a new random encryption key (base64-encoded 32 bytes)."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")
