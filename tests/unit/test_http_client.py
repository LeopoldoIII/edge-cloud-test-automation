"""Unit tests for ResilientHttpClient backoff, retry curves, and header injection."""

import pytest
import requests

from src.core.chaos_engine import ChaosEngine, ChaosPolicy
from src.core.exceptions import MaxRetriesExceededError
from src.core.http_client import ResilientHttpClient
from src.simulators.mock_cloud_gateway import MockCloudGateway


@pytest.mark.unit
class TestResilientHttpClient:
    """Test suite for HTTP client resilience, exponential backoff, and idempotency headers."""

    def test_calculate_backoff_bounds(self) -> None:
        """Verifies that exponential backoff with full jitter stays within calculated bounds."""
        client = ResilientHttpClient(
            base_delay_seconds=1.0,
            max_delay_seconds=10.0,
            backoff_multiplier=2.0,
        )

        for attempt in range(5):
            delay = client.calculate_backoff(attempt)
            upper_bound = min(10.0, 1.0 * (2.0**attempt))
            assert 0.0 <= delay <= upper_bound

    def test_header_injection(
        self,
        resilient_client: ResilientHttpClient,
        mock_gateway: MockCloudGateway,
    ) -> None:
        """Verifies automatic injection of X-Device-ID, X-Request-ID, and Idempotency-Key."""
        response = resilient_client.request(
            method="POST",
            path="/api/v1/telemetry",
            json_data={"metric": "cpu_usage", "value": 45.2},
        )
        assert response.status_code == 201

        # Check recorded telemetry on mock gateway
        assert len(mock_gateway.ingested_telemetry) == 1
        record = mock_gateway.ingested_telemetry[0]
        assert record["device_id"] == resilient_client.device_id

    def test_retry_on_chaos_transient_failure(
        self,
        resilient_client: ResilientHttpClient,
    ) -> None:
        """Verifies that client retries upon transient 503 errors and succeeds within budget."""
        # Attach chaos engine that fails twice with 503 then succeeds
        resilient_client.chaos_engine = ChaosEngine(
            ChaosPolicy(failure_rate=1.0, status_codes=[503], failure_budget=2)
        )

        response = resilient_client.request(
            method="POST",
            path="/api/v1/telemetry",
            json_data={"metric": "temperature", "value": 52.1},
        )
        assert response.status_code == 201
        assert resilient_client.chaos_engine.injected_failure_count == 2

    def test_max_retries_exceeded_raises_error(
        self,
        resilient_client: ResilientHttpClient,
    ) -> None:
        """Verifies that exceeding retry threshold raises MaxRetriesExceededError."""
        # Chaos engine configured to fail indefinitely
        resilient_client.chaos_engine = ChaosEngine(
            ChaosPolicy(failure_rate=1.0, status_codes=[504])
        )

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            resilient_client.request(
                method="POST",
                path="/api/v1/telemetry",
                json_data={"metric": "test"},
            )

        assert exc_info.value.attempts == resilient_client.max_retries + 1
        assert exc_info.value.last_status == 504

    def test_socket_connection_error_retry_and_exhaustion(
        self, resilient_client: ResilientHttpClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies retry and exhaustion upon requests.ConnectionError."""
        from unittest.mock import MagicMock

        mock_send = MagicMock(side_effect=requests.ConnectionError("Network unreachable"))
        monkeypatch.setattr(resilient_client.session, "request", mock_send)

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            resilient_client.request("POST", "/api/v1/telemetry", json_data={"a": 1})

        assert exc_info.value.attempts == resilient_client.max_retries + 1
        assert "Socket error" in str(exc_info.value)

    def test_transient_server_status_retry_and_recovery(
        self, resilient_client: ResilientHttpClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies retry and eventual success when server responds with 502 then 200."""
        from unittest.mock import MagicMock

        resp_502 = requests.Response()
        resp_502.status_code = 502
        resp_502._content = b"Bad Gateway"

        resp_200 = requests.Response()
        resp_200.status_code = 200
        resp_200._content = b'{"status": "ok"}'

        mock_send = MagicMock(side_effect=[resp_502, resp_200])
        monkeypatch.setattr(resilient_client.session, "request", mock_send)

        resp = resilient_client.request("GET", "/health")
        assert resp.status_code == 200
        assert mock_send.call_count == 2
