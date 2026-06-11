# ADR-017: Canonical API JSON field naming — snake_case

Status: Accepted

Context
-------
- The frontend and backend have historically used mixed-case JSON field names, causing user-visible bugs (e.g., admin features not appearing when API returns mixed-case keys).
- The repository policy prefers snake_case for public API JSON fields and camelCase for internal JavaScript usage.

Decision
--------
We will adopt snake_case as the canonical naming for all public API JSON fields. Server responses (OpenAPI/JSON) will use snake_case aliases produced by Pydantic models. The frontend will convert between snake_case (wire) and camelCase (client) using a centralized converter.

Consequences
------------
- Pros:
  - Predictable, consistent API contract for external clients.
  - Single source of truth (Pydantic alias generator) reduces runtime conversions and edge-case bugs.
  - OpenAPI docs will reflect the canonical shape.
- Cons:
  - Migration requires updating many schema classes and adding tests to raise coverage.
  - Temporary CI friction due to coverage gating until additional tests are added.

Plan
----
1. Introduce a `SnakeModel` Pydantic base with an `alias_generator` producing snake_case aliases. (Completed)
2. Migrate all API response schemas to inherit `SnakeModel` (incremental batches). (In progress)
3. Remove outbound response conversion from the ASGI middleware and leave incoming request bodies untouched so routes and repositories enforce snake_case directly. (Completed)
4. Add focused unit tests per migrated schema to verify snake_case output; incrementally raise Python test coverage. (Ongoing)
5. Update OpenAPI generation and docs to ensure snake_case is visible to API consumers.
6. Communicate rollout plan and a temporary CI exception window if needed while coverage grows.

Alternatives Considered
---------------------
- Keep runtime middleware converting responses: rejected due to complexity and risk of double-conversion with Pydantic aliasing.
- Use a post-processing step in the router: rejected in favor of a simpler, schema-driven approach.

Notes
-----
- Frontend conversion utilities exist and are wired at the UI boundary; backend request bodies are not rewritten by middleware.
- Tests and CI gating require coordinated work; propose an incremental approach to migration and targeted tests to raise coverage.
