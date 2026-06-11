# EDR-044 [INF]: Container Egress Enforcement and Environment-Specific Claims

**Status**: Accepted
**Date**: 2026-04-23
**Tag**: INF

## Context
SEC-4 introduces deny-by-default public internet egress for repository-managed containers, with approved outbound access restricted to `jaccloud.nl` and `jacloud.nl`.

The repository already established the architecture direction in ADR-032, but engineering still needs a durable repository-level rule for how that claim is made in practice across supported environments.

That distinction matters because the current stack uses ordinary Docker bridge networking, includes host-specific routing helpers, and still has at least one direct public runtime dependency. It also matters because Linux-hosted Docker environments and macOS Docker Desktop do not offer the same enforcement surface.

Without an explicit engineering rule, the repository risks overstating compliance by treating Compose hardening as if it were an authoritative outbound network-control layer.

## Decision
- Repository-managed containers may claim deny-by-default public internet egress only when outbound enforcement is backed by an authoritative control plane outside Docker Compose, such as Linux firewall rules, a Docker-VM firewall, a controlled egress gateway, or an outbound proxy backed by deny rules.
- Linux-hosted environments are the primary enforcement-capable target for SEC-4 and should use a firewall-capable control surface such as `DOCKER-USER`, `nftables`, or an equivalent gateway pattern.
- macOS Docker Desktop is a distinct enforcement case and must not be represented as strongly enforced based on Compose settings alone; strong enforcement must live in the Docker VM, a companion Linux-hosted gateway, or an explicit outbound proxy path backed by deny rules.
- Any repository profile that lacks an authoritative egress-control plane is validation-only or hardening-only and must not be described as fully compliant with SEC-4 enforcement goals.
- Approved public internet egress is limited to the documented `jaccloud.nl` and `jacloud.nl` destination set. Direct third-party runtime downloads and similar unmanaged public destinations must be removed, routed through the enforcement layer, or tracked as explicit deviations.
- Services and startup helpers must fail fast when required outbound access is blocked or missing; they must not silently fall back to alternate public destinations.

## Rationale
- Compose can express routing intent and reduce exposure, but it cannot by itself provide a credible hostname-allowlisted outbound enforcement claim.
- Linux-hosted Docker gives the repository a realistic place to apply and verify authoritative deny-by-default outbound policy.
- macOS Docker Desktop runs container networking inside Docker Desktop's Linux VM, so host-local Compose settings do not equal host-authoritative firewall enforcement.
- Separating enforcement-capable from validation-only environments avoids false security claims and keeps release evidence technically defensible.
- Removing unmanaged runtime downloads is required for a deny-by-default posture to be operational rather than aspirational.

## Scope Boundaries
This decision covers the repository's engineering claim boundaries for container egress enforcement and the environment-specific interpretation of SEC-4.

It does not by itself define:
- the exact approved FQDN and port inventory beneath `jaccloud.nl` and `jacloud.nl`
- the final firewall rule syntax, proxy product, or gateway implementation
- Docker daemon image-pull policy before containers start
- general workstation internet policy outside repository-managed container execution

## Consequences
**Positive**
- SEC-4 enforcement claims remain tied to a real control surface instead of optimistic Compose interpretation.
- Linux-hosted rollouts have a clear default direction for authoritative enforcement.
- macOS-local development can still be supported without pretending that hardening-only profiles are fully enforced.

**Negative**
- Environment documentation, validation, and release evidence must distinguish enforcement-capable and validation-only profiles.
- Some current startup paths must change before the repository can honestly claim deny-by-default outbound enforcement.
- Local developer convenience may decrease where direct public runtime downloads are removed or blocked.

## Implementation Guidance
- Treat Linux-hosted enforcement as the first supported authoritative path for SEC-4.
- Document macOS Docker Desktop separately and label profiles accurately when they do not have strong outbound enforcement.
- Remove or internalize runtime public downloads before enabling deny-by-default outbound policy broadly.
- Add validation coverage that proves one approved outbound destination succeeds and one unapproved destination fails.
- Record any temporary non-compliant outbound dependency in the architecture deviation register instead of leaving it implicit.

## Related Artifacts
- `architecture/adr/ADR-032-container-egress-deny-by-default-and-approved-destination-enforcement.md`
- `docs/features/SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md`
- `docs/implementation-details/SEC_4_CONTAINER_EGRESS_CONTROL_IMPLEMENTATION_PLAN.md`
- `docker-compose.yml`
- `/memories/repo/dq-rulebuilder-container-egress-firewall-proxy-note.md`