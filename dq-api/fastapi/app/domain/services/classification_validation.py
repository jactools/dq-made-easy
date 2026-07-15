"""Classification validation utilities for SEC-3 synthetic/test bucket and evidence boundaries.

Provides naming convention checks, classification derivation, and fail-fast guards
that enforce the boundary between synthetic/test and real/evidence storage.

Related:
    - [SEC-3 Feature](../../docs/features/SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES.md)
    - [Bucket and Prefix Naming Conventions](../../docs/technical/object-storage-classification/BUCKET_PREFIX_NAMING_CONVENTIONS.md)
    - [SEC-3 Implementation Plan](../../docs/implementation-details/SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES_IMPLEMENTATION_PLAN.md)
"""

from __future__ import annotations

import re

from fastapi import HTTPException

from app.domain.services import classification_constants as constants

__all__ = [
    "classify_bucket_name",
    "classify_uri",
    "validate_bucket_naming",
    "ensure_no_mixed_classification",
    "ensure_storage_target_matches_classification",
]


def _normalize_bucket(bucket: str) -> str:
    return str(bucket or "").strip().lower()


def _classify_from_bucket(bucket: str) -> str:
    """Derive the storage classification from the bucket name.

    Returns "synthetic_test", "real_evidence", or "unclassified".
    """
    normalized = _normalize_bucket(bucket)
    for prefix in constants.SYNTHETIC_TEST_BUCKET_PREFIXES:
        if normalized.startswith(prefix):
            return "synthetic_test"
    for prefix in constants.REAL_EVIDENCE_BUCKET_PREFIXES:
        if normalized.startswith(prefix):
            return "real_evidence"
    return "unclassified"


def classify_bucket_name(bucket: str) -> str:
    """Classify a bucket name as synthetic_test, real_evidence, or unclassified."""
    return _classify_from_bucket(bucket)


def _parse_s3_uri(uri: str) -> tuple[str, str] | None:
    """Parse an s3:// or s3a:// URI into (bucket, key_prefix). Returns None if unparseable."""
    normalized = str(uri or "").strip()
    if normalized.startswith("s3a://"):
        remainder = normalized[6:]
    elif normalized.startswith("s3://"):
        remainder = normalized[5:]
    else:
        return None

    if not remainder:
        return None
    if "/" in remainder:
        bucket, key_prefix = remainder.split("/", 1)
        return bucket, key_prefix
    return remainder, ""


def classify_uri(uri: str) -> tuple[str, str | None, str]:
    """Classify an S3 URI.

    Returns (classification, bucket, key_prefix).
    classification is "synthetic_test", "real_evidence", or "unclassified".
    """
    parsed = _parse_s3_uri(uri)
    if parsed is None:
        return "unclassified", None, ""
    bucket, key_prefix = parsed
    return _classify_from_bucket(bucket), bucket, key_prefix


def _has_prohibited_synthetic_terms(key_prefix: str) -> list[str]:
    """Check if a key prefix uses terms prohibited in synthetic/test buckets."""
    normalized = str(key_prefix or "").lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", normalized) if token}
    return [term for term in constants.SYNTHETIC_TEST_PROHIBITED_PREFIX_TERMS if term in tokens]


def _has_prohibited_evidence_terms(key_prefix: str) -> list[str]:
    """Check if a key prefix uses terms prohibited in real/evidence buckets."""
    normalized = str(key_prefix or "").lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", normalized) if token}
    return [term for term in constants.REAL_EVIDENCE_PROHIBITED_PREFIX_TERMS if term in tokens]


def validate_bucket_naming(
    *,
    bucket: str,
    key_prefix: str = "",
    expected_classification: str | None = None,
    context: str | None = None,
) -> str | None:
    """Validate that a bucket/prefix follows the naming convention.

    Returns None if valid, or a violation description string.
    """
    classification = _classify_from_bucket(bucket)

    if classification == "unclassified":
        return f"bucket '{_normalize_bucket(bucket)}' does not match any classification naming pattern (synthetic_test or real_evidence)"

    if expected_classification and classification != expected_classification:
        return (
            f"bucket '{_normalize_bucket(bucket)}' is classified as '{classification}' "
            f"but expected '{expected_classification}'"
        )

    if classification == "synthetic_test":
        prohibited = _has_prohibited_synthetic_terms(key_prefix)
        if prohibited:
            return (
                f"synthetic/test bucket key prefix contains prohibited terms: {prohibited}"
            )
    elif classification == "real_evidence":
        prohibited = _has_prohibited_evidence_terms(key_prefix)
        if prohibited:
            return (
                f"real/evidence bucket key prefix contains prohibited terms: {prohibited}"
            )

    return None


def ensure_no_mixed_classification(
    *,
    delivery_notes: list[dict[str, object] | object],
    consumer_scope: str | None = None,
    status_code: int = 409,
) -> None:
    """Fail fast when evidence-pack or export contains mixed-classification artifacts.

    If consumer_scope is "real_evidence" and any delivery note has a synthetic
    classification, raise HTTPException. If classifications differ across notes,
    always raise.
    """
    if not delivery_notes:
        return

    classifications: set[str] = set()
    for note in delivery_notes:
        storage_class = _get_field(note, "object_storage_classification")
        evidence_class = _get_field(note, "evidence_classification")
        if storage_class:
            classifications.add(storage_class)
        if evidence_class:
            classifications.add(evidence_class)

    if len(classifications) > 1:
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": "mixed_classification_artifacts",
                "message": (
                    "Export contains artifacts with mixed storage classifications. "
                    "Synthetic/test and real/evidence artifacts must not be mixed "
                    "in the same export scope."
                ),
                "classifications_found": sorted(classifications),
                "consumer_scope": consumer_scope,
            },
        )

    if consumer_scope == "real_evidence":
        for classification in classifications:
            if classification == "synthetic_test" or classification == "synthetic_result":
                raise HTTPException(
                    status_code=status_code,
                    detail={
                        "error": "synthetic_in_evidence_export",
                        "message": (
                            "Export scope is limited to real/evidence artifacts but "
                            "synthetic/test artifacts are present."
                        ),
                        "classifications_found": sorted(classifications),
                        "consumer_scope": consumer_scope,
                    },
                )


def ensure_storage_target_matches_classification(
    *,
    bucket: str,
    expected_classification: str,
    context: str | None = None,
    status_code: int = 409,
) -> None:
    """Fail fast when a storage target bucket does not match the expected classification.

    Used to prevent synthetic test results from being persisted to real/evidence
    storage targets, and vice versa.
    """
    classification = _classify_from_bucket(bucket)

    if classification != expected_classification:
        detail: dict[str, object] = {
            "error": "storage_target_classification_mismatch",
            "message": (
                f"Storage target bucket '{_normalize_bucket(bucket)}' is classified "
                f"as '{classification}' but '{expected_classification}' was expected"
            ),
            "bucket": _normalize_bucket(bucket),
            "expected_classification": expected_classification,
            "actual_classification": classification,
        }
        if context:
            detail["context"] = context
        raise HTTPException(status_code=status_code, detail=detail)


def _get_field(obj: dict[str, object] | object, field: str) -> str | None:
    """Extract a field from a dict or object, returning stripped string or None."""
    if isinstance(obj, dict):
        raw = obj.get(field)
    else:
        raw = getattr(obj, field, None)
    if raw is None:
        return None
    stripped = str(raw).strip()
    return stripped if stripped else None
