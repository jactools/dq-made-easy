# dq-rules-ui

This subtree is unsupported legacy material kept for repository archaeology only.

Current repository guidance:
- The supported frontend is `dq-ui`.
- The supported API and data-catalog model are defined by the FastAPI stack, current `dq-db` sources, and accepted EDRs.
- Files under this subtree, including `db/init`, `dist`, `server`, and older mock data, are not canonical sources for current schema, API, or entity-model claims.
- Legacy object-level `attributeIds` data found here is historical only and must not be used to describe the active data model.
- References to `dq-rules-ui` elsewhere in the repository often refer to the Keycloak client ID, not this legacy subtree.

Do not update this subtree during normal feature work unless the task is explicitly about legacy archaeology, retirement, or removal.