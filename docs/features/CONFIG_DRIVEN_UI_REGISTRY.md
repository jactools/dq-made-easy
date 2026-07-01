# Config-Driven UI Registry

Goal: support a true config-driven registry for UI styles and component bundles so the frontend can discover theme names, stylesheet sources, and component adapters from configuration instead of a closed set hard-coded in source.

Current overlap assessment as of 2026-07-01:

- The app already has a selectable style-package layer and a theme preference layer.
- The current style and component selection surfaces are backed by fixed source code lists, not a manifest-driven registry.
- The missing scope is not a theme switcher or a simple settings toggle; the missing scope is a registry contract that can be supplied externally and resolved at runtime.
- This track is about portability and controlled configuration, not runtime user selection between arbitrary design systems without an adapter boundary.

## Phase 1: Define the Registry Contract

- Define the registry payload for styles and component bundles, including IDs, labels, source references, adapters, and fallback behavior.
- Decide which sources are allowed for the registry itself, such as ignored local files, environment-injected URLs, or deployment-provided manifests.
- Define how the app validates, normalizes, and caches the registry before it reaches UI code.

## Phase 2: Preserve Unknown Registry Entries

- Replace closed-set style and component unions with registry-backed descriptors where unknown IDs survive round-tripping.
- Keep safe fallback entries for startup and recovery, but do not silently collapse new registry values to defaults.
- Make persistence and normalization treat the registry as data, not as a hard-coded enum.

## Phase 3: Generalize the Style Loader Boundary

- Refactor the style theme provider so it resolves stylesheet URLs from registry entries instead of fixed package mappings.
- Support arbitrary external stylesheet sources and clean up injected links when the active registry entry changes.
- Keep the default baseline styles intact while allowing registry-driven overlays or replacements.

## Phase 4: Make Settings and UI Registry-Driven

- Replace fixed package option lists and labels in application settings with registry-provided data.
- Persist only registry identifiers and the minimum required runtime metadata.
- Surface registry content in the UI without hard-coding package names or bundle choices in components.

## Phase 5: Generalize Component Bundle Resolution

- Introduce a registry-backed adapter layer for component bundles such as icon providers and other bundle-scoped UI surfaces.
- Resolve bundle selection through registry entries instead of binary source code switches.
- Keep app-owned primitives as the stable surface while allowing the underlying implementation to vary by registry entry.

## Phase 6: Move Build-Time Asset Handling Behind the Registry

- Refactor style-package build scripts and generated asset assumptions so emitted CSS outputs and vendor-specific transforms are described by registry entries.
- Keep build outputs aligned with the manifest until the pipeline can consume the registry directly.
- Remove fixed package-name assumptions only after the registry owns those references.

## Phase 7: Add Guardrails and Verification

- Add tests that prove unknown registry entries round-trip through load, normalize, and save flows.
- Add tests that verify arbitrary stylesheet URLs are injected, updated, and removed correctly.
- Add tests that ensure registry-provided options render in the UI and that malformed registries fail safely.
- Add a contract check so registry entries cannot be added without a resolver, adapter, or fallback path.

## Phase 8: Document the External Configuration Workflow

- Document how the registry is supplied without committing its contents to git.
- Document how new style and component entries are added outside the repository.
- Document the fallback behavior when the registry cannot be loaded or validated.

## Acceptance Criteria

- The frontend can read a registry manifest from an external configuration source.
- Style and component selections no longer depend on closed source-code enums.
- Unknown registry entries survive persistence and round-tripping.
- Arbitrary stylesheet sources can be loaded and cleaned up correctly.
- Settings and UI render registry-provided options instead of fixed package lists.
- The implementation remains safe when the registry is missing or malformed.

## Tracked Work Items

- [ ] `UI-REG-1` Registry contract and loader
- [ ] `UI-REG-2` Registry-backed persistence and normalization
- [ ] `UI-REG-3` Registry-driven style loader
- [ ] `UI-REG-4` Registry-driven settings UI
- [ ] `UI-REG-5` Registry-backed component adapters
- [ ] `UI-REG-6` Build pipeline registry integration
- [ ] `UI-REG-7` Guardrails and verification
- [ ] `UI-REG-8` Documentation and workflow guidance

## Non-goals

- Do not introduce a new end-user theme picker that switches between arbitrary UI libraries without an adapter boundary.
- Do not commit protected registry contents to git.
- Do not preserve the current closed-set enum model once the registry path is in place.
- Do not rewrite the entire styling system in one pass.

## Remaining Platform Gap

The missing scope is a stable configuration registry that can supply UI styles and component bundles externally while still preserving app-owned primitives, safe fallbacks, and a bounded adapter layer.
