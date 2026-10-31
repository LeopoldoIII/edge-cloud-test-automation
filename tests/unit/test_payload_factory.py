"""Unit tests for synthetic dataset generators and Pydantic validation schemas."""

import pytest
from pydantic import ValidationError

from src.generators.edge_file_generator import EdgeFileGenerator
from src.generators.payload_factory import (
    EdgeTelemetryRecord,
    generate_medical_telemetry_batch,
    generate_telemetry_record,
)


@pytest.mark.unit
class TestPayloadFactory:
    """Test suite for edge payload models, schema validation, and chunking generators."""

    def test_valid_telemetry_generation(self) -> None:
        """Verifies generation of compliant EdgeTelemetryRecord."""
        record = generate_telemetry_record("edge-hw-101")
        assert record.device_id == "edge-hw-101"
        assert 0.0 <= record.battery_percentage <= 100.0
        assert -120 <= record.signal_strength_dbm <= 0

    def test_telemetry_validation_out_of_bounds(self) -> None:
        """Verifies Pydantic enforces valid ranges on telemetry values."""
        with pytest.raises(ValidationError):
            EdgeTelemetryRecord(
                device_id="edge-invalid",
                battery_percentage=150.0,  # Out of range (>100.0)
                cpu_temp_c=50.0,
                memory_usage_mb=512.0,
                signal_strength_dbm=-50,
            )

    def test_medical_telemetry_batch_anomaly_injection(self) -> None:
        """Verifies medical telemetry batch generation with anomalous readings."""
        batch = generate_medical_telemetry_batch(
            device_id="icu-monitor-02",
            reading_count=4,
            include_anomaly=True,
        )
        assert len(batch.readings) == 4
        assert any(r.flagged_anomaly for r in batch.readings)
        assert batch.metadata["hipaa_scrubbed"] is True

    def test_edge_file_chunking(self) -> None:
        """Verifies deterministic chunking of binary packages."""
        data = EdgeFileGenerator.create_binary_package(size_bytes=1000)
        chunks = EdgeFileGenerator.chunk_payload(file_id="pkg-001", data=data, chunk_size=300)

        assert len(chunks) == 4  # 300 + 300 + 300 + 100
        assert chunks[0].chunk_index == 0
        assert chunks[-1].is_last is True
        reassembled = b"".join(c.chunk_bytes for c in chunks)
        assert reassembled == data

    def test_mutate_corrupt_bytes(self) -> None:
        """Verifies byte mutation modifies the payload content."""
        original = b"A" * 100
        corrupted = EdgeFileGenerator.mutate_corrupt_bytes(original, mutation_rate=0.1)
        assert len(corrupted) == len(original)
        assert corrupted != original

    def test_create_binary_package_with_pattern(self) -> None:
        """Verifies binary package generation with repeating pattern."""
        pattern = b"XYZ123"
        pkg = EdgeFileGenerator.create_binary_package(size_bytes=20, pattern=pattern)
        assert len(pkg) == 20
        assert pkg.startswith(pattern)

    def test_generate_out_of_order_stream(self) -> None:
        """Verifies generation of shuffled chunk stream."""
        data = b"Stream content for out of order testing" * 20
        shuffled = EdgeFileGenerator.generate_out_of_order_stream(
            file_id="ord-1", data=data, chunk_size=50
        )
        assert len(shuffled) > 1

    def test_generate_partial_stream(self) -> None:
        """Verifies generation of truncated stream simulating premature drop."""
        data = b"Continuous telemetry buffer" * 30
        partial = EdgeFileGenerator.generate_partial_stream(
            file_id="part-1", data=data, chunk_size=50, drop_last_n=2
        )
        full_chunks = EdgeFileGenerator.chunk_payload(file_id="part-1", data=data, chunk_size=50)
        assert len(partial) == len(full_chunks) - 2
