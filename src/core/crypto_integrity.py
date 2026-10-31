"""Cryptographic and data integrity controls for edge payloads and file streams."""

import hashlib
import hmac
import os
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.core.exceptions import IntegrityError


class CryptoIntegrityManager:
    """Manages SHA-256 checksum calculation, verification, and AES-256-GCM authenticated encryption."""

    def __init__(self, secret_key: bytes | None = None) -> None:
        """Initializes the manager with a 256-bit symmetric key.

        Args:
            secret_key: Optional 32-byte key. If omitted, generates a cryptographically secure random key.
        """
        if secret_key is None:
            self._key = AESGCM.generate_key(bit_length=256)
        else:
            if len(secret_key) != 32:
                raise ValueError("AES-256 key must be exactly 32 bytes (256 bits).")
            self._key = secret_key
        self._aesgcm = AESGCM(self._key)

    @property
    def key(self) -> bytes:
        """Returns the symmetric key bytes."""
        return self._key

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Computes the hex-encoded SHA-256 checksum of the provided raw bytes.

        Args:
            data: Binary payload to hash.

        Returns:
            Hexadecimal SHA-256 digest string.
        """
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def compute_stream_sha256(stream: BinaryIO, chunk_size: int = 65536) -> str:
        """Computes SHA-256 checksum for a file or binary stream in chunks.

        Args:
            stream: Readable binary IO stream.
            chunk_size: Byte buffer size for reading chunks.

        Returns:
            Hexadecimal SHA-256 digest string.
        """
        hasher = hashlib.sha256()
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def verify_sha256(data: bytes, expected_checksum: str) -> bool:
        """Verifies payload checksum against expected value using constant-time comparison.

        Args:
            data: Raw payload bytes to verify.
            expected_checksum: Hexadecimal SHA-256 string to compare against.

        Returns:
            True if matching, raises IntegrityError otherwise.

        Raises:
            IntegrityError: If checksums do not match.
        """
        actual_checksum = hashlib.sha256(data).hexdigest()
        if not hmac.compare_digest(actual_checksum.lower(), expected_checksum.lower()):
            raise IntegrityError(
                f"Checksum mismatch! Expected: {expected_checksum}, Actual: {actual_checksum}"
            )
        return True

    def encrypt_payload(self, plaintext: bytes, associated_data: bytes | None = None) -> bytes:
        """Encrypts data using AES-256-GCM.

        Output format: 12-byte Nonce + Ciphertext with appended 16-byte GCM authentication tag.

        Args:
            plaintext: Plain payload bytes.
            associated_data: Optional authenticated associated data (AAD).

        Returns:
            Combined binary blob (nonce + ciphertext + tag).
        """
        nonce = os.urandom(12)  # Standard 96-bit nonce for AES-GCM
        ciphertext_and_tag = self._aesgcm.encrypt(nonce, plaintext, associated_data)
        return nonce + ciphertext_and_tag

    def decrypt_payload(self, encrypted_data: bytes, associated_data: bytes | None = None) -> bytes:
        """Decrypts AES-256-GCM encrypted payload and verifies cryptographic authenticity.

        Args:
            encrypted_data: Combined binary blob (12-byte nonce + ciphertext + tag).
            associated_data: Optional authenticated associated data matching encryption.

        Returns:
            Decrypted plaintext bytes.

        Raises:
            IntegrityError: If ciphertext or associated data has been tampered with or corrupted.
        """
        if len(encrypted_data) < 28:  # 12-byte nonce + 16-byte minimum tag
            raise IntegrityError("Corrupted ciphertext: payload size is smaller than nonce + tag.")

        nonce = encrypted_data[:12]
        ciphertext_and_tag = encrypted_data[12:]

        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data)
            return plaintext
        except InvalidTag as exc:
            raise IntegrityError(
                "Payload integrity validation failed! Ciphertext or tag has been tampered with."
            ) from exc
