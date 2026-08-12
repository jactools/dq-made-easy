# DQ Results Contract

This directory contains the versioned, runtime-neutral execution-result summary contract.

Contract structure:

- `v1/schema.json`: canonical machine-readable result-summary contract.
- `v1/example.json`: canonical example payload.
- `v1/example.yaml`: review-friendly rendering of the same example payload.

Use it for the result produced after a validation artifact has been executed. Each `rule_results` item identifies the rule or expectation, its outcome, threshold relation, and checked, failed, succeeded, and filtered-out record counts.

The [validation-artifact-envelope](../validation-artifact-envelope/README.md) remains the input artifact contract. It does not embed execution outcomes.