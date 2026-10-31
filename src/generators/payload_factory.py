"""Pydantic-based synthetic edge telemetry and data model factories."""

import random
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class EdgeTelemetryRecord(BaseModel):
    """Represents a single hardware telemetry reading captured on a Linux edge device."""

    device_id: str
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    battery_percentage: float = Field(ge=0.0, le=100.0)
    cpu_temp_c: float
    memory_usage_mb: float
    signal_strength_dbm: int = Field(ge=-120, le=0)
    network_interface: str = "eth0"
    firmware_version: str = "2.4.1-rc3"


class SensorReading(BaseModel):
    """Represents a sensor measurement emitted by edge hardware."""

    sensor_id: str
    sensor_type: str
    measurement: float
    unit: str
    flagged_anomaly: bool = False


class MedicalTelemetryBatch(BaseModel):
    """Represents structured clinical/medical telemetry from an edge monitoring station."""

    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str
    station_identifier: str
    patient_pseudonym_hash: str
    modality: str  # e.g., "ECG", "SPO2", "HEM"
    readings: list[SensorReading]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


def generate_telemetry_record(device_id: str | None = None) -> EdgeTelemetryRecord:
    """Generates a realistic synthetic edge telemetry reading.

    Args:
        device_id: Optional device ID string.

    Returns:
        Populated EdgeTelemetryRecord.
    """
    return EdgeTelemetryRecord(
        device_id=device_id or f"edge-{uuid.uuid4().hex[:6]}",
        battery_percentage=round(random.uniform(15.0, 99.0), 1),
        cpu_temp_c=round(random.uniform(42.0, 78.5), 2),
        memory_usage_mb=round(random.uniform(256.0, 1850.0), 2),
        signal_strength_dbm=random.randint(-95, -45),
        network_interface=random.choice(["eth0", "wlan0", "wwan0"]),
        firmware_version="2.4.1",
    )


def generate_medical_telemetry_batch(
    device_id: str,
    reading_count: int = 5,
    include_anomaly: bool = False,
) -> MedicalTelemetryBatch:
    """Generates a medical edge telemetry batch conforming to healthcare compliance guidelines.

    Args:
        device_id: Unique edge station ID.
        reading_count: Number of consecutive sensor readings.
        include_anomaly: Whether to inject an out-of-spec measurement.

    Returns:
        MedicalTelemetryBatch instance.
    """
    readings: list[SensorReading] = []
    for i in range(reading_count):
        is_anomaly = include_anomaly and (i == reading_count - 1)
        heart_rate = random.uniform(140.0, 175.0) if is_anomaly else random.uniform(60.0, 95.0)
        readings.append(
            SensorReading(
                sensor_id=f"sensor-ecg-{i:02d}",
                sensor_type="heart_rate_bpm",
                measurement=round(heart_rate, 1),
                unit="bpm",
                flagged_anomaly=is_anomaly,
            )
        )

    return MedicalTelemetryBatch(
        device_id=device_id,
        station_identifier="ICU-BAY-04",
        patient_pseudonym_hash=uuid.uuid5(
            uuid.NAMESPACE_DNS, f"patient-{random.randint(100, 999)}"
        ).hex,
        modality="ECG",
        readings=readings,
        metadata={"hipaa_scrubbed": True, "compression": "zstd", "sample_rate_hz": 250},
    )
