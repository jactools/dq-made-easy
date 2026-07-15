from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.domain.services import classification_validation as validation


# ---------------------------------------------------------------------------
# Bucket classification
# ---------------------------------------------------------------------------


def test_classify_bucket_name_synthetic() -> None:
    assert validation.classify_bucket_name("dq-test-data") == "synthetic_test"
    assert validation.classify_bucket_name("dq-landing-zone-workspace1") == "synthetic_test"
    assert validation.classify_bucket_name("dq-preview-finance") == "synthetic_test"
    assert validation.classify_bucket_name("dq-demo-onboarding") == "synthetic_test"


def test_classify_bucket_name_evidence() -> None:
    assert validation.classify_bucket_name("dq-evidence-default") == "real_evidence"
    assert validation.classify_bucket_name("dq-reporting-bcbs239") == "real_evidence"
    assert validation.classify_bucket_name("dq-source-teller-machine") == "real_evidence"
    assert validation.classify_bucket_name("dq-delivery-finance") == "real_evidence"


def test_classify_bucket_name_unclassified() -> None:
    assert validation.classify_bucket_name("dq-gx-exceptions") == "unclassified"
    assert validation.classify_bucket_name("random-bucket") == "unclassified"
    assert validation.classify_bucket_name("") == "unclassified"


# ---------------------------------------------------------------------------
# URI classification
# ---------------------------------------------------------------------------


def test_classify_uri_synthetic() -> None:
    classification, bucket, key = validation.classify_uri("s3a://dq-test-data/data_object_version_id=abc123")
    assert classification == "synthetic_test"
    assert bucket == "dq-test-data"
    assert key == "data_object_version_id=abc123"


def test_classify_uri_evidence() -> None:
    classification, bucket, key = validation.classify_uri("s3a://dq-evidence-default/gx-exceptions/run123")
    assert classification == "real_evidence"
    assert bucket == "dq-evidence-default"
    assert key == "gx-exceptions/run123"


def test_classify_uri_unparseable() -> None:
    classification, bucket, key = validation.classify_uri("file:///tmp/data")
    assert classification == "unclassified"
    assert bucket is None
    assert key == ""


# ---------------------------------------------------------------------------
# Bucket naming validation
# ---------------------------------------------------------------------------


def test_validate_bucket_naming_synthetic_valid() -> None:
    assert validation.validate_bucket_naming(
        bucket="dq-test-data",
        key_prefix="data_object_version_id=abc",
    ) is None


def test_validate_bucket_naming_evidence_valid() -> None:
    assert validation.validate_bucket_naming(
        bucket="dq-evidence-default",
        key_prefix="gx-exceptions/run123",
    ) is None


def test_validate_bucket_naming_unclassified() -> None:
    violation = validation.validate_bucket_naming(bucket="dq-gx-exceptions")
    assert violation is not None
    assert "does not match any classification naming pattern" in violation


def test_validate_bucket_naming_synthetic_with_prohibited_terms() -> None:
    violation = validation.validate_bucket_naming(
        bucket="dq-test-data",
        key_prefix="evidence/reporting/output",
    )
    assert violation is not None
    assert "prohibited" in violation


def test_validate_bucket_naming_evidence_with_prohibited_terms() -> None:
    violation = validation.validate_bucket_naming(
        bucket="dq-evidence-default",
        key_prefix="test/synthetic/output",
    )
    assert violation is not None
    assert "prohibited" in violation


def test_validate_bucket_naming_expected_mismatch() -> None:
    violation = validation.validate_bucket_naming(
        bucket="dq-test-data",
        expected_classification="real_evidence",
    )
    assert violation is not None
    assert "synthetic_test" in violation
    assert "real_evidence" in violation


# ---------------------------------------------------------------------------
# Mixed classification guard
# ---------------------------------------------------------------------------


def test_ensure_no_mixed_classification_empty() -> None:
    validation.ensure_no_mixed_classification(delivery_notes=[])


def test_ensure_no_mixed_classification_uniform() -> None:
    notes = [
        {"object_storage_classification": "synthetic_test"},
        {"object_storage_classification": "synthetic_test"},
    ]
    validation.ensure_no_mixed_classification(delivery_notes=notes)


def test_ensure_no_mixed_classification_mixed_raises() -> None:
    notes = [
        {"object_storage_classification": "synthetic_test"},
        {"object_storage_classification": "real_evidence"},
    ]
    with pytest.raises(HTTPException) as excinfo:
        validation.ensure_no_mixed_classification(delivery_notes=notes)
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["error"] == "mixed_classification_artifacts"


def test_ensure_no_mixed_classification_synthetic_in_evidence_scope() -> None:
    notes = [
        {"object_storage_classification": "synthetic_test"},
        {"object_storage_classification": "synthetic_test"},
    ]
    with pytest.raises(HTTPException) as excinfo:
        validation.ensure_no_mixed_classification(
            delivery_notes=notes,
            consumer_scope="real_evidence",
        )
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["error"] == "synthetic_in_evidence_export"


# ---------------------------------------------------------------------------
# Storage target classification guard
# ---------------------------------------------------------------------------


def test_ensure_storage_target_matches() -> None:
    validation.ensure_storage_target_matches_classification(
        bucket="dq-test-data",
        expected_classification="synthetic_test",
    )


def test_ensure_storage_target_mismatch_raises() -> None:
    with pytest.raises(HTTPException) as excinfo:
        validation.ensure_storage_target_matches_classification(
            bucket="dq-evidence-default",
            expected_classification="synthetic_test",
            context="test-data materialization",
        )
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["error"] == "storage_target_classification_mismatch"
    assert excinfo.value.detail["context"] == "test-data materialization"
    assert excinfo.value.detail["actual_classification"] == "real_evidence"
    assert excinfo.value.detail["expected_classification"] == "synthetic_test"
