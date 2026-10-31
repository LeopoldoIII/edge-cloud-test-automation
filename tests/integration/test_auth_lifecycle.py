"""Integration tests for OAuth2 token lifecycle, expiration, refresh, and revocation."""

import time
import pytest

from src.core.auth_manager import OAuth2TokenManager
from src.core.exceptions import AuthenticationError
from src.core.http_client import ResilientHttpClient
from src.simulators.mock_cloud_gateway import MockCloudGateway


@pytest.mark.integration
class TestAuthLifecycle:
    """Test suite for OAuth2 client credentials, proactive refresh, and reactive 401 recovery."""

    def test_token_acquisition_success(self, auth_manager: OAuth2TokenManager) -> None:
        """Verifies successful token exchange with client credentials."""
        token = auth_manager.get_valid_token()
        assert token.startswith("jwt-token-")

    def test_token_acquisition_invalid_credentials_fails(
        self, mock_gateway: MockCloudGateway
    ) -> None:
        """Verifies rejection of invalid client credentials."""
        manager = OAuth2TokenManager(
            token_endpoint="https://cloud.internal/oauth/token",
            client_id="invalid-client-id",
            client_secret="wrong-secret",
            token_requester=lambda url, body: mock_gateway.handle_oauth_token(body)[1],
        )

        with pytest.raises(AuthenticationError, match="Bad client credentials"):
            manager.get_valid_token()

    def test_proactive_token_refresh(self, auth_manager: OAuth2TokenManager) -> None:
        """Verifies token is refreshed when remaining validity is under expiry buffer."""
        initial_token = auth_manager.get_valid_token()

        # Simulate approaching expiration by setting expiry to now + 10s (buffer is 30s)
        assert auth_manager._current_token is not None
        auth_manager._current_token.expires_at = time.time() + 10.0

        refreshed_token = auth_manager.get_valid_token()
        assert refreshed_token != initial_token

    def test_reactive_token_refresh_on_revocation(
        self,
        resilient_client: ResilientHttpClient,
        mock_gateway: MockCloudGateway,
    ) -> None:
        """Verifies client catches 401 on revoked token, invalidates cache, and recovers."""
        # Initial successful request
        resp1 = resilient_client.request(
            method="POST",
            path="/api/v1/telemetry",
            json_data={"metric": "initial"},
        )
        assert resp1.status_code == 201

        # Revoke the active token on the gateway
        assert resilient_client.auth_manager is not None
        cached_token = resilient_client.auth_manager.get_valid_token()
        mock_gateway.revoke_token(cached_token)

        # Subsequent request should receive 401, refresh token automatically, and succeed
        resp2 = resilient_client.request(
            method="POST",
            path="/api/v1/telemetry",
            json_data={"metric": "after_revocation"},
        )
        assert resp2.status_code == 201
        new_token = resilient_client.auth_manager.get_valid_token()
        assert new_token != cached_token

    def test_missing_requester_raises_auth_error(self) -> None:
        """Verifies missing requester callback raises AuthenticationError."""
        manager = OAuth2TokenManager(
            token_endpoint="https://cloud.internal/oauth/token",
            client_id="test",
            client_secret="test",
            token_requester=None,
        )
        with pytest.raises(AuthenticationError, match="Token requester callback is not configured"):
            manager.get_valid_token()
