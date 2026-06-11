# API-5 Business Metadata Integration (Source for Business Terms)

Goal: Use an external business catalog as the authoritative source for business terms used in rule expressions.

Related work: [API-7 Real DQ Rule Execution](./API_7_REAL_DQ_RULE_EXECUTION.md)

## Phase 1: Catalog Connectivity

- Add a catalog adapter service in `dq-api` with configurable provider settings.
- Implement a read-only sync endpoint for business terms and their metadata.
- Store synced terms in local cache tables to keep validation resilient during catalog outages.
- Add a health indicator and sync timestamp for operational visibility.

## Phase 2: Business-Term Resolution in Rule Flow

- Extend business-term resolution order: `catalog business term -> manual mapping -> raw technical attribute token`.
- Enrich business-term expectation checks with catalog datatype and optional domain constraints.
- Keep manual mapping supported as fallback to avoid breaking existing rules.
- Add diagnostics that explicitly say whether business-term metadata came from catalog or fallback mapping.

## Phase 3: UI Integration

- In the mapping modal, show catalog term suggestions for detected business terms.
- Display source badge per business term: `Catalog` or `Manual`.
- Allow users to override a catalog mapping (with audit trail) when needed.
- Add filter/search by business domain or glossary term.

## Phase 4: Governance and Lifecycle

- Add drift checks to detect when catalog definitions change and impact active rules.
- Add approval workflow hook for rules affected by business-term metadata changes.
- Add versioned snapshots of resolved business-term metadata per rule version.
- Provide revalidation batch action for all impacted rules.

## Acceptance Criteria

- Validating `email-format-validation` only reports true unresolved business terms.
- Rules can validate successfully when catalog is temporarily unavailable (using cached metadata).
- Rule details show traceable business-term provenance (`Catalog` vs `Manual`).
- Existing rules without catalog mappings continue to work unchanged.

## Tracked Work Items (Complete)

- [x] `API-5.1` Catalog adapter interface and provider config
- [x] `API-5.2` Catalog term sync endpoint and cache schema
- [x] `API-5.3` Health/status endpoint for sync freshness
- [x] `API-5.4` Business-term resolver precedence implementation
- [x] `API-5.5` Validation enrichment with catalog datatypes/domains
- [x] `API-5.6` Validation diagnostics with provenance (`Catalog` vs `Manual`)
- [x] `UX-5.1` Assign Attributes modal business-term suggestions
- [x] `UX-5.2` Business-term source badges and override UX
- [x] `API-5.WF-1` Metadata drift detection for active rules
- [x] `API-5.WF-2` Revalidation batch action for impacted rules
- [x] `API-5.WF-3` Rule version snapshot of resolved business-term metadata
- [x] `DOC-5.1` Integration runbook and fallback behavior

## Delivery Milestones

- Milestone A (Foundation): complete
- Milestone B (Core Logic): complete
- Milestone C (UI): complete
- Milestone D (Governance): complete (`API-5.WF-1` to `API-5.WF-3`)
- Milestone E (Docs/Hardening): complete

## Notes

- Phase 1 is covered by [docs/technical/API_5_SETUP_GUIDE.md](../technical/API_5_SETUP_GUIDE.md).
- Phase 2 is covered by [docs/implementation-details/API_5_PHASE_2_COMPLETE.md](../implementation-details/API_5_PHASE_2_COMPLETE.md).
- Phase 4 is covered by [docs/implementation-details/API_5_PHASE_4_COMPLETE.md](../implementation-details/API_5_PHASE_4_COMPLETE.md).
- Phase 5 is covered by [docs/implementation-details/API_5_PHASE_5_UI_INTEGRATION.md](../implementation-details/API_5_PHASE_5_UI_INTEGRATION.md).
- Incident runbooks and regression coverage are already present under [docs/runbooks/](../runbooks/).
