"""Integration tests validating edge-to-cloud observability, health checks, and alerting signals."""

from typing import Any
import pytest

from src.core.http_client import ResilientHttpClient
from src.core.metrics import MetricsCollector


@pytest.mark.integration
class TestObservability:
    """Test suite validating health probes, metrics aggregation, and alert dispatchers."""

    def test_health_probes(self, resilient_client: ResilientHttpClient) -> None:
        """Verifies liveness and readiness probe responses."""
        live_resp = resilient_client.request("GET", "/health/live")
        assert live_resp.status_code == 200
        assert live_resp.json()["status"] == "alive"

        ready_resp = resilient_client.request("GET", "/health/ready")
        assert ready_resp.status_code == 200
        data = ready_resp.json()
        assert data["status"] == "ready"
        assert data["services"]["database"] == "up"

    def test_metrics_collection_and_prometheus_export(self) -> None:
        """Verifies counters, gauges, histograms and Prometheus exposition formatting."""
        collector = MetricsCollector()
        collector.increment_counter(
            "edge_telemetry_uploaded_total", value=5, labels={"device": "edge-01"}
        )
        collector.set_gauge("edge_cpu_temp_gauge", value=58.2, labels={"device": "edge-01"})
        collector.observe_histogram("edge_upload_duration_seconds", value=0.125)

        assert (
            collector.get_counter_value(
                "edge_telemetry_uploaded_total", labels={"device": "edge-01"}
            )
            == 5
        )
        assert (
            collector.get_gauge_value("edge_cpu_temp_gauge", labels={"device": "edge-01"}) == 58.2
        )

        prometheus_text = collector.export_prometheus_text()
        assert "# TYPE edge_telemetry_uploaded_total counter" in prometheus_text
        assert 'edge_telemetry_uploaded_total{device="edge-01"} 5.0' in prometheus_text
        assert "# TYPE edge_cpu_temp_gauge gauge" in prometheus_text

    def test_alerting_signal_on_tamper_detection(self) -> None:
        """Verifies alerting signals trigger when tamper events occur."""
        collector = MetricsCollector()
        dispatched_alerts: list[dict[str, Any]] = []

        def alert_handler(name: str, payload: dict[str, Any]) -> None:
            dispatched_alerts.append({"alert": name, **payload})

        collector.register_alert_listener(alert_handler)
        collector.increment_counter("tamper_detection_total", value=1)

        assert len(dispatched_alerts) == 1
        assert dispatched_alerts[0]["alert"] == "SECURITY_ALERT_PAYLOAD_TAMPERING"
        assert dispatched_alerts[0]["severity"] == "CRITICAL"

    def test_high_retry_warning_alert(self) -> None:
        """Verifies warning alert triggers when retry attempts cross failure threshold."""
        collector = MetricsCollector()
        alerts: list[str] = []

        collector.register_alert_listener(lambda name, payload: alerts.append(name))
        collector.increment_counter("retry_attempts_total", value=5)

        assert "HIGH_NETWORK_DEGRADATION_ALERT" in alerts
