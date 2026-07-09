# EDR-046 META: Docs Publishing Model — Keep Docusaurus Baked Into UI Container

**Status**: Accepted
**Date**: 2026-05-31
**Tag**: META
**Workstream**: WS-9 Documentation and Onboarding

## Context

WS9-A03 required an explicit decision on whether to keep or migrate the current documentation publishing model. The platform already has a working Docusaurus 3 site (`dq-ui/docs-site/`) that:

- Reads canonical source from `docs/` and `architecture/` directly (no separate authoring copy).
- Builds via `dq-ui/scripts/build-public-docs.sh`.
- Copies build output into `dq-ui/public/docs/` and is served by the nginx container at `/docs/`.
- Is public (no login required) and separate from authenticated application routes.
- Is versioned together with `dq-ui`.

The alternatives evaluated were:

| Option | Summary |
| --- | --- |
| A — Keep and formalise | Record the current model as the official decision; document what would trigger re-evaluation. Zero migration risk. |
| B — Decouple to external hosting | Separate CI job deploying to GitHub Pages, Netlify, Vercel, or a dedicated container. Canonical source unchanged. |
| C — Replace Docusaurus with MkDocs or VitePress | New static site generator. All sidebar config and `sidebars-utils.js` logic must be rewritten. |
| D — Plain Markdown / no-build | Drop the static site generator entirely. Loses navigation, search, and portal UX. |

## Decision

Keep the current Docusaurus model (Option A). The existing model is well-designed, stable, and zero-migration-risk. It is formalised here as the accepted approach.

One improvement is added alongside this decision: the docs build step (`build-public-docs.sh`) should be triggerable independently of a full UI image build in CI. This removes the main practical concern with the current model (docs-only changes requiring a full UI rebuild) without requiring a migration.

## Rationale

- Canonical source (`docs/` + `architecture/`) is already cleanly separated from rendered output. The right ownership boundary is already in place.
- Docusaurus provides full-text search, a structured sidebar, versioned release sections, and dark/light theme without additional tooling.
- The build pipeline is a single script with a known validation path.
- Migrating to external hosting (Option B) adds an independent deployment target and DNS/TLS management with no new user-facing capability.
- Replacing the static site generator (Option C) carries high migration cost (all sidebar config, custom components, and `sidebars-utils.js` must be rewritten) for no functional gain.
- Dropping the build (Option D) loses the portal UX that users already have access to.

## Scope Boundaries

This decision covers:
- How the public documentation portal is built and served.
- Which static site generator is used.
- Where canonical source lives.

This decision does not cover:
- Content governance (see `docs/technical/DOCUMENTATION_OWNERSHIP_AND_SOURCE_OF_TRUTH.md`).
- Whether individual doc families are public or restricted.
- CI pipeline specifics for the docs build step (tracked separately as an improvement item).

## Consequences

**Positive**
- No migration effort; existing docs portal continues working immediately.
- Canonical source stays in `docs/` and `architecture/` — no split authoring trees to maintain.
- The improvement item (independent docs build step) can be delivered incrementally without blocking this decision.

**Negative**
- Docs publish remains coupled to the UI container image until the independent build step is wired into CI.
- Future re-evaluation is needed if the platform moves to a fully external public portal or if the Docusaurus major version upgrade cost becomes prohibitive.

## Implementation Guidance

- Do not hand-edit files under `dq-ui/docs-site/docs/` directly; all source changes belong in `docs/` or `architecture/`.
- Run `bash dq-ui/scripts/build-public-docs.sh` to regenerate the portal locally before verifying docs changes.
- The docs build step should be extracted to a standalone CI job (e.g. triggered on changes to `docs/**` or `architecture/**`) so a docs-only commit does not require a full UI image build.
- Re-evaluate this decision if: (a) the platform needs a publicly hosted URL that is stable independently of any deployed container, or (b) Docusaurus major-version migration cost exceeds three days of effort.

## Related Artifacts

- [Public Documentation Portal Rollout and Operator Notes](../technical/DQ_PUBLIC_DOCUMENTATION_PORTAL_ROLLOUT_AND_OPERATOR_NOTES.md)
- [Documentation Ownership and Source-Of-Truth Policy](../technical/DOCUMENTATION_OWNERSHIP_AND_SOURCE_OF_TRUTH.md)
- [dq-ui docs-site](../../dq-ui/docs-site/docusaurus.config.js)
- [build-public-docs.sh](../../dq-ui/scripts/build-public-docs.sh)
- `WS9-A03` in [FEATURE_ROADMAP_OVERVIEW.md](../features/roadmap/FEATURE_ROADMAP_OVERVIEW.md)
