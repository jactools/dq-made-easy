# SEC-4 Container Egress Control Implementation Plan

**Status**: Proposed  
**Target**: deny-by-default public internet egress for repository-managed containers, with approved external destinations limited to `jaccloud.nl` and `jacloud.nl` and enforced by a real egress-control plane  
**Date**: 2026-04-23

Related engineering decision: [EDR-044 Container Egress Enforcement and Environment-Specific Claims](../engineering-decisions/EDR-044-INF-container-egress-enforcement-and-environment-specific-claims.md)

---

## Overview

SEC-4 introduces controlled outbound internet behavior for repository-managed containers.

The target state is not just a documentation rule. It is an enforceable network-control posture where:

- containers do not have broad public internet reachability by default,
- approved external destinations are restricted to the documented `jaccloud.nl` and `jacloud.nl` allowlist,
- direct bypass routes are blocked,
- and repository startup does not depend on ad hoc third-party runtime downloads.

The current stack cannot claim that posture through Compose alone. Compose can reduce exposure and centralize routing intent, but strong enforcement must live in a firewall-capable or DNS-aware egress-control layer. That distinction matters especially on macOS Docker Desktop, where container traffic runs through Docker Desktop's Linux VM rather than directly through the host network stack.

This plan therefore combines repository hardening with an explicit enforcement-plane rollout.

## Scope Definition

### In Scope

- Public internet egress initiated by long-running services, one-shot containers, and startup helpers defined by repository-managed Compose files.
- Compose, entrypoint, bootstrap, and validation changes needed to eliminate unmanaged direct-internet dependencies.
- Enforcement patterns for Linux-hosted stacks and for macOS Docker Desktop local development.
- Validation evidence proving that approved destinations are reachable and unapproved destinations are blocked.

### Out of Scope for the First Cut

- Docker image pulls performed by the Docker daemon before container startup.
- General workstation browsing controls outside repository-managed container execution.
- Non-repository environments that already provide an external network-policy platform and do not rely on repository Compose files for enforcement.

## Workstream 1: Policy Baseline and Dependency Inventory

- [ ] (SEC4-I-W1-01) Define the public internet egress boundary used by the repository, separating it from internal Docker traffic, loopback probes, and explicitly documented host-local integration paths.
- [ ] (SEC4-I-W1-02) Produce the initial approved external destination inventory for `jaccloud.nl` and `jacloud.nl`, including required FQDNs, ports, and rationale.
- [ ] (SEC4-I-W1-03) Inventory all current container-startup and runtime flows that attempt direct public internet access.
- [ ] (SEC4-I-W1-04) Identify all public third-party runtime dependencies that must be removed, proxied, or temporarily excepted.
- [ ] (SEC4-I-W1-05) Record the initial gap list and any temporary exceptions in the architecture deviation register instead of leaving them implicit.

## Workstream 2: Repository Exposure Reduction

- [ ] (SEC4-I-W2-01) Remove live third-party artifact downloads from entrypoints and one-shot services, including startup helpers that currently fetch binaries from public endpoints.
- [ ] (SEC4-I-W2-02) Move required third-party runtime artifacts into images, mounted seed artifacts, or repository-managed build steps that are outside the steady-state container startup path.
- [ ] (SEC4-I-W2-03) Review Compose service definitions for public URLs, direct host aliases, and special DNS mappings that are not required for the supported runtime path.
- [ ] (SEC4-I-W2-04) Convert eligible service attachments to more restrictive network patterns, including `internal: true` networks where that does not break required host exposure.
- [ ] (SEC4-I-W2-05) Ensure every blocked outbound dependency fails clearly and is surfaced as a configuration or runtime error instead of triggering a hidden alternative route.

## Workstream 3: Enforcement Architecture Selection

- [ ] (SEC4-I-W3-01) Select the authoritative enforcement design for Linux-hosted environments, such as a DOCKER-USER chain policy, nftables policy, or equivalent firewall-backed egress gateway.
- [ ] (SEC4-I-W3-02) Select the authoritative enforcement design for macOS Docker Desktop, recognizing that Compose-only controls are insufficient and that enforcement must live in the Docker VM, a companion Linux network appliance, or an explicit egress proxy backed by deny rules.
- [ ] (SEC4-I-W3-03) Decide whether the allowlist is enforced primarily through a DNS-aware proxy, a firewall rule set with synchronized destination IP material, or a hybrid of both.
- [ ] (SEC4-I-W3-04) Define the routing model for container outbound traffic, including how approved public egress differs from internal Docker service traffic.
- [ ] (SEC4-I-W3-05) Document the unsupported enforcement claims explicitly so environments that only have Compose hardening are not misrepresented as fully enforced.

## Workstream 4: Policy Implementation and Bypass Elimination

- [ ] (SEC4-I-W4-01) Implement deny-by-default outbound rules so containers cannot directly reach arbitrary public internet destinations.
- [ ] (SEC4-I-W4-02) Permit outbound access only to the documented `jaccloud.nl` and `jacloud.nl` destination set through the chosen enforcement layer.
- [ ] (SEC4-I-W4-03) Ensure internal Docker service traffic and explicitly documented host-local integration traffic remain functional without being mistaken for public-internet exceptions.
- [ ] (SEC4-I-W4-04) Configure proxy-related environment variables and `NO_PROXY` handling where an explicit outbound proxy is part of the design.
- [ ] (SEC4-I-W4-05) Eliminate or explicitly justify every known bypass path, including direct host-gateway routes, unmanaged DNS aliases, or public side downloads.

## Workstream 5: Validation, Observability, and Runbooks

- [x] (SEC4-I-W5-01) Add a validation script that flags obvious direct-internet startup paths, third-party download commands, and unreviewed public URLs in repository-managed stack definitions.
- [ ] (SEC4-I-W5-02) Add smoke coverage that proves at least one approved outbound request succeeds and at least one unapproved outbound request fails.
- [ ] (SEC4-I-W5-03) Add validation for environment drift, such as missing proxy envs, broken deny rules, or stale allowlist entries.
- [ ] (SEC4-I-W5-04) Add operator runbooks for approved-destination changes, blocked-egress debugging, and macOS-versus-Linux enforcement troubleshooting.
- [ ] (SEC4-I-W5-05) Add observability guidance so blocked outbound requests and policy violations are easy to detect and interpret.

## Recommended Sequencing

1. Finish Workstream 1 before asserting any egress-compliance claim.
2. Finish Workstream 2 before enabling hard deny rules in environments that still depend on third-party startup downloads.
3. Land Workstream 3 before broad rollout so Linux-hosted and macOS-local expectations are explicit.
4. Use Workstream 4 to implement the chosen control plane and remove bypasses.
5. Use Workstream 5 to convert the network policy into repeatable evidence instead of a one-time configuration exercise.

## Acceptance Criteria

- [ ] (SEC4-I-AC-01) Supported enforcement-capable environments deny direct public internet egress from containers by default.
- [ ] (SEC4-I-AC-02) The approved public internet allowlist is limited to documented `jaccloud.nl` and `jacloud.nl` destinations.
- [ ] (SEC4-I-AC-03) No supported steady-state container startup path depends on unmanaged third-party public downloads.
- [ ] (SEC4-I-AC-04) An unapproved outbound request fails clearly and predictably in validation coverage.
- [ ] (SEC4-I-AC-05) An approved outbound request succeeds through the chosen enforcement plane in validation coverage.
- [ ] (SEC4-I-AC-06) Linux-hosted and macOS-local runbooks explain where enforcement is authoritative and where a profile is validation-only.

## Known Current Gaps to Address Early

- The stack currently relies on ordinary bridge networking rather than an explicit egress-control plane.
- Some services still define host aliases or public URL configuration that should be reviewed as part of bypass elimination.

## Related Documents

- [SEC-4 Controlled Container Egress and Approved External Destinations](../features/SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md)
- [SEC_FEATURES.md](../features/SEC_FEATURES.md)
- [ADR-032 Container Egress Deny-by-Default and Approved-Destination Enforcement](../../architecture/adr/ADR-032-container-egress-deny-by-default-and-approved-destination-enforcement.md)
- [EDR-044 Container Egress Enforcement and Environment-Specific Claims](../engineering-decisions/EDR-044-INF-container-egress-enforcement-and-environment-specific-claims.md)
- [ADR-029 EU Financial C=3 Security Baseline Mandate](../../architecture/adr/ADR-029-eu-financial-c3-security-baseline-mandate.md)