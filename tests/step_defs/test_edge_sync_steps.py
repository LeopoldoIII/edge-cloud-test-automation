"""Pytest-BDD Step Definitions binding edge_to_cloud_sync.feature to Python automation logic."""

from typing import Any
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from src.core.chaos_engine import ChaosEngine, ChaosPolicy
from src.core.http_client import ResilientHttpClient
from src.generators.payload_factory import generate_medical_telemetry_batch
from src.simulators.edge_device_spool import EdgeDeviceSpool
from src.simulators.mock_cloud_gateway import MockCloudGateway

# Bind Gherkin feature file
scenarios("../../features/edge_to_cloud_sync.feature")


@pytest.fixture
def bdd_context() -> dict[str, Any]:
    """Shared execution context dictionary across BDD steps."""
    return {}


@given(parsers.parse("a Linux edge device with {count:d} spooled medical telemetry batches"))
def setup_edge_spool(
    count: int,
    resilient_client: ResilientHttpClient,
    bdd_context: dict[str, Any],
) -> None:
    """Enqueues synthetic medical batches into the local edge spool."""
    spool = EdgeDeviceSpool(device_id="edge-linux-station-07", client=resilient_client)
    for i in range(count):
        batch = generate_medical_telemetry_batch(device_id=spool.device_id, reading_count=3)
        spool.enqueue(endpoint="/api/v1/telemetry", payload=batch.model_dump(mode="json"))

    assert spool.pending_count == count
    bdd_context["spool"] = spool
    bdd_context["initial_count"] = count


@given("the cloud gateway experiences intermittent 503 transient failures")
def configure_chaos_failures(
    resilient_client: ResilientHttpClient, bdd_context: dict[str, Any]
) -> None:
    """Attaches a chaos policy injecting 503 errors on the uplink."""
    chaos = ChaosEngine(ChaosPolicy(failure_rate=1.0, status_codes=[503], failure_budget=2))
    resilient_client.chaos_engine = chaos
    bdd_context["chaos"] = chaos


@when("the edge device initiates spool synchronization")
def drain_spool(bdd_context: dict[str, Any]) -> None:
    """Drains all spooled items across the resilient client."""
    spool: EdgeDeviceSpool = bdd_context["spool"]
    synced = spool.drain_all()
    bdd_context["synced_count"] = synced


@then("the resilient client retries with exponential backoff and jitter")
def verify_retries_occurred(bdd_context: dict[str, Any]) -> None:
    """Verifies that the chaos engine intercepted and forced retries."""
    chaos: ChaosEngine = bdd_context["chaos"]
    assert chaos.injected_failure_count == 2


@then(
    parsers.parse(
        "all {count:d} telemetry batches are successfully acknowledged by the cloud gateway"
    )
)
def verify_all_synced(count: int, bdd_context: dict[str, Any]) -> None:
    """Verifies that all items drained from local storage."""
    spool: EdgeDeviceSpool = bdd_context["spool"]
    assert bdd_context["synced_count"] == count
    assert spool.pending_count == 0
    assert len(spool.synced_items) == count


@then("the cloud gateway processes each batch effectively once with zero duplicates")
def verify_effectively_once(mock_gateway: MockCloudGateway, bdd_context: dict[str, Any]) -> None:
    """Verifies no duplicate records exist in the cloud gateway database."""
    expected = bdd_context["initial_count"]
    assert len(mock_gateway.ingested_telemetry) == expected
