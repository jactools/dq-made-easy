# EDR-037 [API]: Validation Policy Legacy JSON and Config-Versioning Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: API

## Context
Application configuration now has to read both modern JSON-serialized policy data and older legacy rows stored as Python repr strings. The repository needs a stable compatibility rule so old data remains readable without preserving bad write behavior.

## Decision
- App-config deserialization must infer expected value type from the config key rather than trusting persisted `value_type` metadata blindly.
- Complex config payloads must be parsed as JSON first and only fall back to safe literal evaluation for legacy rows.
- New writes of structured validation-policy data must always use JSON serialization and must not create new repr-string rows.
- Compatibility handling must live in repository read/write behavior, not in manual data patching or retroactive metadata rewrites.
- Tests must cover both legacy and modern storage formats for the same logical config key.

## Rationale
- Historical config rows are heterogeneous enough that persisted type metadata is not always trustworthy.
- JSON is the repository's forward format, but legacy reads still need to work.
- Safe fallback parsing preserves compatibility without normalizing new bad writes.

## Scope Boundaries
This decision covers legacy compatibility and versioning behavior for validation-policy app config.

It does not by itself define:
- the policy schema itself
- broader app-config caching rules
- feature-flag configuration behavior

## Consequences
**Positive**
- Legacy config rows remain readable without reintroducing repr writes.
- Repository behavior stays deterministic for known config keys.

**Negative**
- Repository code must preserve dual-format read coverage.
- Config bugs can still surface if key-to-type inference drifts.

## Implementation Guidance
- Infer type from config key consistently.
- Parse JSON first, then use safe literal evaluation only for legacy compatibility.
- Serialize all new structured writes as JSON.
- Keep tests for both storage formats.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-app-config-validation-policies-legacy-json-note.md`