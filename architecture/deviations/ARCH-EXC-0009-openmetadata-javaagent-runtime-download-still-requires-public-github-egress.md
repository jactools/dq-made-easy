# ARCH-EXC-0009: OpenMetadata Javaagent Runtime Download Still Requires Public GitHub Egress

**Status**: Closed
**Category**: vendor-dependency
**Owner**: Platform Engineering
**First recorded**: 2026-04-23
**Last reviewed**: 2026-04-23
**Next review date**: none - closed 2026-04-23
**Closure date**: 2026-04-23
**Target closure date**: 2026-06-30
**Risk level**: high
**Impact level**: high
**Governing baseline**: [ADR-032 Container Egress Deny-by-Default and Approved-Destination Enforcement](../adr/ADR-032-container-egress-deny-by-default-and-approved-destination-enforcement.md), [EDR-044 Container Egress Enforcement and Environment-Specific Claims](../../docs/engineering-decisions/EDR-044-INF-container-egress-enforcement-and-environment-specific-claims.md), [SEC-4 Controlled Container Egress and Approved External Destinations](../../docs/features/SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md), [SEC-4 Container Egress Control Implementation Plan](../../docs/implementation-details/SEC_4_CONTAINER_EGRESS_CONTROL_IMPLEMENTATION_PLAN.md)

## Affected Surface

The historical `openmetadata-otel-javaagent` startup helper in [docker-compose.yml](../../docker-compose.yml) downloaded the OpenTelemetry Java agent from a GitHub release URL during stack startup.

## Summary

This deviation is closed. The OpenMetadata Java agent is now baked into the OpenMetadata server image during image build, so the metadata startup path no longer requires direct public GitHub egress at runtime.

## Rationale

The deviation originally existed because the helper provisioned the Javaagent dynamically from GitHub at startup. That runtime fetch has been removed in favor of baking the artifact into the server image build path.

## Risk Details

While the deviation was open, the metadata startup path depended on public internet availability outside the approved `jaccloud.nl` and `jacloud.nl` destination set. That risk is removed for steady-state startup because the runtime fetch no longer exists.

## Impact Details

Metadata startup and OpenMetadata observability attachment no longer rely on direct GitHub egress at runtime. Environments still need a rebuilt OpenMetadata image to pick up the change.

## Compensating Controls

ADR-032, EDR-044, SEC-4, and the SEC-4 implementation plan made the gap explicit while it was open. The repository validation script [validate_container_egress_policy.sh](../../scripts/validate_container_egress_policy.sh) now fails on unapproved public destinations in stack definitions, which prevents this exact runtime drift from returning silently.

## Validation and Evidence

- [dq-metadata/Dockerfile.openmetadata-server](../../dq-metadata/Dockerfile.openmetadata-server) now downloads the Javaagent during image build and copies it into the OpenMetadata server image.
- [docker-compose.yml](../../docker-compose.yml) no longer defines the `openmetadata-otel-javaagent` runtime helper or the `otel_javaagent_data` volume mount for OpenMetadata startup.
- [validate_container_egress_policy.sh](../../scripts/validate_container_egress_policy.sh) now fails on unapproved public destinations in tracked stack definitions.

## Exit Criteria

Achieved on 2026-04-23: the Javaagent artifact is now provided through the repository-managed OpenMetadata server image build path, and no repository-managed steady-state startup flow requires direct public GitHub access from a container.