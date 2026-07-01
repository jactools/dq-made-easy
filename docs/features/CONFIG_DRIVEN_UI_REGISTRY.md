# Config-Driven UI Registry

Goal: support a true config-driven registry for UI styles and component bundles so the frontend can discover theme names, stylesheet sources, and component adapters from configuration instead of a closed set hard-coded in source.

Current overlap assessment as of 2026-07-01:

- The app already has a selectable style-package layer and a theme preference layer.
- The current style and component selection surfaces are backed by fixed source code lists, not a manifest-driven registry.
- The missing scope is not a theme switcher or a simple settings toggle; the missing scope is a registry contract that can be supplied externally and resolved at runtime.
- The registry contract and loader belong with the API service layer, while custom theme upload/configuration belongs in dq-ui plus API endpoints, not dq-engine.
- This track is about portability and controlled configuration, not runtime user selection between arbitrary design systems without an adapter boundary.

## Phase 1: Define the Registry Contract

- Define the registry payload for styles and component bundles, including IDs, labels, source references, adapters, and fallback behavior.
- Decide which sources are allowed for the registry itself, such as ignored local files, environment-injected URLs, or deployment-provided manifests.
- Define how the app validates, normalizes, and caches the registry before it reaches UI code.
- Keep the registry loader in dq-api so the frontend consumes API-backed configuration rather than engine-owned helpers.
- [x] Define the registry schema and versioning rules.
- [x] Define allowed registry source types and precedence.
- [x] Add API-side loading and normalization entrypoints.
- [x] Add cache and fallback behavior for missing or invalid registries.

## Phase 2: Preserve Unknown Registry Entries

- Replace closed-set style and component unions with registry-backed descriptors where unknown IDs survive round-tripping.
- Keep safe fallback entries for startup and recovery, but do not silently collapse new registry values to defaults.
- Make persistence and normalization treat the registry as data, not as a hard-coded enum.
- [ ] Replace closed-set enums with registry-backed descriptors.
- [ ] Preserve unknown IDs through load and save.
- [ ] Add safe startup and recovery fallbacks.
- [ ] Ensure normalization does not collapse new values to defaults.

## Phase 3: Generalize the Style Loader Boundary

- Refactor the style theme provider so it resolves stylesheet URLs from registry entries instead of fixed package mappings.
- Support arbitrary external stylesheet sources and clean up injected links when the active registry entry changes.
- Keep the default baseline styles intact while allowing registry-driven overlays or replacements.
- [ ] Resolve stylesheet URLs from registry entries.
- [ ] Support arbitrary external stylesheet sources.
- [ ] Remove injected stylesheet links when entries change.
- [ ] Preserve baseline styles while allowing overlays or replacements.

## Phase 4: Make Settings and UI Registry-Driven

- Replace fixed package option lists and labels in application settings with registry-provided data.
- Persist only registry identifiers and the minimum required runtime metadata.
- Surface registry content in the UI without hard-coding package names or bundle choices in components.
- [ ] Replace fixed settings option lists with registry data.
- [ ] Persist only registry identifiers and required metadata.
- [ ] Render registry-provided content in the UI.
- [ ] Remove hard-coded package and bundle names from settings components.

## Phase 5: Generalize Component Bundle Resolution

- Introduce a registry-backed adapter layer for component bundles such as icon providers and other bundle-scoped UI surfaces.
- Resolve bundle selection through registry entries instead of binary source code switches.
- Keep app-owned primitives as the stable surface while allowing the underlying implementation to vary by registry entry.
- [ ] Add a registry-backed adapter layer for component bundles.
- [ ] Resolve bundle selection through registry entries.
- [ ] Keep app-owned primitives stable across bundle changes.
- [ ] Add adapter fallback behavior for missing bundle implementations.

## Phase 6: Move Build-Time Asset Handling Behind the Registry

- Refactor style-package build scripts and generated asset assumptions so emitted CSS outputs and vendor-specific transforms are described by registry entries.
- Keep build outputs aligned with the manifest until the pipeline can consume the registry directly.
- Remove fixed package-name assumptions only after the registry owns those references.
- [ ] Describe generated CSS outputs in the registry.
- [ ] Align build outputs with the manifest.
- [ ] Remove fixed package-name assumptions from build scripts.
- [ ] Add any required build-time manifest transforms.

## Phase 7: Add Guardrails and Verification

- Add tests that prove unknown registry entries round-trip through load, normalize, and save flows.
- Add tests that verify arbitrary stylesheet URLs are injected, updated, and removed correctly.
- Add tests that ensure registry-provided options render in the UI and that malformed registries fail safely.
- Add a contract check so registry entries cannot be added without a resolver, adapter, or fallback path.
- [ ] Add round-trip tests for unknown registry entries.
- [ ] Add stylesheet injection and cleanup tests.
- [ ] Add UI rendering tests for registry-provided options.
- [ ] Add contract checks for resolver, adapter, and fallback coverage.

## Phase 8: Document the External Configuration Workflow

- Document how the registry is supplied without committing its contents to git.
- Document how new style and component entries are added outside the repository.
- Document the fallback behavior when the registry cannot be loaded or validated.
- Document the API endpoints and UI upload flow that manage custom theme configuration.
- [ ] Document external registry delivery.
- [ ] Document the process for adding new registry entries.
- [ ] Document registry load and validation fallback behavior.
- [ ] Document the API and UI upload flow for custom themes.

## Acceptance Criteria

- The frontend can read a registry manifest from an external configuration source.
- Style and component selections no longer depend on closed source-code enums.
- Unknown registry entries survive persistence and round-tripping.
- Arbitrary stylesheet sources can be loaded and cleaned up correctly.
- Settings and UI render registry-provided options instead of fixed package lists.
- The implementation remains safe when the registry is missing or malformed.

## Tracked Work Items

- [x] `UI-REG-1` Registry contract and loader
- [x] `UI-REG-2` Registry-backed persistence and normalization
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
