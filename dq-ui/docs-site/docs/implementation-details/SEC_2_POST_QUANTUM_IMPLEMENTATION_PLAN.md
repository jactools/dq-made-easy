# SEC-2: Post-Quantum Cryptography Implementation Plan

**Status**: Proposed  
**Target**: Repository post-quantum and hybrid cryptography baseline by 2026-12-31  
**Date**: 2026-04-22

---

## Overview

SEC-2 turns the repository post-quantum mandate into an executable delivery plan.

The objective is not to replace every cryptographic dependency instantly with a PQ-only equivalent. The objective is to reach a repository security baseline by 2026-12-31 in which:

- repository-managed cryptographic surfaces use approved post-quantum or hybrid controls where supported,
- repository-configured transport and trust paths no longer default to classical-only operation where approved migration paths exist,
- vendor-blocked surfaces are recorded explicitly with owners, compensating controls, and removal plans.

This plan is tied directly to [ADR-028 Post-Quantum Cryptography Must Be Implemented by 2026-12-31](/docs/architecture/adr/ADR-028-post-quantum-cryptography-must-be-implemented-by-2026-12-31/).

## Scope Definition

### In Scope

- Transport cryptography used by repository-managed or repository-configured services.
- Certificate, trust-bundle, and key-management surfaces that the repository controls directly.
- JWT, service-token, or other signing surfaces that are configured or constrained by repository behavior.
- Compatibility analysis for Kong, Keycloak, FastAPI, workers, OpenMetadata, Postgres, Redis, AIStor, telemetry collectors, CI tooling, and local development environments.
- Validation, governance, and exception tracking required to support the deadline.

### Out of Scope for the First Cut

- Claiming full production support on vendor-managed surfaces that do not yet publish supported PQ or hybrid paths.
- Blind algorithm swaps without interoperability validation.
- Any silent fallback from approved post-quantum or hybrid paths to weaker defaults.

## Workstream 1: Inventory and Ownership Mapping

- [ ] (SEC2-I-W1-01) Build the complete repository cryptographic inventory across transport, certificates, signing, hashing, encryption-at-rest touchpoints, and secret exchange surfaces.
- [ ] (SEC2-I-W1-02) Classify each surface by ownership model: repository-managed, repository-configured, vendor-managed, or external-platform managed.
- [ ] (SEC2-I-W1-03) Record current algorithm and protocol assumptions per surface, including known classical-only constraints.
- [ ] (SEC2-I-W1-04) Identify which surfaces are already touched by SEC-1 internal TLS work and should share implementation sequencing.
- [ ] (SEC2-I-W1-05) Publish the initial inventory baseline by 2026-06-30.

## Workstream 2: Policy and Target-State Design

- [ ] (SEC2-I-W2-01) Define the repository-approved hybrid-first policy for surfaces where compatibility requires classical plus PQ coexistence.
- [ ] (SEC2-I-W2-02) Define which surfaces are expected to reach hybrid support by the deadline and which are expected to remain under exception management.
- [ ] (SEC2-I-W2-03) Define target certificate, trust, handshake, and signature patterns for repository-managed surfaces.
- [ ] (SEC2-I-W2-04) Define validation requirements for algorithm negotiation, trust-chain verification, and downgrade detection.
- [ ] (SEC2-I-W2-05) Publish the approved target-state matrix by 2026-09-30.

## Workstream 3: Repository-Managed Transport and Trust Execution

- [ ] (SEC2-I-W3-01) Align SEC-1 internal TLS work with post-quantum or hybrid transport requirements where supported by the chosen runtime and proxy stack.
- [ ] (SEC2-I-W3-02) Update certificate-generation and trust-distribution tooling to support future hybrid or PQ-capable certificate and trust models where feasible.
- [ ] (SEC2-I-W3-03) Define and implement the first repository-managed secure transport path that meets the approved hybrid or PQ target pattern.
- [ ] (SEC2-I-W3-04) Add fail-fast checks so migrated surfaces do not silently negotiate back to an unapproved baseline.
- [ ] (SEC2-I-W3-05) Capture runtime, proxy, and library compatibility evidence for each migrated path.

## Workstream 4: Vendor and Dependency Exception Management

- [ ] (SEC2-I-W4-01) Create and maintain the authoritative architecture deviation and exception register entries for blocked or deferred SEC-2 surfaces.
- [ ] (SEC2-I-W4-02) For every blocked surface, record owner, blocking dependency, compensating control, review cadence, and removal target.
- [ ] (SEC2-I-W4-03) Reject unnamed or ownerless exceptions.
- [ ] (SEC2-I-W4-04) Review the exception register on a fixed cadence through 2026 and close resolved entries promptly.
- [ ] (SEC2-I-W4-05) Keep the register aligned with the ADR-028 deadline so exceptions remain bounded rather than indefinite.

## Workstream 5: Validation, Evidence, and Release Controls

- [ ] (SEC2-I-W5-01) Add validation or audit scripts that can detect classical-only defaults on migrated or in-scope surfaces.
- [ ] (SEC2-I-W5-02) Add evidence capture requirements for supported runtimes, proxies, libraries, and negotiated crypto behavior.
- [ ] (SEC2-I-W5-03) Add release-readiness checks for SEC-2 milestone completion and exception register review status.
- [ ] (SEC2-I-W5-04) Add operator guidance for diagnosing negotiation failures, unsupported algorithms, or downgraded handshake paths.
- [ ] (SEC2-I-W5-05) Publish a final implementation readiness assessment before 2026-12-31.

## Timeline Gates

- [ ] (SEC2-I-G-01) By 2026-06-30, complete the cryptographic inventory and ownership map.
- [ ] (SEC2-I-G-02) By 2026-09-30, approve the target-state hybrid/PQ architecture and compatibility matrix.
- [ ] (SEC2-I-G-03) By 2026-11-30, complete implementation and validation for repository-managed in-scope surfaces or record explicit exceptions.
- [ ] (SEC2-I-G-04) By 2026-12-31, achieve the ADR-028 security baseline with only named, approved exceptions remaining.

## Acceptance Criteria

- [ ] (SEC2-I-AC-01) The repository has a maintained cryptographic inventory with ownership classification and target-state mapping.
- [ ] (SEC2-I-AC-02) The repository has an approved hybrid/PQ target policy for in-scope surfaces.
- [ ] (SEC2-I-AC-03) At least one repository-managed transport path is implemented and validated against the approved target model.
- [ ] (SEC2-I-AC-04) Every blocked surface is tracked in the exception register with owner, compensating control, and removal plan.
- [ ] (SEC2-I-AC-05) Validation and release controls can detect drift between the approved SEC-2 baseline and actual repository defaults.
- [ ] (SEC2-I-AC-06) The repository can demonstrate compliance with ADR-028 by 2026-12-31 or identify only explicit approved exceptions.

## Related Documents

- [SEC-2 Post-Quantum Cryptography Readiness](/docs/features/SEC_2_POST_QUANTUM_READINESS/)
- [ADR-028 Post-Quantum Cryptography Must Be Implemented by 2026-12-31](/docs/architecture/adr/ADR-028-post-quantum-cryptography-must-be-implemented-by-2026-12-31/)
- [ADR-027 Internal Service Communication Uses Repository-Managed TLS](/docs/architecture/adr/ADR-027-internal-service-communication-uses-repository-managed-tls/)
- [Architecture Deviations and Exceptions Register](/docs/architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS/)