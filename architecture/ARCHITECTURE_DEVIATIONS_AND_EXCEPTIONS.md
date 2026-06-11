# Architecture Deviations and Exceptions Register

This register is the authoritative list of approved, time-bounded architecture deviations and exceptions in dq-rulebuilder.

Use this file when a repository surface cannot currently comply with an accepted ADR, architecture baseline, or cross-cutting platform rule and that non-compliance must be tracked explicitly instead of remaining implicit.

## Summary

| Metric | Count |
| --- | ---: |
| Active entries | 7 |
| Mitigated entries | 0 |
| Closed entries | 2 |

## Purpose

- Make architecture exceptions visible and reviewable.
- Prevent indefinite drift from accepted architecture decisions.
- Require named ownership, risk assessment, impact description, deadlines, and review cadence.
- Provide one shared register instead of scattered exception notes per feature.

## When to Add an Entry

Add an entry when all of the following are true:

1. An accepted architecture rule, ADR, or platform baseline exists.
2. The current repository behavior deviates from that baseline or cannot yet meet it.
3. The deviation is intentional, tolerated temporarily, or forced by a concrete blocker.
4. The deviation has non-trivial risk, impact, or deadline implications.

## Register Rules

- Every entry MUST use a unique identifier in the form `ARCH-EXC-XXXX`.
- Every entry MUST state the category.
- Every entry MUST state the current status.
- Every entry MUST name an owner.
- Every entry MUST describe risk and impact explicitly.
- Every entry MUST include a review date.
- Every entry MUST include a target closure date or explicitly state why none is possible.
- Every entry MUST reference the governing ADR, feature, implementation plan, or technical artifact it deviates from.
- Closed entries stay in the register for history; do not delete them.
- Ownerless, undated, or unreviewed exceptions are invalid.

## File Naming Convention

- Each deviation subpage MUST live under `architecture/deviations/`.
- Each filename MUST use the pattern `ARCH-EXC-XXXX-short-kebab-case-title.md`.
- The numeric identifier in the filename MUST match the identifier in the document title and register entry.
- Filenames SHOULD use concise kebab-case slugs derived from the deviation title.
- Do not rename an existing file unless the identifier is wrong or the title is materially misleading.
- If a deviation is closed, keep the same filename and move only its index entry to the closed section.

## Categories

- `security`
- `post-quantum`
- `transport`
- `platform-compatibility`
- `vendor-dependency`
- `operational`
- `data`
- `performance`
- `compliance`
- `other`

## Status Values

- `proposed`
- `approved`
- `mitigated`
- `closed`
- `rejected`

## Deviation Subpages

- [ARCH-EXC-0001: Internal Service Transport Still Defaults to Plaintext Links](./deviations/ARCH-EXC-0001-internal-service-transport-still-defaults-to-plaintext-links.md)
- [ARCH-EXC-0002: ADR-028 Post-Quantum Baseline Is Not Yet Implemented](./deviations/ARCH-EXC-0002-adr-028-post-quantum-baseline-is-not-yet-implemented.md)
- [ARCH-EXC-0003: Vendor-Managed OIDC and JWKS Surfaces Lack Repository-Validated PQ/Hybrid Path](./deviations/ARCH-EXC-0003-vendor-managed-oidc-and-jwks-surfaces-lack-repository-validated-pq-hybrid-path.md)
- [ARCH-EXC-0004: C=3 Deployments Still Allow Permissive Local Auth and Default Credentials](./deviations/ARCH-EXC-0004-c3-deployments-still-allow-permissive-local-auth-and-default-credentials.md)
- [ARCH-EXC-0005: C=3 Observability RBAC Is Documented but Not Yet Enforced](./deviations/ARCH-EXC-0005-c3-observability-rbac-is-documented-but-not-yet-enforced.md)
- [ARCH-EXC-0006: Repository-Wide Data Protection and Data Access Policy Is Not Yet Defined](./deviations/ARCH-EXC-0006-repository-wide-data-protection-and-data-access-policy-is-not-yet-defined.md)
- [ARCH-EXC-0007: CRR and EMIR Reporting Evidence Baseline Is Not Yet Defined](./deviations/ARCH-EXC-0007-crr-and-emir-reporting-evidence-baseline-is-not-yet-defined.md)
- [ARCH-EXC-0008: Synthetic/Test Object Storage Boundaries Are Not Yet Enforced](./deviations/ARCH-EXC-0008-synthetic-test-object-storage-boundaries-are-not-yet-enforced.md)
- [ARCH-EXC-0009: OpenMetadata Javaagent Runtime Download Still Requires Public GitHub Egress](./deviations/ARCH-EXC-0009-openmetadata-javaagent-runtime-download-still-requires-public-github-egress.md)

## Active Entries

- [ARCH-EXC-0001](./deviations/ARCH-EXC-0001-internal-service-transport-still-defaults-to-plaintext-links.md) — `approved`, `transport`, owner `Platform Engineering`, next review `2026-05-15`, target closure `2026-12-31`.
- [ARCH-EXC-0002](./deviations/ARCH-EXC-0002-adr-028-post-quantum-baseline-is-not-yet-implemented.md) — `approved`, `post-quantum`, owner `Platform Security`, next review `2026-05-15`, target closure `2026-12-31`.
- [ARCH-EXC-0003](./deviations/ARCH-EXC-0003-vendor-managed-oidc-and-jwks-surfaces-lack-repository-validated-pq-hybrid-path.md) — `approved`, `vendor-dependency`, owner `Platform Security`, next review `2026-05-31`, target closure `2026-11-30`.
- [ARCH-EXC-0004](./deviations/ARCH-EXC-0004-c3-deployments-still-allow-permissive-local-auth-and-default-credentials.md) — `approved`, `security`, owner `Platform Security`, next review `2026-05-15`, target closure `2026-09-30`.
- [ARCH-EXC-0005](./deviations/ARCH-EXC-0005-c3-observability-rbac-is-documented-but-not-yet-enforced.md) — `approved`, `compliance`, owner `ops-team-observability`, next review `2026-05-31`, target closure `2026-08-31`.
- [ARCH-EXC-0006](./deviations/ARCH-EXC-0006-repository-wide-data-protection-and-data-access-policy-is-not-yet-defined.md) — `approved`, `compliance`, owner `Data Governance`, next review `2026-05-31`, target closure `2026-09-30`.
- [ARCH-EXC-0008](./deviations/ARCH-EXC-0008-synthetic-test-object-storage-boundaries-are-not-yet-enforced.md) — `approved`, `data`, owner `Data Governance`, next review `2026-05-31`, target closure `2026-10-31`.

## Closed Entries

- [ARCH-EXC-0007](./deviations/ARCH-EXC-0007-crr-and-emir-reporting-evidence-baseline-is-not-yet-defined.md) — `closed`, `compliance`, owner `Data Governance`, closure date `2026-04-22`.
- [ARCH-EXC-0009](./deviations/ARCH-EXC-0009-openmetadata-javaagent-runtime-download-still-requires-public-github-egress.md) — `closed`, `vendor-dependency`, owner `Platform Engineering`, closure date `2026-04-23`.

When an entry is closed:

- keep the deviation subpage in `architecture/deviations/` for history,
- update the subpage status to `Closed`,
- move the summary line from `Active Entries` to `Closed Entries`,
- include the closure date in the summary line.

## Entry Template

### ARCH-EXC-XXXX: Short Deviation Title

- Status: `proposed` | `approved` | `mitigated` | `closed` | `rejected`
- Category: One of the register categories listed above
- Affected surface: Specific service, protocol, runtime path, infrastructure dependency, or policy surface
- Governing baseline: ADR, feature, implementation plan, or architecture rule being deviated from
- Owner: Team or named role
- First recorded: `YYYY-MM-DD`
- Last reviewed: `YYYY-MM-DD`
- Next review date: `YYYY-MM-DD`
- Target closure date: `YYYY-MM-DD` or `none - reason required`
- Risk level: `low` | `medium` | `high` | `critical`
- Impact level: `low` | `medium` | `high` | `critical`
- Summary: Short statement of the deviation or exception
- Rationale: Why the deviation currently exists
- Risk details: Concrete security, delivery, operational, compliance, or maintainability risks
- Impact details: What users, operators, systems, or deadlines are affected
- Compensating controls: What reduces risk while the deviation remains open
- Validation / evidence: Tests, docs, logs, vendor notes, issue links, or implementation references
- Exit criteria: What must happen to close the entry

## Example Entry Shape

Use the template section above for new entries. Keep future entries concrete and evidence-backed in the same style as the active entries.