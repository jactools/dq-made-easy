# Documentation Hub

This folder is the canonical authored entry point for project documentation.

The public docs pipeline assembles the Docusaurus site from this tree together with the sibling [architecture](../architecture/README.md) tree, so the authored sources stay here while the site uses generated output under `dq-ui/docs-site/docs/`.

## Sections

- [status](status/README.md): Current status and roadmap documents.
- [releases](releases/README.md): Release notes and release planning documents.
- [technical](technical/README.md): Technical references, guides, and architecture-adjacent docs.
- [engineering-decisions](engineering-decisions/README.md): Repository-scoped Engineering Decision Records (EDRs).
- [contracts](contracts/README.md): Versioned API and artifact contracts.
- [ards](ards/README.md): Architecture records and decision links.
- [features](features/README.md): Feature overviews and feature-specific plans.
- [test-proof](test-proof/index.md): Human-readable proof pages generated from git-backed proof JSON.
- [implementation-details](implementation-details/README.md): Deep implementation notes, test and phase summaries.
- [user-manuals](user-manuals/README.md): Topic-focused reference cards for terminology, FAQ, and lookup items.
- [architecture](../architecture/README.md): Cross-cutting architecture decisions and deviations consumed by the same public docs site.

## Notes

- Keep authored docs in this tree or the sibling `architecture/` tree.
- The public docs build copies both trees into the site-local docs tree at build time.

