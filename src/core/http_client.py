"""Resilient HTTP Client with exponential backoff, jitter, and idempotency tracking."""

import random
import time
import uuid
from typing import Any

import requests

from src.core.auth_manager import OAuth2TokenManager
from src.core.chaos_engine import ChaosEngine
from src.core.exceptions import MaxRetriesExceededError, NetworkResilienceError
from src.core.logger import get_logger

logger = get_logger("resilient_http_client")


class ResilientHttpClient:
    """Enterprise HTTP client built for intermittently connected edge devices."""

    def __init__(
        self,
        base_url: str = "",
        device_id: str | None = None,
        max_retries: int = 3,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 8.0,
        backoff_multiplier: float = 2.0,
        retry_status_codes: set[int] | None = None,
        auth_manager: OAuth2TokenManager | None = None,
        chaos_engine: ChaosEngine | None = None,
        session: requests.Session | None = None,
    ) -> None:
        """Initializes the Resilient HTTP Client.

        Args:
            base_url: Base URL prepended to all relative paths.
            device_id: Unique hardware or logical identifier for this edge device.
            max_retries: Maximum number of retry attempts before giving up.
            base_delay_seconds: Initial backoff delay in seconds.
            max_delay_seconds: Maximum backoff delay cap.
            backoff_multiplier: Multiplier factor for consecutive retry delays.
            retry_status_codes: HTTP status codes to consider transient and retryable.
            auth_manager: Optional OAuth2 token manager for automatic token injection.
            chaos_engine: Optional fault injection engine for resilience tests.
            session: Optional custom requests.Session.
        """
        self.base_url = base_url.rstrip("/")
        self.device_id = device_id or f"edge-dev-{uuid.uuid4().hex[:8]}"
        self.max_retries = max_retries
        self.base_delay = base_delay_seconds
        self.max_delay = max_delay_seconds
        self.backoff_multiplier = backoff_multiplier
        self.retry_status_codes = retry_status_codes or {429, 500, 502, 503, 504}
        self.auth_manager = auth_manager
        self.chaos_engine = chaos_engine
        self.session = session or requests.Session()

    def calculate_backoff(self, attempt: int) -> float:
        """Calculates exponential backoff delay with full jitter.

        Formula: random(0, min(max_delay, base_delay * (multiplier ** attempt)))

        Args:
            attempt: The zero-based attempt index (0 for first retry).

        Returns:
            Jittered delay duration in seconds.
        """
        calculated_delay = self.base_delay * (self.backoff_multiplier**attempt)
        capped_delay = min(self.max_delay, calculated_delay)
        return random.uniform(0.0, capped_delay)

    def request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        data: Any = None,
        json_data: Any = None,
        timeout: float = 10.0,
    ) -> requests.Response:
        """Executes an HTTP request with automatic retry, jitter, and idempotency headers.

        Args:
            method: HTTP verb (GET, POST, PUT, DELETE, etc.).
            path: Target endpoint path or full URL.
            headers: Optional dictionary of HTTP headers.
            idempotency_key: Explicit key for idempotent tracking. If omitted, generates a UUID4.
            correlation_id: Correlation/Request ID. If omitted, generates a UUID4.
            data: Raw or binary body.
            json_data: JSON-serializable dictionary body.
            timeout: Socket timeout in seconds.

        Returns:
            Successful requests.Response object.

        Raises:
            MaxRetriesExceededError: If transient failures persist past max retries.
            AuthenticationError: If auth fails unrecoverably.
        """
        target_url = (
            path
            if path.startswith("http://") or path.startswith("https://")
            else f"{self.base_url}/{path.lstrip('/')}"
        )
        req_headers = dict(headers or {})

        # Correlation and device identification headers
        req_headers.setdefault("X-Device-ID", self.device_id)
        req_headers.setdefault("X-Request-ID", correlation_id or str(uuid.uuid4()))
        if idempotency_key is None and method.upper() in {"POST", "PUT", "PATCH"}:
            idempotency_key = str(uuid.uuid4())
        if idempotency_key:
            req_headers.setdefault("Idempotency-Key", idempotency_key)

        last_status: int | None = None
        last_error_message = ""

        for attempt in range(self.max_retries + 1):
            # Inject Authorization header if auth_manager is available
            if self.auth_manager:
                token = self.auth_manager.get_valid_token()
                req_headers["Authorization"] = f"Bearer {token}"

            # Intercept request via ChaosEngine if configured
            if self.chaos_engine:
                try:
                    injected_status = self.chaos_engine.evaluate_and_intercept(
                        {"method": method, "url": target_url, "attempt": attempt}
                    )
                    if injected_status is not None:
                        last_status = injected_status
                        last_error_message = f"Chaos injected HTTP {injected_status}"
                        if attempt < self.max_retries:
                            backoff = self.calculate_backoff(attempt)
                            logger.warning(
                                "Transient chaos error injected. Retrying with backoff",
                                extra={
                                    "status_code": injected_status,
                                    "retry_attempt": attempt + 1,
                                    "duration_ms": backoff * 1000,
                                },
                            )
                            time.sleep(backoff)
                            continue
                        raise MaxRetriesExceededError(attempt + 1, last_status, last_error_message)
                except MaxRetriesExceededError:
                    raise
                except NetworkResilienceError as nre:
                    last_status = None
                    last_error_message = str(nre)
                    if attempt < self.max_retries:
                        backoff = self.calculate_backoff(attempt)
                        logger.warning(
                            "Network timeout/disconnect occurred. Retrying with backoff",
                            extra={"retry_attempt": attempt + 1, "duration_ms": backoff * 1000},
                        )
                        time.sleep(backoff)
                        continue
                    raise MaxRetriesExceededError(
                        attempt + 1, last_status, last_error_message
                    ) from nre

            # Execute real HTTP request
            try:
                start_time = time.time()
                response = self.session.request(
                    method=method,
                    url=target_url,
                    headers=req_headers,
                    data=data,
                    json=json_data,
                    timeout=timeout,
                )
                duration_ms = (time.time() - start_time) * 1000

                # Handle 401 Unauthorized (reactive refresh)
                if response.status_code == 401 and self.auth_manager and attempt < self.max_retries:
                    logger.warning(
                        "Received HTTP 401 Unauthorized. Refreshing token and retrying",
                        extra={"retry_attempt": attempt + 1},
                    )
                    self.auth_manager.invalidate_token()
                    time.sleep(0.1)
                    continue

                # Handle retryable transient status codes
                if response.status_code in self.retry_status_codes:
                    last_status = response.status_code
                    last_error_message = (
                        f"Server returned {response.status_code}: {response.text[:100]}"
                    )
                    if attempt < self.max_retries:
                        backoff = self.calculate_backoff(attempt)
                        logger.warning(
                            f"HTTP {response.status_code} received. Scheduling retry",
                            extra={
                                "status_code": response.status_code,
                                "retry_attempt": attempt + 1,
                                "duration_ms": backoff * 1000,
                            },
                        )
                        time.sleep(backoff)
                        continue
                    raise MaxRetriesExceededError(attempt + 1, last_status, last_error_message)

                logger.info(
                    "Request succeeded",
                    extra={
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        "retry_attempt": attempt,
                    },
                )
                return response

            except (requests.ConnectionError, requests.Timeout) as exc:
                last_status = None
                last_error_message = f"Socket error: {exc}"
                if attempt < self.max_retries:
                    backoff = self.calculate_backoff(attempt)
                    logger.warning(
                        "Connection/Timeout exception. Retrying with backoff",
                        extra={"retry_attempt": attempt + 1, "duration_ms": backoff * 1000},
                    )
                    time.sleep(backoff)
                    continue
                raise MaxRetriesExceededError(attempt + 1, last_status, last_error_message) from exc

        raise MaxRetriesExceededError(self.max_retries, last_status, last_error_message)
