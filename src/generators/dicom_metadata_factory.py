"""Synthetic DICOM and clinical imaging metadata factory."""

import uuid
from pydantic import BaseModel, Field


class DicomMetadataRecord(BaseModel):
    """Represents standard clinical DICOM header metadata tags for medical imaging."""

    study_instance_uid: str = Field(
        default_factory=lambda: f"1.2.840.10008.1.{uuid.uuid4().int % 1000000}"
    )
    series_instance_uid: str = Field(
        default_factory=lambda: f"1.2.840.10008.2.{uuid.uuid4().int % 1000000}"
    )
    sop_instance_uid: str = Field(
        default_factory=lambda: f"1.2.840.10008.3.{uuid.uuid4().int % 1000000}"
    )
    modality: str = "CT"  # CT, MR, XA, US
    body_part_examined: str = "CHEST"
    rows: int = 512
    columns: int = 512
    pixel_spacing: list[float] = Field(default_factory=lambda: [0.75, 0.75])
    slice_thickness_mm: float = 1.25

    # Protected Health Information (PHI) fields
    patient_name: str | None = None
    patient_id: str | None = None
    patient_birth_date: str | None = None
    institution_name: str | None = None
    accession_number: str | None = None
    phi_deidentified: bool = False


def generate_raw_clinical_dicom(
    patient_name: str = "DOE^JOHN",
    patient_id: str = "MRN-90210-X",
    modality: str = "MR",
) -> DicomMetadataRecord:
    """Generates synthetic DICOM metadata containing unscrubbed clinical PHI tags."""
    return DicomMetadataRecord(
        modality=modality,
        body_part_examined="BRAIN",
        patient_name=patient_name,
        patient_id=patient_id,
        patient_birth_date="19800512",
        institution_name="METROPOLITAN GENERAL HOSPITAL",
        accession_number="ACC-2026-9901",
        phi_deidentified=False,
    )
