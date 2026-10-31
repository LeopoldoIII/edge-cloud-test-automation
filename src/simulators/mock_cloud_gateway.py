"""In-memory Mock Cloud Ingestion Gateway for integration and resilience testing."""

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.core.crypto_integrity import CryptoIntegrityManager


@dataclass
class UploadedFileSession:
    """Tracks state of a chunked multi-part upload session on the cloud gateway."""

    file_id: str
    expected_chunks: int
    received_chunks: dict[int, bytes] = field(default_factory=dict)
    is_completed: bool = False
    reassembled_sha256: str | None = None


class MockCloudGateway:
    """Simulates an enterprise cloud gateway with OAuth2, idempotency store, and chunked ingestion."""

    def __init__(
        self,
        valid_client_id: str = "valid-edge-client",
        valid_client_secret: str = "secret-key-123",
    ) -> None:
        self.valid_client_id = valid_client_id
        self.valid_client_secret = valid_client_secret

        # In-memory stores
        self.active_tokens: dict[str, float] = {}  # token -> expires_at
        self.revoked_tokens: set[str] = set()
        self.idempotency_store: dict[str, dict[str, Any]] = {}  # key -> cached response
        self.ingested_telemetry: list[dict[str, Any]] = []
        self.upload_sessions: dict[str, UploadedFileSession] = {}

    def handle_oauth_token(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Handles POST /oauth/token."""
        if (
            payload.get("client_id") != self.valid_client_id
            or payload.get("client_secret") != self.valid_client_secret
        ):
            return 401, {"error": "invalid_client", "error_description": "Bad client credentials"}

        token = f"jwt-token-{uuid.uuid4().hex}"
        expires_in = 3600
        self.active_tokens[token] = time.time() + expires_in

        return 200, {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "scope": "edge:ingest",
        }

    def revoke_token(self, token: str) -> None:
        """Revokes an active token."""
        self.revoked_tokens.add(token)
        self.active_tokens.pop(token, None)

    def validate_auth_header(self, auth_header: str | None) -> tuple[bool, str]:
        """Validates Bearer token authenticity and expiration."""
        if not auth_header or not auth_header.startswith("Bearer "):
            return False, "Missing or malformed Authorization header"

        token = auth_header.split(" ", 1)[1]
        if token in self.revoked_tokens:
            return False, "Token has been revoked"

        expires_at = self.active_tokens.get(token)
        if not expires_at or time.time() >= expires_at:
            return False, "Token is expired or invalid"

        return True, "Authorized"

    def handle_telemetry_ingest(
        self,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        """Handles POST /api/v1/telemetry with idempotency deduplication."""
        is_auth, auth_msg = self.validate_auth_header(headers.get("Authorization"))
        if not is_auth:
            return 401, {"error": "unauthorized", "message": auth_msg}

        idempotency_key = headers.get("Idempotency-Key")
        if idempotency_key and idempotency_key in self.idempotency_store:
            # Replay cached response without re-processing (Effectively-Once guarantee)
            cached = self.idempotency_store[idempotency_key]
            return 200, {
                "status": "idempotent_duplicate",
                "idempotency_key": idempotency_key,
                "data": cached,
            }

        # Store new telemetry record
        record_id = str(uuid.uuid4())
        record_entry = {
            "record_id": record_id,
            "payload": payload,
            "device_id": headers.get("X-Device-ID"),
        }
        self.ingested_telemetry.append(record_entry)

        response_body = {"status": "created", "record_id": record_id}
        if idempotency_key:
            self.idempotency_store[idempotency_key] = response_body

        return 201, response_body

    def handle_chunk_upload(
        self,
        headers: dict[str, str],
        file_id: str,
        chunk_index: int,
        total_chunks: int,
        chunk_data: bytes,
    ) -> tuple[int, dict[str, Any]]:
        """Handles POST /api/v1/upload/chunk with chunk checksum and full reassembly check."""
        is_auth, auth_msg = self.validate_auth_header(headers.get("Authorization"))
        if not is_auth:
            return 401, {"error": "unauthorized", "message": auth_msg}

        # Check payload size limit (reject oversized single chunks > 5MB)
        if len(chunk_data) > 5 * 1024 * 1024:
            return 413, {
                "error": "payload_too_large",
                "message": "Chunk exceeds maximum allowed limit",
            }

        # Verify chunk checksum against header
        expected_chunk_sha = headers.get("X-Chunk-SHA256")
        if expected_chunk_sha:
            computed_chunk_sha = hashlib.sha256(chunk_data).hexdigest()
            if computed_chunk_sha.lower() != expected_chunk_sha.lower():
                return 400, {
                    "error": "chunk_integrity_failure",
                    "expected": expected_chunk_sha,
                    "computed": computed_chunk_sha,
                }

        # Retrieve or initialize upload session
        session = self.upload_sessions.setdefault(
            file_id, UploadedFileSession(file_id=file_id, expected_chunks=total_chunks)
        )
        session.received_chunks[chunk_index] = chunk_data

        # Check if all chunks have been received
        if len(session.received_chunks) == total_chunks:
            # Reassemble complete file
            reassembled = b"".join(session.received_chunks[i] for i in range(total_chunks))
            full_sha256 = CryptoIntegrityManager.compute_sha256(reassembled)
            session.is_completed = True
            session.reassembled_sha256 = full_sha256

            return 200, {
                "status": "completed",
                "file_id": file_id,
                "total_chunks": total_chunks,
                "reassembled_sha256": full_sha256,
                "total_bytes": len(reassembled),
            }

        return 202, {
            "status": "chunk_accepted",
            "file_id": file_id,
            "chunk_index": chunk_index,
            "received": len(session.received_chunks),
            "expected": total_chunks,
        }
