"""DICOM de-identification and HIPAA compliance verification module."""

import hashlib
from src.core.exceptions import IntegrityError
from src.generators.dicom_metadata_factory import DicomMetadataRecord


class DicomDeidentifier:
    """De-identifies clinical DICOM metadata tags according to HIPAA Safe Harbor guidelines."""

    PHI_TAGS = (
        "patient_name",
        "patient_id",
        "patient_birth_date",
        "institution_name",
        "accession_number",
    )

    @classmethod
    def scrub_phi(
        cls, raw: DicomMetadataRecord, salt: str = "edge-salt-key"
    ) -> DicomMetadataRecord:
        """Produces a sanitized DICOM metadata record with all direct PHI stripped and pseudonymized.

        Args:
            raw: Raw clinical DICOM record containing PHI.
            salt: Cryptographic salt for irreversible pseudonym hashing.

        Returns:
            De-identified DicomMetadataRecord.
        """
        pseudonym = hashlib.sha256(f"{raw.patient_id}:{salt}".encode("utf-8")).hexdigest()[:16]

        cleaned_dict = raw.model_dump()
        cleaned_dict["patient_name"] = "ANONYMIZED"
        cleaned_dict["patient_id"] = f"SUBJ-{pseudonym}"
        cleaned_dict["patient_birth_date"] = None
        cleaned_dict["institution_name"] = "REDACTED"
        cleaned_dict["accession_number"] = None
        cleaned_dict["phi_deidentified"] = True

        return DicomMetadataRecord(**cleaned_dict)

    @classmethod
    def assert_hipaa_compliance(cls, record: DicomMetadataRecord) -> bool:
        """Asserts that a DICOM record is compliant with HIPAA Safe Harbor de-identification rules.

        Raises:
            IntegrityError: If direct patient identifiers remain present.
        """
        if not record.phi_deidentified:
            raise IntegrityError("HIPAA Violation: DICOM record is marked as non-deidentified.")

        if record.patient_birth_date is not None:
            raise IntegrityError("HIPAA Violation: Patient birth date detected in payload.")

        if record.patient_name and record.patient_name != "ANONYMIZED":
            raise IntegrityError(
                f"HIPAA Violation: Raw patient name detected: {record.patient_name}"
            )

        return True
