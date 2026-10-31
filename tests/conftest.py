"""Global pytest configuration, hooks, and shared fixtures."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from src.core.auth_manager import OAuth2TokenManager
from src.core.chaos_engine import ChaosEngine, ChaosPolicy
from src.core.crypto_integrity import CryptoIntegrityManager
from src.core.http_client import ResilientHttpClient
from src.simulators.mock_cloud_gateway import MockCloudGateway


class MockGatewayAdapter(requests.adapters.HTTPAdapter):
    """Custom requests adapter that routes HTTP calls directly to in-memory MockCloudGateway."""

    def __init__(self, gateway: MockCloudGateway) -> None:
        super().__init__()
        self.gateway = gateway

    def send(  # type: ignore[override]
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: float | None = None,
        verify: bool = True,
        cert: Any = None,
        proxies: Any = None,
    ) -> requests.Response:
        url = request.url or ""
        headers = {k: v for k, v in request.headers.items()}
        body = request.body

        response = requests.Response()
        response.request = request
        response.url = url

        if "/oauth/token" in url:
            payload = (
                json.loads(body.decode("utf-8"))
                if isinstance(body, bytes)
                else json.loads(body or "{}")
            )
            status, data = self.gateway.handle_oauth_token(payload)
            response.status_code = status
            response._content = json.dumps(data).encode("utf-8")
        elif "/api/v1/telemetry" in url:
            payload = (
                json.loads(body.decode("utf-8"))
                if isinstance(body, bytes)
                else json.loads(body or "{}")
            )
            status, data = self.gateway.handle_telemetry_ingest(headers, payload)
            response.status_code = status
            response._content = json.dumps(data).encode("utf-8")
        elif "/api/v1/upload/chunk" in url:
            file_id = headers.get("X-File-ID", "default-file")
            chunk_idx = int(headers.get("X-Chunk-Index", 0))
            total_chunks = int(headers.get("X-Total-Chunks", 1))
            chunk_bytes = body if isinstance(body, bytes) else b""
            status, data = self.gateway.handle_chunk_upload(
                headers, file_id, chunk_idx, total_chunks, chunk_bytes
            )
            response.status_code = status
            response._content = json.dumps(data).encode("utf-8")
        else:
            response.status_code = 404
            response._content = json.dumps({"error": "not_found"}).encode("utf-8")

        return response


@pytest.fixture
def crypto_manager() -> CryptoIntegrityManager:
    """Provides a fresh CryptoIntegrityManager instance."""
    return CryptoIntegrityManager()


@pytest.fixture
def mock_gateway() -> MockCloudGateway:
    """Provides an isolated MockCloudGateway instance."""
    return MockCloudGateway(
        valid_client_id="edge-test-client", valid_client_secret="test-secret-456"
    )


@pytest.fixture
def auth_manager(mock_gateway: MockCloudGateway) -> OAuth2TokenManager:
    """Provides an OAuth2TokenManager wired to the mock gateway."""

    def requester(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        _, data = mock_gateway.handle_oauth_token(payload)
        return data

    return OAuth2TokenManager(
        token_endpoint="https://cloud.internal/oauth/token",
        client_id="edge-test-client",
        client_secret="test-secret-456",
        token_requester=requester,
    )


@pytest.fixture
def gateway_session(mock_gateway: MockCloudGateway) -> requests.Session:
    """Provides a requests.Session wired directly to the MockCloudGateway."""
    session = requests.Session()
    adapter = MockGatewayAdapter(mock_gateway)
    session.mount("https://cloud.internal", adapter)
    session.mount("http://cloud.internal", adapter)
    return session


@pytest.fixture
def resilient_client(
    auth_manager: OAuth2TokenManager,
    gateway_session: requests.Session,
) -> ResilientHttpClient:
    """Provides a ResilientHttpClient pointing to the mock cloud gateway."""
    return ResilientHttpClient(
        base_url="https://cloud.internal",
        device_id="edge-dev-001",
        max_retries=3,
        base_delay_seconds=0.01,  # Fast backoff for unit & integration testing
        max_delay_seconds=0.05,
        auth_manager=auth_manager,
        session=gateway_session,
    )
