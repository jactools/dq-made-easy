# 0.11.4 Changelog

This changelog summarizes the user-visible and documentation-focused changes shipped in the 0.11.4 release line.

## Summary

- Aligned the UI and docs-site release markers to 0.11.4.
- Refreshed the public documentation portal content and release pointers.
- Added proof-oriented documentation for the Spark Expectations execution path.
- Published guidance for triggering DQ validation runs from pipeline orchestration.
- Cleaned up broken documentation links so the docs build stays healthy.

## Documentation and release alignment

- Updated the version markers for the Documentation component in the repository release manifest.
- Refreshed release notes and release indexes so the 0.11.4 line is discoverable from the public docs tree.
- Kept the API version marker at 0.11.0 because this release is focused on docs, validation evidence, and release-surface alignment rather than a new API runtime version.

## Validation evidence and proof docs

- Added human-readable proof pages for the Spark Expectations dispatch path and the real AIStor-backed validation run.
- Linked the proof pages from the test-proof index for easier inspection.
- Documented the multi-runtime lowerer and Spark Expectations implementation plans under the implementation-details and feature documentation trees.

## Operator and developer guidance

- Added a DQ CLI pipeline integration guide that explains how to trigger run plans from Databricks, Kubernetes, and Azure Container Apps-style workflows.
- Clarified where operators can find release notes, proof artifacts, and implementation details.
- Expanded the feature documentation set so users can follow the rollout story from roadmap to execution evidence.

## Notes

- This release is primarily a documentation, release-surface, and verification-evidence release.
- The current validation and proof content should be reviewed alongside the implementation notes when validating new runtime paths.
