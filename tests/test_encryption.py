"""Tests for AES-256-GCM encryption module."""

from __future__ import annotations

import os

import pytest

from ai_vault.encryption import (
    DecryptionError,
    EncryptionNotConfiguredError,
    decrypt,
    decrypt_value,
    derive_key,
    encrypt,
    encrypt_value,
    generate_encryption_key,
)

TEST_KEY = "test-key-do-not-use-in-production-1234567890"


class TestEncryptDecrypt:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "hello world, this is a secret!"
        encrypted = encrypt(plaintext, key=TEST_KEY)
        decrypted = decrypt(encrypted, key=TEST_KEY)
        assert decrypted == plaintext

    def test_encrypt_produces_different_ciphertext(self):
        """Same plaintext encrypted twice should produce different nonces/ciphertext."""
        plaintext = "same input"
        enc1 = encrypt(plaintext, key=TEST_KEY)
        enc2 = encrypt(plaintext, key=TEST_KEY)
        assert enc1 != enc2
        # But both decrypt to the same value
        assert decrypt(enc1, key=TEST_KEY) == plaintext
        assert decrypt(enc2, key=TEST_KEY) == plaintext

    def test_decrypt_wrong_key_fails(self):
        encrypted = encrypt("secret", key=TEST_KEY)
        with pytest.raises(DecryptionError):
            decrypt(encrypted, key="wrong-key-completely-different")

    def test_decrypt_corrupted_data_fails(self):
        encrypted = encrypt("secret", key=TEST_KEY)
        # Flip a character in the middle
        chars = list(encrypted)
        mid = len(chars) // 2
        chars[mid] = "A" if chars[mid] != "A" else "B"
        corrupted = "".join(chars)
        with pytest.raises(DecryptionError):
            decrypt(corrupted, key=TEST_KEY)

    def test_decrypt_truncated_data_fails(self):
        encrypted = encrypt("secret", key=TEST_KEY)
        # Truncate to just a few chars (valid base64 but too short)
        truncated = encrypted[:20]
        with pytest.raises(DecryptionError):
            decrypt(truncated, key=TEST_KEY)

    def test_empty_string_roundtrip(self):
        encrypted = encrypt("", key=TEST_KEY)
        assert decrypt(encrypted, key=TEST_KEY) == ""

    def test_unicode_roundtrip(self):
        plaintext = "こんにちは世界 🔐🗝️ émojis and ünïcödé"
        encrypted = encrypt(plaintext, key=TEST_KEY)
        assert decrypt(encrypted, key=TEST_KEY) == plaintext

    def test_large_value_roundtrip(self):
        """64KB payload round-trips correctly."""
        plaintext = "x" * 65536
        encrypted = encrypt(plaintext, key=TEST_KEY)
        assert decrypt(encrypted, key=TEST_KEY) == plaintext


class TestEncryptDecryptValue:
    def test_dict_roundtrip(self):
        data = {"api_key": "sk-1234", "endpoint": "https://api.example.com"}
        encrypted = encrypt_value(data, key=TEST_KEY)
        decrypted = decrypt_value(encrypted, key=TEST_KEY)
        assert decrypted == data

    def test_empty_dict_roundtrip(self):
        data = {}
        encrypted = encrypt_value(data, key=TEST_KEY)
        assert decrypt_value(encrypted, key=TEST_KEY) == data

    def test_nested_dict_roundtrip(self):
        data = {"outer": {"inner": [1, 2, 3], "flag": True, "value": None}}
        encrypted = encrypt_value(data, key=TEST_KEY)
        assert decrypt_value(encrypted, key=TEST_KEY) == data


class TestKeyDerivation:
    def test_deterministic(self):
        """Same input always produces same derived key."""
        k1 = derive_key("my-secret", salt=b"test-salt")
        k2 = derive_key("my-secret", salt=b"test-salt")
        assert k1 == k2

    def test_different_salts_produce_different_keys(self):
        k1 = derive_key("my-secret", salt=b"salt-a")
        k2 = derive_key("my-secret", salt=b"salt-b")
        assert k1 != k2

    def test_different_info_produce_different_keys(self):
        k1 = derive_key("my-secret", info=b"context-a")
        k2 = derive_key("my-secret", info=b"context-b")
        assert k1 != k2

    def test_key_length(self):
        k = derive_key("test")
        assert len(k) == 32  # 256 bits


class TestEncryptionNotConfigured:
    def test_encrypt_without_key_raises(self, monkeypatch):
        monkeypatch.delenv("AI_VAULT_ENCRYPTION_KEY", raising=False)
        with pytest.raises(EncryptionNotConfiguredError):
            encrypt("test")

    def test_decrypt_without_key_raises(self, monkeypatch):
        monkeypatch.delenv("AI_VAULT_ENCRYPTION_KEY", raising=False)
        with pytest.raises(EncryptionNotConfiguredError):
            decrypt("some-data")


class TestGenerateKey:
    def test_generates_valid_key(self):
        key = generate_encryption_key()
        assert len(key) > 0
        # Should be usable for encryption
        encrypted = encrypt("test", key=key)
        assert decrypt(encrypted, key=key) == "test"

    def test_generates_unique_keys(self):
        k1 = generate_encryption_key()
        k2 = generate_encryption_key()
        assert k1 != k2
