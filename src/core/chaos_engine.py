"""Chaos and network fault simulation engine for edge-to-cloud resilience testing."""

import random
import time
from dataclasses import dataclass, field
from typing import Any

from src.core.exceptions import NetworkResilienceError
from src.core.logger import get_logger

logger = get_logger("chaos_engine")


@dataclass
class ChaosPolicy:
    """Defines fault injection rules for network simulations."""

    failure_rate: float = 0.0  # Probability of fault between 0.0 and 1.0
    status_codes: list[int] = field(default_factory=lambda: [502, 503, 504])
    simulate_timeout: bool = False
    timeout_duration_seconds: float = 2.0
    latency_min_ms: float = 0.0
    latency_max_ms: float = 0.0
    failure_budget: int | None = None  # Maximum number of times to inject failure before recovering


class ChaosEngine:
    """Intercepts and injects synthetic network anomalies into outgoing requests."""

    def __init__(self, policy: ChaosPolicy | None = None) -> None:
        """Initializes the chaos engine with a given fault policy.

        Args:
            policy: Configuration specifying failure rates, status codes, and latency.
        """
        self.policy = policy or ChaosPolicy()
        self.injected_failure_count: int = 0
        self.total_evaluations: int = 0

    def reset_stats(self) -> None:
        """Resets the failure counters."""
        self.injected_failure_count = 0
        self.total_evaluations = 0

    def evaluate_and_intercept(self, request_context: dict[str, Any] | None = None) -> int | None:
        """Evaluates whether to inject a fault into the current request execution.

        Args:
            request_context: Optional metadata dictionary about the current request.

        Returns:
            Injected HTTP status code (e.g., 503) if a status fault is triggered, None if clean.

        Raises:
            NetworkResilienceError: If a simulated network timeout or socket disconnect is triggered.
        """
        self.total_evaluations += 1

        # Check if failure budget has been reached
        if (
            self.policy.failure_budget is not None
            and self.injected_failure_count >= self.policy.failure_budget
        ):
            logger.info("Chaos failure budget exhausted. Allowing request through.")
            return None

        # Simulate network latency/jitter if configured
        if self.policy.latency_max_ms > 0:
            delay_sec = (
                random.uniform(self.policy.latency_min_ms, self.policy.latency_max_ms) / 1000.0
            )
            time.sleep(delay_sec)

        # Evaluate failure probability
        if self.policy.failure_rate > 0 and random.random() < self.policy.failure_rate:
            self.injected_failure_count += 1

            if self.policy.simulate_timeout:
                logger.warning(
                    "ChaosEngine injected network timeout",
                    extra={"duration_ms": self.policy.timeout_duration_seconds * 1000},
                )
                time.sleep(self.policy.timeout_duration_seconds)
                raise NetworkResilienceError(
                    f"Simulated network timeout after {self.policy.timeout_duration_seconds}s"
                )

            status = random.choice(self.policy.status_codes)
            logger.warning(
                "ChaosEngine injected transient HTTP status", extra={"status_code": status}
            )
            return status

        return None
