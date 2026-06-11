# Documentation Features

Goal: Turn the current documentation set into a maintainable product surface with clear audience boundaries, current operational guidance, complete user workflow coverage, and an explicit platform decision for long-term publishing.

Current overlap assessment as of 2026-05-25:

- The repo already ships a public Docusaurus documentation portal at `/docs`, built from the authored `docs/` and `architecture/` trees and published through the frontend container.
- Technical documentation already exists in multiple forms: root guides such as `TECHNICAL.md`, rollout notes under `docs/technical/`, architecture and ADR content, release notes, and setup or deployment guides.
- User documentation already has an authored `docs/user-manuals/` tree, a public User Manuals landing page, and at least one current task-focused guide for the metadata-only data observability triage flow.
- Documentation navigation already exists in multiple places, including `DOCUMENTATION_GUIDE.md`, `docs/README.md`, the public portal structure, and in-app release notes.
- The current gap is not lack of documentation infrastructure; it is fragmented ownership, uneven freshness, mixed entry points, and incomplete coverage of core user and operator workflows.
- There is no evidence yet of a completed TechDocs or WikiJS evaluation, so that work should compare against the current Docusaurus baseline instead of assuming a blank-slate docs platform choice.

What still remains is the documentation operating model: one clear audience map, explicit source-of-truth rules, freshness or review expectations, fuller user and operator workflow coverage, and a platform decision based on real publishing gaps rather than generic tooling interest.

## Phase 1: Documentation Architecture and Governance

- Define canonical audiences and entry points: operators, developers, platform maintainers, and end users.
- Define source-of-truth boundaries for root docs, public portal pages, architecture docs, feature plans, rollout notes, and user manuals.
- Add documentation ownership and review cadence for high-change areas such as auth, deployment, startup, and observability.
- Define release-time documentation expectations so version bumps and feature delivery update the right authored surfaces together.

## Phase 2: Technical Documentation Refresh

- Replace stale or mixed technical entry points with a current technical navigation model aligned to the public portal.
- Consolidate operator guidance for startup, deployment, auth, ingress, observability, and recovery into discoverable runbooks and rollout notes.
- Add coverage mapping for setup guides, architectural references, contracts, validation scripts, and troubleshooting paths.
- Reduce duplicate or contradictory technical narratives by pointing readers to canonical documents instead of parallel summaries.

## Phase 3: User Documentation Expansion

- Build a task-based manual set for the main user journeys: login and workspace access, rule authoring, approvals, monitoring, triage, profiling, testing, and support escalation.
- Add role-aware guidance so admin, analyst, approver, and read-only users can find the right flows without reading implementation-heavy docs.
- Add terminology and quick-reference material where the product introduces domain-specific concepts.
- Ensure user guidance is linked consistently from the public docs portal and in-app discovery surfaces.

## Phase 4: Publishing Platform Decision

- Evaluate whether the current Docusaurus-based public portal already satisfies authoring, navigation, search, public access, and maintenance needs.
- Compare TechDocs and WikiJS only against the concrete gaps that remain after the architecture and coverage cleanup.
- Assess migration cost, repo-native authoring fit, auth or public-access model, versioning support, ownership workflow, and CI automation.
- Make an explicit keep-or-migrate decision with a bounded migration plan if another platform provides material benefit.

## Acceptance Criteria

- Every primary audience has a clear documentation entry point and a maintained path to the content they need.
- High-change technical surfaces have canonical runbooks or operator notes instead of scattered overlapping guides.
- Core user workflows are covered by task-focused manuals, not just release notes or feature plans.
- The public documentation portal remains the canonical published surface unless a replacement is explicitly chosen.
- Any platform change is justified by documented gaps, migration cost, and operating-model impact.

## Tracked Work Items (Current Status)

- [~] `DOC-1` Improve technical documentation
	- Existing overlap: the repo already has `TECHNICAL.md`, a public docs portal, technical rollout notes, architecture docs, ADRs, deployment guides, and setup guides.
	- Remaining: align stale root entry points with the current `0.11.0` documentation surface, define canonical technical navigation, close duplication across technical docs, and add explicit ownership and freshness expectations for high-change operational topics.
- [~] `DOC-2` Improve user documentation
	- Existing overlap: the `docs/user-manuals/` tree exists, the public User Manuals landing page is wired, in-app release notes exist, and the data observability triage guide is already published.
	- Remaining: expand the user-manual set to the main product workflows, add role-aware and terminology guidance, and make user-facing docs easier to discover than release-note archaeology.
- [~] `DOC-3` Investigate TechDocs and WikiJS
	- Existing overlap: the current Docusaurus portal gives a working baseline for authored repo-native docs, public access, and docs publishing.
	- Remaining: compare TechDocs and WikiJS against real unmet needs such as ownership workflow, search, metadata, versioning, and maintainability; do not treat a platform migration as work by default.

## Already Covered Elsewhere

- Public documentation publishing through the Docusaurus `/docs` portal.
- Authored technical notes, rollout guides, architecture docs, and ADR content.
- Initial user-manual infrastructure and at least one current end-user guide.
- Multiple navigation surfaces that can be consolidated instead of rebuilt.

## Remaining Platform Gap

The missing scope is not "write more docs" in general. The missing scope is a disciplined documentation model that decides which authored surface owns which audience and workflow, keeps those surfaces current as the product changes, and only revisits the publishing platform if the current Docusaurus baseline cannot support that model.
