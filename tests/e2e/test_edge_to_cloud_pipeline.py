"""End-to-End tests validating the full device-to-cloud file capture, chunking, and upload pipeline."""

import pytest

from src.core.chaos_engine import ChaosEngine, ChaosPolicy
from src.core.crypto_integrity import CryptoIntegrityManager
from src.core.http_client import ResilientHttpClient
from src.generators.edge_file_generator import EdgeFileGenerator
from src.simulators.mock_cloud_gateway import MockCloudGateway


@pytest.mark.e2e
class TestEdgeToCloudPipeline:
    """Test suite validating full edge capture -> chunking -> resilient upload -> cloud verification."""

    def test_full_pipeline_multi_chunk_resilience(
        self,
        resilient_client: ResilientHttpClient,
        mock_gateway: MockCloudGateway,
        crypto_manager: CryptoIntegrityManager,
    ) -> None:
        """Verifies end-to-end multi-chunk file upload surviving transient network faults."""
        # 1. Edge generates a 1MB payload package
        original_data = EdgeFileGenerator.create_binary_package(size_bytes=1024 * 1024)
        original_sha256 = crypto_manager.compute_sha256(original_data)

        # 2. Chunk into 256KB segments
        file_id = "imaging-study-scan-4040"
        chunks = EdgeFileGenerator.chunk_payload(
            file_id=file_id, data=original_data, chunk_size=256 * 1024
        )
        assert len(chunks) == 4

        # 3. Configure ChaosEngine with transient 503 failures on the uplink
        resilient_client.chaos_engine = ChaosEngine(
            ChaosPolicy(failure_rate=0.75, status_codes=[503], failure_budget=2)
        )

        # 4. Upload all chunks sequentially
        last_response = None
        for chunk in chunks:
            last_response = resilient_client.request(
                method="POST",
                path="/api/v1/upload/chunk",
                headers={
                    "X-File-ID": chunk.file_id,
                    "X-Chunk-Index": str(chunk.chunk_index),
                    "X-Total-Chunks": str(chunk.total_chunks),
                    "X-Chunk-SHA256": chunk.chunk_sha256,
                },
                data=chunk.chunk_bytes,
            )

        # 5. Assertions on final cloud state
        assert last_response is not None
        assert last_response.status_code == 200
        completed_body = last_response.json()

        assert completed_body["status"] == "completed"
        assert completed_body["file_id"] == file_id
        assert completed_body["reassembled_sha256"] == original_sha256
        assert completed_body["total_bytes"] == len(original_data)

        # Gateway session verification
        session = mock_gateway.upload_sessions[file_id]
        assert session.is_completed is True
        assert session.reassembled_sha256 == original_sha256
