"""Integration tests for edge device provisioning, header contracts, and authorization gates."""

from typing import Any
import pytest

from src.core.http_client import ResilientHttpClient
from src.simulators.mock_cloud_gateway import MockCloudGateway


@pytest.mark.integration
class TestDeviceProvisioning:
    """Test suite for edge device identity handshakes, header assertions, and access gates."""

    def test_device_headers_contract(
        self,
        resilient_client: ResilientHttpClient,
        mock_gateway: MockCloudGateway,
    ) -> None:
        """Verifies that all device requests carry mandatory identity headers."""
        custom_corr_id = "corr-test-trace-999"
        resilient_client.request(
            method="POST",
            path="/api/v1/telemetry",
            correlation_id=custom_corr_id,
            json_data={"status": "online"},
        )

        assert len(mock_gateway.ingested_telemetry) == 1
        record = mock_gateway.ingested_telemetry[0]
        assert record["device_id"] == resilient_client.device_id

    def test_unauthorized_direct_access_rejected(
        self,
        mock_gateway: MockCloudGateway,
    ) -> None:
        """Verifies that requests omitting Authorization header are blocked with HTTP 401."""
        status, response = mock_gateway.handle_telemetry_ingest(
            headers={},  # Missing Authorization
            payload={"metric": "unauthorized_attempt"},
        )
        assert status == 401
        assert response["error"] == "unauthorized"

    def test_spool_custom_dispatcher_and_partial_failure(
        self, resilient_client: ResilientHttpClient
    ) -> None:
        """Verifies spool draining with custom dispatcher handling partial failures."""
        from src.simulators.edge_device_spool import EdgeDeviceSpool

        spool = EdgeDeviceSpool(device_id="dev-spool-01", client=resilient_client)
        spool.enqueue("/api/v1/telemetry", {"batch": 1})
        spool.enqueue("/api/v1/telemetry", {"batch": 2})

        # Custom dispatcher fails batch 2
        def dispatcher(ep: str, p: dict[str, Any], k: str) -> bool:
            return p.get("batch") == 1

        synced = spool.drain_all(custom_dispatcher=dispatcher)
        assert synced == 1
        assert spool.pending_count == 1
        assert spool.queue[0].retry_count == 1
