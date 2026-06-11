# ADR-032: Container Egress Deny-by-Default and Approved-Destination Enforcement

**Status**: Accepted  
**Date**: 2026-04-23  
**Related**: [ADR-026](./ADR-026-shell-scripts-must-run-on-macos-and-debian-linux.md), [ADR-027](./ADR-027-internal-service-communication-uses-repository-managed-tls.md), [ADR-029](./ADR-029-eu-financial-c3-security-baseline-mandate.md), [ADR-030](./ADR-030-eu-financial-regulatory-baseline-and-control-mapping.md), [SEC-4 Controlled Container Egress and Approved External Destinations](../../docs/features/SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md)

## Context

dq-rulebuilder currently runs its Docker services on ordinary bridge networks defined in repository-managed Compose files.

That layout supports service-to-service communication, but it does not provide a repository-level outbound access-control plane. In the current setup:

- containers are not attached to an `internal: true` network by default,
- Compose does not define deny-by-default outbound internet rules,
- some services still carry host aliases or public URL configuration that can reach beyond the Docker network,
- at least one one-shot container currently performs a live third-party artifact download at runtime.

The repository now has a stricter security objective: containers must not initiate internet traffic except to the approved external destination set associated with `jaccloud.nl` and `jacloud.nl`.

That requirement cannot be enforced reliably by Docker Compose alone. Compose can reduce exposure by changing network topology, removing runtime downloads, and centralizing proxy configuration, but it cannot express or guarantee a hostname allowlist for outbound internet traffic.

This limitation is even more important on macOS with Docker Desktop, where container networking runs inside Docker Desktop's Linux VM rather than directly on the host network stack. Strong outbound enforcement therefore requires a firewall-capable or DNS-aware egress control plane outside ordinary Compose declarations.

## Decision

Adopt a repository security rule that container-originated public internet egress is deny-by-default and may be permitted only to the approved external destination set for `jaccloud.nl` and `jacloud.nl`, with enforcement performed by a dedicated egress control plane rather than by Compose alone.

For this ADR:

1. Public internet egress from repository-managed containers MUST be treated as denied by default.
2. The only approved public internet destination set is the `jaccloud.nl` and `jacloud.nl` domain space, including explicitly documented FQDNs beneath those zones when required by a supported deployment profile.
3. Internal Docker-network service traffic, loopback probes, and explicitly documented host-local integration paths are not considered public internet egress, but they MUST still be documented and minimized.
4. Enforcement MUST be performed by a firewall-capable or DNS-aware egress control plane such as:
   - a host or VM firewall with deny-by-default outbound rules and an approved-destination allowlist, or
   - an explicit outbound proxy or egress gateway backed by network rules that block direct bypass traffic.
5. Docker Compose, env defaults, and entrypoints MAY provide supporting controls, but they are not an authoritative enforcement layer for approved-destination internet policy.
6. Runtime container downloads from third-party public endpoints MUST be removed from the steady-state startup path or routed through the approved egress control plane and tracked as explicit transitional exceptions.
7. Fail-fast behavior applies: if a blocked destination is required by mistake, the affected flow MUST fail clearly instead of silently retrying through an unapproved fallback route.
8. macOS Docker Desktop local development MUST be treated as a special-case environment where enforcement cannot be claimed from Compose alone; strong enforcement must live in the Docker VM, a Linux-hosted environment, or a controlled outbound proxy path.
9. Any temporary need for container-originated internet access outside the approved destination set MUST be recorded in the architecture deviation register with owner, rationale, review date, and closure target.

## Consequences

### Positive

- The repository gains a clear security boundary for outbound internet traffic instead of relying on informal developer discipline.
- Egress-sensitive controls required for regulated financial-sector deployments become explicit and auditable.
- Runtime behavior becomes more predictable because hidden third-party dependencies are surfaced and removed.
- The platform can distinguish between internal service communication hardening and true public internet egress control.

### Negative

- Additional engineering work is required to remove live internet downloads and other unapproved dependencies.
- Local development on macOS becomes more operationally complex if strong enforcement must be demonstrated locally.
- A pure Compose-only local stack is no longer sufficient evidence for egress-policy compliance.
- Domain-based allowlisting introduces operational work around DNS resolution, destination drift, and validation evidence.

## Implementation Notes

- Treat Compose changes as exposure reduction and routing support, not final enforcement.
- Prefer a design where containers do not need direct public internet access at all; pre-bake or vendor runtime artifacts where practical.
- If domain-level allowlisting is required, prefer a DNS-aware proxy or gateway layer over a brittle static IP-only rule set.
- Validation should prove both directions:
  - approved destinations are reachable when policy allows them, and
  - unapproved destinations fail clearly.
- Known current gaps, such as runtime artifact fetches from third-party public endpoints, should be removed first or tracked explicitly as deviations until eliminated.