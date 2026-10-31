"""Observability metrics collector and alerting signal evaluator for edge-to-cloud systems."""

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class MetricRecord:
    """Represents a time-series metric entry."""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """Thread-safe in-memory metrics collector supporting Prometheus-style export and alerting."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._alert_listeners: list[Callable[[str, dict[str, Any]], None]] = []
        self._lock = threading.Lock()

    def register_alert_listener(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """Registers an alerting callback invoked when metric thresholds are breached."""
        self._alert_listeners.append(callback)

    def _format_key(self, name: str, labels: dict[str, str] | None = None) -> str:
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def increment_counter(
        self, name: str, value: float = 1.0, labels: dict[str, str] | None = None
    ) -> float:
        """Increments a monotonically increasing counter.

        Args:
            name: Metric identifier.
            value: Increment value (must be >= 0).
            labels: Optional dimensional labels.

        Returns:
            Updated counter total.
        """
        key = self._format_key(name, labels)
        with self._lock:
            current = self._counters.get(key, 0.0) + value
            self._counters[key] = current

            # Check if this metric triggers an alert condition
            if name == "tamper_detection_total" and current > 0:
                self._dispatch_alert(
                    "SECURITY_ALERT_PAYLOAD_TAMPERING",
                    {"metric": key, "value": current, "severity": "CRITICAL"},
                )
            elif name == "retry_attempts_total" and current >= 5:
                self._dispatch_alert(
                    "HIGH_NETWORK_DEGRADATION_ALERT",
                    {"metric": key, "value": current, "severity": "WARNING"},
                )

            return current

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Sets an instantaneous gauge measurement."""
        key = self._format_key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def observe_histogram(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Records an observed duration or size in a histogram bucket."""
        key = self._format_key(name, labels)
        with self._lock:
            self._histograms.setdefault(key, []).append(value)

    def get_counter_value(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Retrieves current counter value."""
        key = self._format_key(name, labels)
        with self._lock:
            return self._counters.get(key, 0.0)

    def get_gauge_value(self, name: str, labels: dict[str, str] | None = None) -> float | None:
        """Retrieves current gauge value."""
        key = self._format_key(name, labels)
        with self._lock:
            return self._gauges.get(key)

    def export_prometheus_text(self) -> str:
        """Exports metrics in standard Prometheus exposition format."""
        lines: list[str] = []
        with self._lock:
            for key, val in sorted(self._counters.items()):
                metric_name = key.split("{")[0]
                lines.append(f"# TYPE {metric_name} counter")
                lines.append(f"{key} {val}")

            for key, val in sorted(self._gauges.items()):
                metric_name = key.split("{")[0]
                lines.append(f"# TYPE {metric_name} gauge")
                lines.append(f"{key} {val}")

            for key, values in sorted(self._histograms.items()):
                metric_name = key.split("{")[0]
                count = len(values)
                total = sum(values)
                lines.append(f"# TYPE {metric_name} histogram")
                lines.append(f"{metric_name}_count {count}")
                lines.append(f"{metric_name}_sum {total:.4f}")

        return "\n".join(lines) + "\n"

    def _dispatch_alert(self, alert_name: str, payload: dict[str, Any]) -> None:
        for listener in self._alert_listeners:
            listener(alert_name, payload)


# Global default collector
global_metrics = MetricsCollector()
