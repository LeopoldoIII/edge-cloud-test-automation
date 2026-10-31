"""Security test suite validating data integrity, tampering detection, and authorization controls."""

import pytest

from src.core.crypto_integrity import CryptoIntegrityManager
from src.core.exceptions import IntegrityError
from src.core.http_client import ResilientHttpClient
from src.generators.edge_file_generator import EdgeFileGenerator


@pytest.mark.security
class TestPayloadTampering:
    """Test suite ensuring corrupted payloads, checksum discrepancies, and unauthorized requests are blocked."""

    def test_chunk_checksum_mismatch_rejected(
        self,
        resilient_client: ResilientHttpClient,
    ) -> None:
        """Verifies gateway rejects chunk when content does not match X-Chunk-SHA256 header."""
        valid_bytes = b"Legitimate clinical sensor data"
        tampered_bytes = b"Corrupted clinical sensor data"
        valid_checksum = CryptoIntegrityManager.compute_sha256(valid_bytes)

        # Upload with mismatched checksum header
        resp = resilient_client.request(
            method="POST",
            path="/api/v1/upload/chunk",
            headers={
                "X-File-ID": "tamper-file-01",
                "X-Chunk-Index": "0",
                "X-Total-Chunks": "1",
                "X-Chunk-SHA256": valid_checksum,
            },
            data=tampered_bytes,
        )

        assert resp.status_code == 400
        error_body = resp.json()
        assert error_body["error"] == "chunk_integrity_failure"

    def test_oversized_payload_rejected(
        self,
        resilient_client: ResilientHttpClient,
    ) -> None:
        """Verifies gateway enforces payload limits and rejects oversized payloads with HTTP 413."""
        # 6MB payload (limit is 5MB)
        oversized = b"X" * (6 * 1024 * 1024)

        resp = resilient_client.request(
            method="POST",
            path="/api/v1/upload/chunk",
            headers={
                "X-File-ID": "oversized-file",
                "X-Chunk-Index": "0",
                "X-Total-Chunks": "1",
            },
            data=oversized,
        )

        assert resp.status_code == 413
        assert resp.json()["error"] == "payload_too_large"

    def test_tampered_encrypted_payload_detection(
        self,
        crypto_manager: CryptoIntegrityManager,
    ) -> None:
        """Verifies end-to-end cryptographic tampering detection under bit-flip attack."""
        sensitive_telemetry = b"Patient-UID=9981;BloodOxygen=99.2;Status=CRITICAL"
        encrypted = crypto_manager.encrypt_payload(sensitive_telemetry)

        # Apply synthetic bit flip corruption
        corrupted = EdgeFileGenerator.mutate_corrupt_bytes(encrypted, mutation_rate=0.05)

        with pytest.raises(IntegrityError):
            crypto_manager.decrypt_payload(corrupted)
