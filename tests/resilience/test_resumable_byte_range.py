"""Resilience test suite validating HTTP Content-Range resumable uploads after connection drops."""

import pytest

from src.core.crypto_integrity import CryptoIntegrityManager
from src.core.http_client import ResilientHttpClient
from src.simulators.mock_cloud_gateway import MockCloudGateway


@pytest.mark.resilience
class TestResumableByteRange:
    """Test suite validating byte-range resume, out-of-order rejection, and checksum verification."""

    def test_interrupted_upload_resumes_from_exact_offset(
        self,
        resilient_client: ResilientHttpClient,
        mock_gateway: MockCloudGateway,
    ) -> None:
        """Verifies interrupted byte-range upload recovers and finishes without re-sending transmitted bytes."""
        file_id = "resumable-scan-5501"
        full_content = b"BinaryEdgeDataPackage" * 50  # 1050 bytes
        total_bytes = len(full_content)
        split_point = 500

        part1 = full_content[:split_point]
        part2 = full_content[split_point:]

        # 1. Transmit Part 1 (0 to 499)
        resp1 = resilient_client.request(
            method="PATCH",
            path=f"/api/v1/upload/resumable/{file_id}",
            headers={"Content-Range": f"bytes 0-{split_point - 1}/{total_bytes}"},
            data=part1,
        )
        assert resp1.status_code == 206
        assert resp1.json()["uploaded_bytes"] == split_point

        # 2. Simulate edge network drop & reconnection: Client queries status
        status_resp = resilient_client.request(
            method="GET",
            path=f"/api/v1/upload/resumable/{file_id}/status",
        )
        assert status_resp.status_code == 200
        current_offset = status_resp.json()["uploaded_bytes"]
        assert current_offset == split_point

        # 3. Resume sending Part 2 from the current offset
        resp2 = resilient_client.request(
            method="PATCH",
            path=f"/api/v1/upload/resumable/{file_id}",
            headers={"Content-Range": f"bytes {current_offset}-{total_bytes - 1}/{total_bytes}"},
            data=part2,
        )
        assert resp2.status_code == 200
        final_body = resp2.json()
        assert final_body["status"] == "completed"
        assert final_body["sha256"] == CryptoIntegrityManager.compute_sha256(full_content)

    def test_gap_in_byte_range_returns_416_range_not_satisfiable(
        self,
        resilient_client: ResilientHttpClient,
    ) -> None:
        """Verifies that attempting to skip bytes produces HTTP 416 Range Not Satisfiable."""
        file_id = "gap-check-99"

        # Attempt to send bytes 200-300 when current offset is 0
        resp = resilient_client.request(
            method="PATCH",
            path=f"/api/v1/upload/resumable/{file_id}",
            headers={"Content-Range": "bytes 200-300/1000"},
            data=b"Z" * 101,
        )
        assert resp.status_code == 416
        assert resp.json()["error"] == "range_not_satisfiable"
