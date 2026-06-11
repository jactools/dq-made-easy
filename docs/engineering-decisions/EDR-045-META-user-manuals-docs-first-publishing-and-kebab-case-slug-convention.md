# EDR-045 [META]: User Manuals Docs-First Publishing and Kebab-Case Slug Convention

**Status**: Accepted
**Date**: 2026-05-03
**Tag**: META

## Context

The repository now has a static user-manuals system that starts in `docs/user-manuals/`, publishes generated HTML through the existing frontend hosting path, and exposes the manuals from the app's Documentation area.

Two durable questions needed a stable repository rule:

- where the source of truth for manuals should live
- how individual manuals should be named so published URLs stay predictable over time

The implementation already proved that the manuals can be published from Markdown source into static HTML without introducing a separate documentation service. The remaining task is to record the canonical convention so future cards, links, and validation all follow the same pattern.

## Decision

- Keep the authored manuals source of truth under `docs/user-manuals/` for now.
- Use one Markdown file per topic, named in lowercase kebab-case.
- Reserve `README.md` for index pages.
- Keep underscore-prefixed files only for authoring templates such as `_template.md` and `_reference-template.md`.
- Publish each source file to a stable static URL derived from the source slug, following `/user-manuals/&lt;slug&gt;.html`.
- Keep the manuals index in `docs/user-manuals/README.md` as the authored index, while the build continues to generate the public static copy under `dq-ui/public/user-manuals/`.
- Do not introduce a second authored documentation tree or move manuals source content into the public output directory.

## Rationale

- Lowercase kebab-case file names are predictable, readable, and safe across filesystems and URL paths.
- Source-file-derived slugs reduce future link churn and make newly added cards easy to reason about.
- Keeping the authored manuals in `docs/` preserves the repo as the source of truth while still allowing public static publishing.
- Reserving `README.md` for index pages avoids ambiguity between a topic card and a directory index.
- Keeping the published output generated from `docs/` avoids duplicated authored content and prevents the repository from drifting into two separate documentation systems.

## Scope Boundaries

This decision applies to:

- manuals source-file naming
- the canonical location of authored manuals content
- the shape of public manuals slugs
- the distinction between authored docs and generated public HTML

It does not by itself define:

- the exact visual styling of the published manuals pages
- the search implementation within the generated HTML shell
- the decision to keep or change the frontend hosting path in the future
- whether other docs areas should adopt the same slug convention

## Consequences

**Positive**
- Manuals links remain stable and easy to predict.
- Future manuals can be added without inventing new naming rules.
- The repository retains one authored source tree for manuals and one generated static output tree.

**Negative**
- The convention is stricter than ad hoc markdown naming and requires authors to follow kebab-case.
- If a topic later needs multiple pages, the repository will need an explicit folder-based variant for that topic.

## Implementation Guidance

- Name new topic cards like `business-term-drift.md` or `technical-attribute-reference.md`.
- Keep authoring templates underscore-prefixed and excluded from public publishing.
- Map source files directly to public slugs during the sync step so links remain deterministic.
- Keep the docs index in `docs/user-manuals/README.md` authoritative and let the build produce the public HTML copy.
- If a topic expands into multiple related pages, place it in a dedicated folder with a `README.md` index and document the exception explicitly.

## Related Artifacts

- `docs/implementation-details/USER_MANUALS_IMPLEMENTATION_PLAN.md`
- `docs/user-manuals/README.md`
- `docs/user-manuals/governance-terminology.md`
- `docs/user-manuals/_template.md`
- `docs/user-manuals/_reference-template.md`
- `dq-ui/scripts/sync-user-manuals.sh`
- `dq-ui/scripts/sync-user-manuals.py`
- `dq-ui/public/user-manuals/`
- `docs/engineering-decisions/EDR-001-META-engineering-decision-records-scope-and-usage.md`