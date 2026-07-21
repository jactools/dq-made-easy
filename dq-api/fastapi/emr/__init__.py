"""EMR (Enterprise Metadata Repository) — Canonical Delivery Registry.

EMR is a standalone FastAPI app that provides the Canonical Delivery Registry
per the Solution Design: Canonical Data Delivery Phase 1.

EMR stores delivery metadata, lifecycle events, errors, and extended metadata
in a dedicated `emr` schema in the existing dq-db PostgreSQL instance.

EMR is separate from the DQ API but can be mounted as a sub-app for convenience.
"""
