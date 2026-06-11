# Analytics and Reporting Features

This backlog should stay tied to the platform's actual strengths: DQ run history, observability, incidents, governance, and audit-ready reporting. It should not become a generic BI wishlist.

Scope guardrails:

- Reporting must remain metadata-first and policy-aligned. No raw source records or sensitive payloads should be exposed through analytics exports or dashboards.
- Build on existing DQ-11, DQ-12, DQ-13, and DQ-14 capabilities instead of introducing a parallel analytics model.
- Prefer workspace-scoped views, business-key grouping, and evidence-oriented exports over ad hoc charting.

- [ ] #AR-1 Role-based operational and governance dashboards
	- [ ] `AR-1.1` Add workspace overview tiles for run success rate, failed monitors, open incidents, stale assets, and recent schema changes.
	- [ ] `AR-1.2` Add steward-facing governance dashboards for classification coverage, masking/encryption coverage, contract review status, and policy exceptions.
	- [ ] `AR-1.3` Add owner/team drilldowns grouped by workspace, domain, data product, and business key rather than only technical IDs.
	- [ ] `AR-1.4` Add runtime-specific drilldowns under the existing aggregate execution-monitoring model instead of fragmenting the top-level dashboard.
	- [ ] `AR-1.AC-01` A steward can identify which assets need action without opening individual incidents or rules one by one.
	- [ ] `AR-1.AC-02` A workspace admin can switch from aggregate view to asset/rule/incident drilldown in at most two hops.

- [ ] #AR-2 Audit-ready export and evidence packs
	- [ ] `AR-2.1` Export filtered dashboard views to CSV and JSON with applied filters, time range, workspace, and generated-at metadata.
	- [ ] `AR-2.2` Export incident and observability summaries as metadata-only evidence packs suitable for governance reviews and audit follow-up.
	- [ ] `AR-2.3` Export contract conformance, schema drift, and protection coverage summaries without leaking protected values or failure payloads.
	- [ ] `AR-2.4` Add scheduled export generation for recurring stakeholder reporting.
	- [ ] `AR-2.AC-01` Every export includes provenance metadata so recipients know which filters, workspace, and time window were used.
	- [ ] `AR-2.AC-02` Exports fail closed when the user is not allowed to access the requested workspace or reporting scope.
	- [ ] `AR-2.AC-03` Exports never include raw source data, masked values, or hidden failure payload details.

- [ ] #AR-3 Custom metrics and scorecards
	- [ ] `AR-3.1` Allow admins or stewards to define workspace-scoped derived metrics from existing signals such as pass rate, incident recurrence, SLA breach rate, and protection coverage.
	- [ ] `AR-3.2` Support weighted health scorecards per workspace, domain, data product, or data asset.
	- [ ] `AR-3.3` Allow threshold configuration for warning/critical states and trend direction semantics.
	- [ ] `AR-3.4` Surface metric definitions with owner, rationale, formula, and last calculation time for auditability.
	- [ ] `AR-3.AC-01` Custom metrics must be built from canonical platform signals rather than arbitrary raw-query execution in the UI.
	- [ ] `AR-3.AC-02` Users can understand why a score changed by drilling into contributing runs, incidents, or governance findings.

- [ ] #AR-4 Trend analysis and forecasting signals
	- [ ] `AR-4.1` Add trend views for rule pass/fail rates, anomaly counts, incident recurrence, schema drift frequency, and remediation lead time.
	- [ ] `AR-4.2` Add before/after comparisons for releases, rule changes, contract updates, or protection-policy changes.
	- [ ] `AR-4.3` Highlight deteriorating assets and noisy monitors using rolling windows and configurable baselines.
	- [ ] `AR-4.4` Add simple forward-looking indicators such as projected SLA breach risk or rising incident pressure when enough history exists.
	- [ ] `AR-4.AC-01` Trend views distinguish chronic issues from one-off spikes.
	- [ ] `AR-4.AC-02` Users can pivot from a trend anomaly to the underlying runs, incidents, assets, or contracts that explain it.

Recommended sequencing:

1. `AR-1` first, because the platform already has most of the source signals.
2. `AR-2` next, because exports and evidence packs are immediate user value and align with audit/governance needs.
3. `AR-4` after that, once historical data contracts are stable enough for meaningful comparisons.
4. `AR-3` last, because custom metrics are powerful but can become vague or ungoverned if introduced too early.
