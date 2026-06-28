# SEC-4 Controlled Container Egress and Approved External Destinations

Goal: enforce deny-by-default public internet egress for repository-managed containers and permit outbound internet traffic only to the approved external destination set for `jaccloud.nl` and `jacloud.nl`, using a real enforcement plane rather than relying on Docker Compose alone.

Related architecture: [ADR-032 Container Egress Deny-by-Default and Approved-Destination Enforcement](/docs/architecture/adr/ADR-032-container-egress-deny-by-default-and-approved-destination-enforcement/)

Related engineering decision: [EDR-044 Container Egress Enforcement and Environment-Specific Claims](/docs/engineering-decisions/EDR-044-INF-container-egress-enforcement-and-environment-specific-claims/)

Implementation plan: [SEC-4 Container Egress Control Implementation Plan](/docs/implementation-details/SEC_4_CONTAINER_EGRESS_CONTROL_IMPLEMENTATION_PLAN/)

This file defines the stable scope and acceptance contract for the security feature. Progress tracking and implementation sequencing live in the implementation-plan document.

Note: The lists below use stable IDs so tasks and acceptance criteria can be referenced unambiguously across engineering work, validation scripts, and release notes.

## Phase 1: Policy Boundary and Current-State Inventory

- [ ] (SEC4-F-P1-01) Define the exact boundary between internal Docker traffic, host-local integration traffic, and public internet egress for supported stack profiles.
- [ ] (SEC4-F-P1-02) Define the approved external destination set for `jaccloud.nl` and `jacloud.nl`, including any required FQDN-level documentation beneath those zones.
- [ ] (SEC4-F-P1-03) Inventory current container-startup and runtime flows that attempt direct public internet access.
- [ ] (SEC4-F-P1-04) Identify every public URL, host alias, runtime downloader, or bootstrap path that would violate deny-by-default egress.
- [ ] (SEC4-F-P1-05) Record environment-specific enforcement limits, especially the difference between Linux-hosted stacks and macOS Docker Desktop.

## Phase 2: Exposure Reduction Inside the Repository

- [ ] (SEC4-F-P2-01) Remove live third-party runtime downloads from container entrypoints, one-shot services, and startup flows where practical.
- [ ] (SEC4-F-P2-02) Convert eligible service networks and startup paths so containers do not require direct public internet reachability for normal operation.
- [ ] (SEC4-F-P2-03) Minimize host aliases, special DNS mappings, and direct host-gateway paths that bypass clear network intent.
- [ ] (SEC4-F-P2-04) Keep internal service discovery on repository-managed Docker names and explicit local trust roots rather than public internet names where possible.
- [ ] (SEC4-F-P2-05) Ensure blocked or missing outbound paths fail fast instead of silently downgrading to alternate public destinations.

## Phase 3: Enforcement Plane Rollout

- [ ] (SEC4-F-P3-01) Select and document the authoritative enforcement layer for supported environments, such as a Linux firewall, a Docker-VM firewall, or a DNS-aware outbound proxy backed by network deny rules.
- [ ] (SEC4-F-P3-02) Ensure containers cannot bypass the chosen enforcement layer to reach the public internet directly.
- [ ] (SEC4-F-P3-03) Route any approved public egress through the enforcement layer with explicit allowlisting for `jaccloud.nl` and `jacloud.nl`.
- [ ] (SEC4-F-P3-04) Treat macOS Docker Desktop as a distinct enforcement case and document how local policy is applied or where strong enforcement is not claimed.
- [ ] (SEC4-F-P3-05) Track any temporary non-compliant outbound dependencies as explicit deviations with owners and closure dates.

## Phase 4: Validation, Evidence, and Operations

- [x] (SEC4-F-P4-01) Add validation tooling that flags known direct-internet startup paths, public third-party URLs, and obvious egress-policy bypasses in repository-managed stack definitions.
- [ ] (SEC4-F-P4-02) Add smoke checks that verify allowed outbound access to approved destinations and denied access to an unapproved destination.
- [ ] (SEC4-F-P4-03) Add operator runbooks for policy updates, destination allowlist changes, DNS-related debugging, and blocked-egress diagnosis.
- [ ] (SEC4-F-P4-04) Make egress-policy violations visible through logs, validation scripts, or observability surfaces.
- [ ] (SEC4-F-P4-05) Document which environments are enforcement-capable, validation-only, or explicitly out of scope.

## Acceptance Criteria

- [ ] (SEC4-F-AC-01) Supported enforcement-capable environments deny direct public internet egress from containers by default.
- [ ] (SEC4-F-AC-02) The only approved public internet destination set is the documented `jaccloud.nl` and `jacloud.nl` allowlist.
- [ ] (SEC4-F-AC-03) Normal stack startup does not require unmanaged third-party runtime downloads from containers.
- [ ] (SEC4-F-AC-04) Containers fail clearly when they attempt blocked outbound internet access instead of silently using a fallback route.
- [ ] (SEC4-F-AC-05) Validation tooling can demonstrate at least one blocked unapproved destination and one allowed approved destination.
- [ ] (SEC4-F-AC-06) Operators have a documented enforcement and debugging workflow for Linux-hosted and macOS-local development cases.

## Delivery Milestones

- Milestone A (Inventory and Gap Register): `SEC4-F-P1-01` to `SEC4-F-P1-05`
- Milestone B (Repository Hardening): `SEC4-F-P2-01` to `SEC4-F-P2-05`
- Milestone C (Enforcement Plane): `SEC4-F-P3-01` to `SEC4-F-P3-05`
- Milestone D (Validation and Operations): `SEC4-F-P4-01` to `SEC4-F-P4-05`