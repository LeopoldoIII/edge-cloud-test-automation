"""Unit tests for cryptographic integrity and AES-256-GCM authenticated encryption."""

import io
import pytest

from src.core.crypto_integrity import CryptoIntegrityManager
from src.core.exceptions import IntegrityError


@pytest.mark.unit
class TestCryptoIntegrity:
    """Test suite for cryptographic hashing, authenticated encryption, and tampering detection."""

    def test_sha256_computation(self, crypto_manager: CryptoIntegrityManager) -> None:
        """Verifies deterministic SHA-256 computation."""
        sample_data = b"Edge-to-Cloud Telemetry Payload 12345"
        expected_hash = "9889ac6e87fe35111ef607f3b28a6fd67ab7bcd7c5854192412728a951535b7a"
        computed_hash = crypto_manager.compute_sha256(sample_data)
        assert computed_hash == expected_hash

    def test_stream_sha256_computation(self, crypto_manager: CryptoIntegrityManager) -> None:
        """Verifies chunked stream SHA-256 hashing matches in-memory hash."""
        data = b"Large streamed chunk buffer" * 1000
        stream = io.BytesIO(data)
        stream_hash = crypto_manager.compute_stream_sha256(stream, chunk_size=256)
        direct_hash = crypto_manager.compute_sha256(data)
        assert stream_hash == direct_hash

    def test_verify_sha256_success(self, crypto_manager: CryptoIntegrityManager) -> None:
        """Verifies constant-time comparison succeeds for matching hashes."""
        payload = b"Valid Medical Sensor Record"
        valid_hash = crypto_manager.compute_sha256(payload)
        assert crypto_manager.verify_sha256(payload, valid_hash) is True

    def test_verify_sha256_mismatch_raises_integrity_error(
        self, crypto_manager: CryptoIntegrityManager
    ) -> None:
        """Verifies that modified payload raises IntegrityError."""
        original = b"Original Sensor Payload"
        tampered = b"Tampered Sensor Payload"
        original_hash = crypto_manager.compute_sha256(original)

        with pytest.raises(IntegrityError, match="Checksum mismatch"):
            crypto_manager.verify_sha256(tampered, original_hash)

    def test_aes_gcm_encrypt_decrypt_roundtrip(
        self, crypto_manager: CryptoIntegrityManager
    ) -> None:
        """Verifies encryption and authenticated decryption preserves payload content."""
        plaintext = b"Sensitive Edge Clinical Metrics: HeartRate=72, SpO2=98"
        aad = b"DeviceID=edge-station-99;Firmware=2.4.1"

        ciphertext = crypto_manager.encrypt_payload(plaintext, associated_data=aad)
        assert ciphertext != plaintext
        assert len(ciphertext) == len(plaintext) + 12 + 16  # Nonce (12) + tag (16) overhead

        decrypted = crypto_manager.decrypt_payload(ciphertext, associated_data=aad)
        assert decrypted == plaintext

    def test_aes_gcm_tampered_ciphertext_fails(
        self, crypto_manager: CryptoIntegrityManager
    ) -> None:
        """Verifies that bit-flipping ciphertext causes decryption failure with IntegrityError."""
        plaintext = b"Payload to be tampered"
        ciphertext = crypto_manager.encrypt_payload(plaintext)

        # Mutate byte in the ciphertext body
        mutated = bytearray(ciphertext)
        mutated[15] = mutated[15] ^ 0xFF

        with pytest.raises(IntegrityError, match="Payload integrity validation failed"):
            crypto_manager.decrypt_payload(bytes(mutated))

    def test_aes_gcm_tampered_associated_data_fails(
        self, crypto_manager: CryptoIntegrityManager
    ) -> None:
        """Verifies that altering AAD causes authentication tag verification failure."""
        plaintext = b"Payload with AAD"
        valid_aad = b"Station-01"
        tampered_aad = b"Station-02"

        ciphertext = crypto_manager.encrypt_payload(plaintext, associated_data=valid_aad)

        with pytest.raises(IntegrityError, match="Payload integrity validation failed"):
            crypto_manager.decrypt_payload(ciphertext, associated_data=tampered_aad)

    def test_invalid_key_length_raises_value_error(self) -> None:
        """Verifies initialization with invalid key length raises ValueError."""
        with pytest.raises(ValueError, match="AES-256 key must be exactly 32 bytes"):
            CryptoIntegrityManager(secret_key=b"too-short-key")

    def test_explicit_key_property(self) -> None:
        """Verifies explicit 32-byte key is retained and exposed via property."""
        custom_key = b"A" * 32
        mgr = CryptoIntegrityManager(secret_key=custom_key)
        assert mgr.key == custom_key

    def test_decrypt_corrupted_short_payload_raises(
        self, crypto_manager: CryptoIntegrityManager
    ) -> None:
        """Verifies decrypting payload shorter than nonce + tag raises IntegrityError."""
        with pytest.raises(IntegrityError, match="Corrupted ciphertext: payload size is smaller"):
            crypto_manager.decrypt_payload(b"too_short")
