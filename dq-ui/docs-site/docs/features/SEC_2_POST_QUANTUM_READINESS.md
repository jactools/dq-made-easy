# SEC-2 Post-Quantum Cryptography Readiness

Goal: Prepare dq-made-easy for post-quantum cryptography by inventorying current cryptographic dependencies, defining migration boundaries, and delivering a phased readiness and implementation plan for transport, signatures, keys, and third-party integrations.

Related work: [SEC-1 Internal Service-to-Service TLS](/docs/features/SEC_1_INTERNAL_SERVICE_TLS/)
Related architecture: [ADR-028 Post-Quantum Cryptography Must Be Implemented by 2026-12-31](/docs/architecture/adr/ADR-028-post-quantum-cryptography-must-be-implemented-by-2026-12-31/)
Implementation plan: [SEC-2: Post-Quantum Cryptography Implementation Plan](/docs/implementation-details/SEC_2_POST_QUANTUM_IMPLEMENTATION_PLAN/)
Deviation register: [Architecture Deviations and Exceptions Register](/docs/architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS/)

This file defines the stable scope and acceptance contract for post-quantum readiness and implementation planning. It is intentionally focused on controlled, standards-aligned adoption rather than claiming immediate blanket PQC replacement across every dependency on day one.

Note: The lists below use stable IDs so tasks and acceptance criteria can be referenced unambiguously across architecture, implementation, validation, and release planning.

## Phase 1: Cryptography Inventory and Risk Mapping

- [ ] (SEC2-F-P1-01) Inventory all cryptographic surfaces used by the platform, including TLS, JWT signing, password hashing, certificates, key storage, database/client drivers, and third-party integrations.
- [ ] (SEC2-F-P1-02) Classify each cryptographic surface as transport, signing, hashing, encryption-at-rest, secret-management, or external-dependency managed.
- [ ] (SEC2-F-P1-03) Identify which crypto dependencies are repository-controlled versus inherited from external platforms such as browsers, Keycloak, Kong, OpenMetadata, Postgres, Redis, and cloud services.
- [ ] (SEC2-F-P1-04) Document candidate post-quantum migration paths and standards dependencies for each critical surface.
- [ ] (SEC2-F-P1-05) Mark unsupported or blocked surfaces explicitly instead of assuming future vendor support.

## Phase 2: Architecture and Compatibility Strategy

- [ ] (SEC2-F-P2-01) Define the repository policy for when hybrid classical plus post-quantum cryptography is preferred over PQ-only approaches.
- [ ] (SEC2-F-P2-02) Define which trust boundaries can adopt post-quantum transport first without breaking browser, proxy, or vendor compatibility.
- [ ] (SEC2-F-P2-03) Define how certificate, key, and signature lifecycle management would change under a post-quantum or hybrid model.
- [ ] (SEC2-F-P2-04) Define compatibility expectations for user-facing clients, internal services, CI pipelines, and local developer environments.
- [ ] (SEC2-F-P2-05) Keep all post-quantum adoption decisions tied to explicit standards and supported library/runtime versions.

## Phase 3: Controlled Adoption Surfaces

- [ ] (SEC2-F-P3-01) Identify one or more internal transport paths that are safe candidates for hybrid TLS experiments.
- [ ] (SEC2-F-P3-02) Define how JWT or service-token signing surfaces are evaluated for post-quantum or hybrid signature readiness.
- [ ] (SEC2-F-P3-03) Define how repository-managed certificates and trust bundles would support future hybrid or post-quantum algorithms.
- [ ] (SEC2-F-P3-04) Define validation requirements for cryptographic negotiation, fallback behavior, and interoperability failures.
- [ ] (SEC2-F-P3-05) Ensure any experimental post-quantum adoption remains explicitly scoped and does not silently weaken current production-safe cryptography.

## Phase 4: Governance, Validation, and Rollout Controls

- [ ] (SEC2-F-P4-01) Add a maintained compatibility matrix covering runtimes, proxies, libraries, and infrastructure components relevant to post-quantum adoption.
- [ ] (SEC2-F-P4-02) Add validation guidance or tooling that can detect unsupported algorithms, expired assumptions, or downgraded crypto paths in planned migration areas.
- [ ] (SEC2-F-P4-03) Define rollback and feature-flag expectations for any future experimental or staged post-quantum rollout.
- [ ] (SEC2-F-P4-04) Document operator guidance for crypto capability verification and failure diagnosis.
- [ ] (SEC2-F-P4-05) Keep the roadmap current as standards, library support, and vendor support evolve.

## Acceptance Criteria

- [ ] (SEC2-F-AC-01) The repository has a named inventory of critical cryptographic surfaces and ownership boundaries.
- [ ] (SEC2-F-AC-02) The repository has an explicit policy for where post-quantum readiness is planned, deferred, blocked, or vendor-dependent.
- [ ] (SEC2-F-AC-03) Any future post-quantum experimentation is defined as explicit, reversible, and compatibility-checked rather than implied platform behavior.
- [ ] (SEC2-F-AC-04) Transport-security planning and certificate-management planning account for future hybrid or post-quantum migration needs.
- [ ] (SEC2-F-AC-05) Validation and operational guidance exist for at least one planned post-quantum or hybrid adoption path.

## Delivery Milestones

- Milestone A (Inventory): `SEC2-F-P1-01` to `SEC2-F-P1-05`
- Milestone B (Architecture): `SEC2-F-P2-01` to `SEC2-F-P2-05`
- Milestone C (Adoption Surfaces): `SEC2-F-P3-01` to `SEC2-F-P3-05`
- Milestone D (Governance): `SEC2-F-P4-01` to `SEC2-F-P4-05`