"""Custom exception hierarchy for the Edge-to-Cloud framework."""


class EdgeFrameworkError(Exception):
    """Base exception for all framework-specific errors."""


class IntegrityError(EdgeFrameworkError):
    """Raised when cryptographic checksum or authentication tag validation fails."""


class NetworkResilienceError(EdgeFrameworkError):
    """Base exception for network and connectivity failures."""


class MaxRetriesExceededError(NetworkResilienceError):
    """Raised when all retry attempts with backoff are exhausted."""

    def __init__(self, attempts: int, last_status: int | None, message: str) -> None:
        super().__init__(f"Exceeded {attempts} retries. Last status: {last_status}. {message}")
        self.attempts = attempts
        self.last_status = last_status


class AuthenticationError(EdgeFrameworkError):
    """Raised when OAuth2 or identity verification fails."""


class IdempotencyConflictError(EdgeFrameworkError):
    """Raised when an unrecoverable idempotency or replay conflict occurs."""
