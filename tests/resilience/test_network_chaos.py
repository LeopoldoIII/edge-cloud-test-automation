"""Resilience test suite for network disruptions, timeouts, and exponential backoff."""

import time
import pytest

from src.core.chaos_engine import ChaosEngine, ChaosPolicy
from src.core.exceptions import MaxRetriesExceededError
from src.core.http_client import ResilientHttpClient


@pytest.mark.resilience
class TestNetworkChaos:
    """Test suite validating client resilience under transient HTTP 5xx faults and network drops."""

    def test_intermittent_503_recovery(self, resilient_client: ResilientHttpClient) -> None:
        """Verifies successful recovery when cloud returns 503 twice before succeeding."""
        resilient_client.chaos_engine = ChaosEngine(
            ChaosPolicy(failure_rate=1.0, status_codes=[503], failure_budget=2)
        )

        start = time.time()
        resp = resilient_client.request(
            method="POST",
            path="/api/v1/telemetry",
            json_data={"metric": "pressure", "value": 101.3},
        )
        elapsed = time.time() - start

        assert resp.status_code == 201
        assert resilient_client.chaos_engine.injected_failure_count == 2
        assert elapsed >= 0.01  # Backoff delay took place

    def test_simulated_socket_timeout_retry(self, resilient_client: ResilientHttpClient) -> None:
        """Verifies retry and recovery when encountering simulated network socket timeout."""
        resilient_client.chaos_engine = ChaosEngine(
            ChaosPolicy(
                failure_rate=1.0,
                simulate_timeout=True,
                timeout_duration_seconds=0.01,
                failure_budget=1,
            )
        )

        resp = resilient_client.request(
            method="POST",
            path="/api/v1/telemetry",
            json_data={"metric": "vibration", "value": 0.04},
        )
        assert resp.status_code == 201
        assert resilient_client.chaos_engine.injected_failure_count == 1

    def test_permanent_outage_raises_max_retries_error(
        self, resilient_client: ResilientHttpClient
    ) -> None:
        """Verifies that persistent outage is caught and reported deterministically."""
        resilient_client.chaos_engine = ChaosEngine(
            ChaosPolicy(failure_rate=1.0, status_codes=[502, 504])
        )

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            resilient_client.request(
                method="POST",
                path="/api/v1/telemetry",
                json_data={"metric": "permanent_fail"},
            )

        assert exc_info.value.attempts == resilient_client.max_retries + 1

    def test_chaos_engine_latency_and_reset(self) -> None:
        """Verifies ChaosEngine injects latency and resets evaluation statistics."""
        engine = ChaosEngine(ChaosPolicy(latency_min_ms=5.0, latency_max_ms=10.0))
        start = time.time()
        engine.evaluate_and_intercept()
        elapsed = time.time() - start
        assert elapsed >= 0.004
        assert engine.total_evaluations == 1

        engine.reset_stats()
        assert engine.total_evaluations == 0
