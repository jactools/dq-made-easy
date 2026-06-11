# EDR-030 [INF]: Zammad Support Integration and Ticket Payload Mapping Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: INF

## Context
Support request handling now depends on a concrete Zammad integration rather than an abstract internal envelope. Ticket creation, seeded users, requester identity, and observability all need stable repository rules so support flows do not drift or silently degrade.

## Decision
- Support API code must translate the repository's internal support request envelope into the Zammad ticket payload contract before posting tickets.
- Requester identity must resolve from authenticated email claims rather than opaque user identifiers; if an email cannot be resolved, ticket creation must fail fast.
- Support ticket bodies must carry correlation-relevant identifiers such as request, workspace, and user context so downstream support handling remains auditable.
- Zammad user import data must be generated from seeded repository user data and must preserve required organization references before import.
- Repository monitoring must treat the active Zammad profile and shared services topology as the supported runtime, rather than assuming legacy service names.

## Rationale
- Zammad expects a specific ticket payload shape and does not accept the repository's internal request model directly.
- Email is the durable requester identity Zammad can resolve reliably across seeded and authenticated flows.
- Correlation context is required for operational debugging and support auditability.
- User and organization seeding must line up with Zammad import expectations to avoid partial or misleading support state.

## Scope Boundaries
This decision covers repository-side Zammad integration and request mapping.

It does not by itself define:
- Zammad agent workflows
- SLA or ticket-routing business rules
- outbound Zammad notification behavior

## Consequences
**Positive**
- Support ticket creation is aligned with Zammad's real contract.
- Support requests are attributable and diagnosable across systems.

**Negative**
- Missing or malformed requester identity now fails loudly.
- Zammad import behavior stays coupled to seed-data correctness.

## Implementation Guidance
- Map internal support requests to the Zammad `/api/v1/tickets` shape explicitly.
- Resolve requester email from auth claims and reject unresolved requests.
- Include correlation identifiers in the article body.
- Keep monitoring and compose expectations aligned with the active support stack profile.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-zammad-support-ticket-payload-note.md`
- `/memories/repo/dq-rulebuilder-zammad-observability-metrics-note.md`
- `/memories/repo/dq-rulebuilder-zammad-shared-services-note.md`
- `/memories/repo/dq-rulebuilder-zammad-generated-users-csv-note.md`
- `/memories/repo/dq-rulebuilder-support-requester-email-claims-note.md`
