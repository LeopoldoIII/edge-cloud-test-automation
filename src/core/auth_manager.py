"""OAuth2 / JWT Authentication and Token Lifecycle Manager."""

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable

from src.core.exceptions import AuthenticationError
from src.core.logger import get_logger

logger = get_logger("auth_manager")


@dataclass
class TokenInfo:
    """Represents an active OAuth2 access token and its metadata."""

    access_token: str
    token_type: str
    expires_at: float  # Unix timestamp
    scope: str = "edge:ingest"

    @property
    def is_expired(self) -> bool:
        """Checks if the token has expired."""
        return time.time() >= self.expires_at

    def is_close_to_expiry(self, buffer_seconds: float = 30.0) -> bool:
        """Checks if token will expire within the buffer window."""
        return (self.expires_at - time.time()) <= buffer_seconds


class OAuth2TokenManager:
    """Manages the full lifecycle of OAuth2 tokens: acquisition, cache, refresh, and revocation."""

    def __init__(
        self,
        token_endpoint: str,
        client_id: str,
        client_secret: str,
        token_requester: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        expiry_buffer_seconds: float = 30.0,
    ) -> None:
        """Initializes the OAuth2 token manager.

        Args:
            token_endpoint: URL of the OAuth2 /token endpoint.
            client_id: Client identifier.
            client_secret: Client secret credential.
            token_requester: Optional callable to issue HTTP request to the auth server.
            expiry_buffer_seconds: Seconds before expiry to proactively trigger refresh.
        """
        self.token_endpoint = token_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        self.expiry_buffer_seconds = expiry_buffer_seconds
        self._token_requester = token_requester
        self._current_token: TokenInfo | None = None
        self._lock = Lock()

    def get_valid_token(self, force_refresh: bool = False) -> str:
        """Retrieves a valid access token, performing proactive refresh if near expiration.

        Args:
            force_refresh: If True, invalidates cached token and acquires a new one.

        Returns:
            Bearer access token string.

        Raises:
            AuthenticationError: If token acquisition fails.
        """
        with self._lock:
            if (
                self._current_token is None
                or force_refresh
                or self._current_token.is_close_to_expiry(self.expiry_buffer_seconds)
            ):
                logger.info(
                    "Requesting fresh OAuth2 token",
                    extra={"device_id": self.client_id, "force_refresh": force_refresh},
                )
                self._current_token = self._fetch_token()
            return self._current_token.access_token

    def invalidate_token(self) -> None:
        """Explicitly invalidates the cached token, typically on HTTP 401 challenge."""
        with self._lock:
            if self._current_token:
                logger.warning(
                    "Invalidating cached OAuth2 token due to 401 challenge or revocation",
                    extra={"device_id": self.client_id},
                )
            self._current_token = None

    def _fetch_token(self) -> TokenInfo:
        """Exchanges client credentials for a new OAuth2 access token."""
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "edge:ingest",
        }

        if self._token_requester is None:
            raise AuthenticationError("Token requester callback is not configured.")

        try:
            response_data = self._token_requester(self.token_endpoint, payload)
        except Exception as exc:
            raise AuthenticationError(f"OAuth2 token request failed: {exc}") from exc

        if "access_token" not in response_data:
            error_desc = response_data.get(
                "error_description", response_data.get("error", "Unknown error")
            )
            raise AuthenticationError(f"Failed to acquire OAuth2 token: {error_desc}")

        expires_in = float(response_data.get("expires_in", 3600))
        expires_at = time.time() + expires_in

        return TokenInfo(
            access_token=str(response_data["access_token"]),
            token_type=str(response_data.get("token_type", "Bearer")),
            expires_at=expires_at,
            scope=str(response_data.get("scope", "edge:ingest")),
        )
