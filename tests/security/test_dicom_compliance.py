"""Security and regulatory compliance test suite for clinical DICOM metadata and HIPAA de-identification."""

import pytest

from src.core.dicom_scrubber import DicomDeidentifier
from src.core.exceptions import IntegrityError
from src.generators.dicom_metadata_factory import generate_raw_clinical_dicom


@pytest.mark.security
class TestDicomCompliance:
    """Test suite ensuring clinical imaging metadata adheres to HIPAA Safe Harbor de-identification rules."""

    def test_dicom_phi_scrubbing_and_pseudonymization(self) -> None:
        """Verifies direct identifiers are stripped while clinical parameters are preserved."""
        raw_record = generate_raw_clinical_dicom(
            patient_name="SMITH^ALICE",
            patient_id="HOSP-123456",
            modality="CT",
        )
        assert raw_record.phi_deidentified is False
        assert raw_record.patient_name == "SMITH^ALICE"

        scrubbed = DicomDeidentifier.scrub_phi(raw_record)

        # PHI assertions
        assert scrubbed.phi_deidentified is True
        assert scrubbed.patient_name == "ANONYMIZED"
        assert scrubbed.patient_id is not None and scrubbed.patient_id.startswith("SUBJ-")
        assert scrubbed.patient_birth_date is None
        assert scrubbed.institution_name == "REDACTED"

        # Diagnostic geometry preserved
        assert scrubbed.modality == "CT"
        assert scrubbed.rows == 512
        assert scrubbed.columns == 512

        # HIPAA compliance check passes
        assert DicomDeidentifier.assert_hipaa_compliance(scrubbed) is True

    def test_unscrubbed_record_fails_hipaa_compliance_assertion(self) -> None:
        """Verifies attempting to transmit unscrubbed clinical DICOM triggers IntegrityError."""
        raw_record = generate_raw_clinical_dicom(patient_name="DOE^JOHN")

        with pytest.raises(IntegrityError, match="HIPAA Violation"):
            DicomDeidentifier.assert_hipaa_compliance(raw_record)

    def test_hipaa_violation_on_unscrubbed_birth_date_or_name(self) -> None:
        """Verifies IntegrityError if birth date or raw patient name is present in deidentified record."""
        record_with_birth_date = generate_raw_clinical_dicom()
        record_with_birth_date.phi_deidentified = True
        record_with_birth_date.patient_birth_date = "19900101"

        with pytest.raises(IntegrityError, match="Patient birth date detected"):
            DicomDeidentifier.assert_hipaa_compliance(record_with_birth_date)

        record_with_raw_name = generate_raw_clinical_dicom()
        record_with_raw_name.phi_deidentified = True
        record_with_raw_name.patient_birth_date = None
        record_with_raw_name.patient_name = "UNREDACTED^NAME"

        with pytest.raises(IntegrityError, match="Raw patient name detected"):
            DicomDeidentifier.assert_hipaa_compliance(record_with_raw_name)
