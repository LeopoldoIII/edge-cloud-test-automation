"""Resilience test suite for idempotency, deduplication, and effectively-once guarantees."""

import pytest

from src.core.http_client import ResilientHttpClient
from src.simulators.mock_cloud_gateway import MockCloudGateway


@pytest.mark.resilience
class TestIdempotency:
    """Test suite ensuring duplicate requests do not corrupt cloud pipelines or duplicate records."""

    def test_duplicate_request_idempotent_response(
        self,
        resilient_client: ResilientHttpClient,
        mock_gateway: MockCloudGateway,
    ) -> None:
        """Verifies replaying request with identical idempotency key returns 200 without duplication."""
        fixed_key = "idemp-unique-tx-777"
        payload = {"metric": "patient_pulse", "value": 78}

        # First dispatch
        resp1 = resilient_client.request(
            method="POST",
            path="/api/v1/telemetry",
            idempotency_key=fixed_key,
            json_data=payload,
        )
        assert resp1.status_code == 201
        assert len(mock_gateway.ingested_telemetry) == 1

        # Second dispatch (e.g. simulated edge network retransmission)
        resp2 = resilient_client.request(
            method="POST",
            path="/api/v1/telemetry",
            idempotency_key=fixed_key,
            json_data=payload,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["status"] == "idempotent_duplicate"

        # Crucial assertion: Cloud store still contains exactly ONE entry
        assert len(mock_gateway.ingested_telemetry) == 1

    def test_distinct_keys_create_distinct_records(
        self,
        resilient_client: ResilientHttpClient,
        mock_gateway: MockCloudGateway,
    ) -> None:
        """Verifies that differing idempotency keys produce separate stored records."""
        for i in range(3):
            resp = resilient_client.request(
                method="POST",
                path="/api/v1/telemetry",
                idempotency_key=f"key-batch-{i}",
                json_data={"metric": "flow_rate", "value": i * 10},
            )
            assert resp.status_code == 201

        assert len(mock_gateway.ingested_telemetry) == 3
