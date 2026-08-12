"""Delivery Registry — Canonical Delivery Registry.

Delivery is a standalone FastAPI app that provides the Canonical Delivery Registry
per the Solution Design: Canonical Data Delivery Phase 1.

Delivery stores delivery metadata, lifecycle events, errors, and extended metadata
in a dedicated `delivery` schema in the existing dq-db PostgreSQL instance.

Delivery is separate from the DQ API but can be mounted as a sub-app for convenience.
"""
