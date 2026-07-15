"""Classification constants for SEC-3 synthetic/test bucket and evidence boundaries.

Defines the canonical bucket prefixes and prohibited terms used by the classification
validation module. These constants derive directly from the bucket and prefix naming
conventions document.

Related:
    - [Bucket and Prefix Naming Conventions](../../docs/technical/object-storage-classification/BUCKET_PREFIX_NAMING_CONVENTIONS.md)
"""

from __future__ import annotations

# Bucket prefixes that identify a bucket as synthetic/test storage.
SYNTHETIC_TEST_BUCKET_PREFIXES: tuple[str, ...] = (
    "dq-test-data",
    "dq-landing-zone",
    "dq-preview",
    "dq-demo",
)

# Bucket prefixes that identify a bucket as real/evidence storage.
REAL_EVIDENCE_BUCKET_PREFIXES: tuple[str, ...] = (
    "dq-evidence",
    "dq-reporting",
    "dq-source",
    "dq-delivery",
)

# Key prefix terms prohibited in synthetic/test buckets.
SYNTHETIC_TEST_PROHIBITED_PREFIX_TERMS: tuple[str, ...] = (
    "evidence",
    "reporting",
    "regulatory",
    "compliance",
    "production",
    "operational",
)

# Key prefix terms prohibited in real/evidence buckets.
REAL_EVIDENCE_PROHIBITED_PREFIX_TERMS: tuple[str, ...] = (
    "test",
    "synthetic",
    "preview",
    "demo",
    "mock",
    "fixture",
)
