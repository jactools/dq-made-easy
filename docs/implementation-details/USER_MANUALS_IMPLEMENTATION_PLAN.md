# User Manuals Implementation Plan

## Goal
Create a small, topic-focused user manuals system under `docs/user-manuals/`, publish it as static HTML through the existing frontend hosting model, and expose it from the app's documentation navigation.

## Roadmap-facing feature backlog

- Canonical feature backlog: [../features/DOCUMENTATION_FEATURES.md](../features/DOCUMENTATION_FEATURES.md)
- Canonical roadmap summary: [../features/FEATURE_ROADMAP_OVERVIEW.md](../features/FEATURE_ROADMAP_OVERVIEW.md)

## Scope
- Source of truth: one Markdown file per topic under `docs/user-manuals/`
- Published artifact: static HTML under the frontend public assets
- Navigation: entry point from the existing Documentation area in the UI, with a link to a manuals index page
- Hosting: existing nginx frontend, no separate docs service

## Content Model
Each reference card should stay small and predictable:
- title
- time to read
- last updated
- term
- explanation
- context
- faq
- terminology used
- related terms

## Repository Layout
- `docs/user-manuals/README.md` as the index for all cards
- `docs/user-manuals/_template.md` as the reusable starting point for new cards
- `docs/user-manuals/<topic>/README.md` or `docs/user-manuals/<topic>.md` for each card, depending on the final publishing convention
- `dq-ui/public/user-manuals/` as the published static output location
- `dq-ui/scripts/sync-user-manuals.sh` with `dq-ui/scripts/sync-user-manuals.py` for build-time publishing

## Implementation Checklist

### 1. Define the manuals structure
- [x] Confirm the final manuals path under `docs/user-manuals/`
- [x] Decide whether each card uses a folder-based clean URL or a flat file name
- [x] Create the manuals index file with links to all cards
- [x] Add a visible time-to-read field to each card
- [x] Add a visible last-updated field to each card
- [x] Create a second template for FAQ and terminology lookup cards
- [x] Document the authoring rules for non-procedural reference cards
- [x] Add a short note that the manuals are reference cards, not task guides

### 2. Establish the publishing pipeline
- [x] Choose the static publishing approach: Markdown source plus generated HTML output
- [x] Add a build-time sync/render script in `dq-ui/scripts/`
- [x] Make the script fail fast if the source manuals directory is missing
- [x] Ensure deleted source files do not remain in the published output
- [x] Wire the script into `dq-ui` `predev` and `prebuild` hooks
- [x] Confirm the Vite build copies the published static output into the final bundle

### 3. Add frontend navigation
- [x] Add a manuals entry in the Documentation UI
- [x] Link the entry to the published manuals index page
- [x] Keep the existing Documentation tabs intact
- [x] Make sure the manuals entry is discoverable from the sidebar Documentation area
- [x] Add a short in-app explanation that the manuals are reference cards for lookup and terminology

### 4. Publish through nginx
- [x] Verify the published manuals live under the frontend static root
- [x] Confirm nginx serves the manuals path with clean URLs
- [x] Confirm SPA routing still works for application routes
- [x] Confirm existing static docs routes remain unchanged
- [x] Add only the minimum routing needed for the manuals path, if any

### 5. Cross-link the docs tree
- [x] Add a link from `docs/README.md` or `docs/features/README.md` to the manuals index
- [x] Keep the docs hub and the app navigation pointing at the same published manuals entry point
- [x] Avoid duplicating manuals content in multiple repo locations

### 6. Quality and validation
- [x] Add or update validation coverage for the manuals publishing script
- [x] Confirm the manuals index resolves in the built frontend
- [x] Confirm a sample card opens correctly from the UI
- [x] Confirm a deleted card is removed from the published output on rebuild
- [x] Validate the touched markdown and script files for errors

## Acceptance Criteria
- [x] A user can reach the manuals index from the app's Documentation area
- [x] The manuals are served as static HTML through the existing frontend hosting model
- [x] Each card stays focused on one topic or lookup item
- [x] The repository keeps Markdown source under `docs/user-manuals/`
- [x] The build fails fast if the manuals source tree is missing or incomplete
- [x] The docs hub exposes the manuals without creating a second documentation system

## Delivery Order
- [x] Create the manuals index and a first sample card
- [x] Create the reusable manuals template
- [x] Create the reference template for FAQ and terminology cards
- [x] Add the sync/render script and wire it into the UI build
- [x] Add the UI navigation link
- [x] Publish the static output and verify nginx serving
- [x] Add docs hub cross-links
- [x] Add validation and regression coverage

## Open Decisions
- [x] Finalize the file naming convention for individual cards
- [x] Decide whether the manuals index should live only in `docs/` or also be mirrored into the static site

## Suggested Convention
- Use lowercase kebab-case for all user-manual source files, one topic per `.md` file.
- Keep underscore-prefixed files only for authoring templates such as `_template.md` and `_reference-template.md`.
- Use the source filename as the public slug, mapped into `/user-manuals/<slug>.html` for predictable linking and future additions.
- Keep `README.md` reserved for index pages only.
- If a topic ever needs multiple pages, place them in a dedicated folder with a `README.md` index, but keep the top-level slug pattern canonical for single-page cards.

## Notes
- This plan intentionally keeps backend contracts unchanged.
- The manuals system should stay static and repo-owned.
- The implementation should reuse the existing frontend static hosting path rather than introducing a new docs service.
