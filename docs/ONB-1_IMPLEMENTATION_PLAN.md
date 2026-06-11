# ONB-1 Implementation Plan

**Feature:** Guided Standard Rule Generation  
**Workstream:** WS9-A04  
**Spec:** [docs/features/ONBOARDING_FEATURES.md](./features/ONBOARDING_FEATURES.md)  
**User Guide:** [docs/user-manuals/workflow-onboarding-rule-generation.md](./user-manuals/workflow-onboarding-rule-generation.md)  
**Last updated:** 2026-05-31

---

## Completed Work

### E01: Proposal-Generation Endpoint ✅

**Delivered files (2026-05-31):**

| File | Description |
| --- | --- |
| `dq-api/fastapi/app/domain/entities/onboarding_models.py` | Domain models: ProposedAttribute, ProposedObjectGroup, ProposedTemplateGroup, GenerateProposalsRequest/Response |
| `dq-api/fastapi/app/domain/onboarding_matching.py` | Template matching logic with DAMA registry and matching rules for attribute types/names |
| `dq-api/fastapi/app/application/services/onboarding_service.py` | OnboardingService: orchestrates scope traversal, matching, deduplication, grouping |
| `dq-api/fastapi/app/api/v1/endpoints/onboarding.py` | FastAPI route handler with fail-fast error handling and dependency injection |
| `dq-api/fastapi/app/api/v1/router.py` | Updated to include onboarding router in rulebuilder group |
| `dq-api/fastapi/tests/test_onboarding_proposals.py` | Unit and integration tests for matching, service logic, and endpoint |

**Key features implemented:**

1. **Scope-aware proposal generation**: workspace, product, dataset, or single object
2. **Metadata-driven matching**: 12-template DAMA registry with matching rules for data type, name patterns, and required flags
3. **Grouped response structure**: Proposals grouped by template → dataset → data object, with count rollups at each level
4. **Deduplication**: Attributes with existing active equivalent rules marked as "already_covered"
5. **Fail-fast error handling**: 400 for invalid scope, 401 for unauthorized, 503 with correlation_id for service unavailability
6. **Full test coverage**: Matching logic tests, service orchestration tests, grouping structure validation, count accuracy

**Template registry (12 templates implemented):**

- Completeness: NULL Value Check, Empty String Check, Default Value Detection
- Accuracy: Format Validation, Email Format Check, Phone Number Validation, Allowlist Validation
- Consistency: Referential Integrity
- Timeliness: Freshness Check, Lag Detection, Future Date Detection
- Validity: Range Check
- Uniqueness: Uniqueness

**Contract details:**

```
POST /rulebuilder/v1/onboarding/generate-proposals
Request:
{
  "scope_type": "workspace|product|dataset|object",
  "scope_id": "...",
  "workspace_id": "..."
}

Response:
{
  "scope_type": "workspace",
  "scope_id": "...",
  "total_attributes": 640,
  "total_proposals": 1847,
  "proposals": [
    {
      "template_id": "template-completeness-1",
      "template_name": "NULL Value Check",
      "dimension": "completeness",
      "check_type": "THRESHOLD",
      "total_count": 640,
      "by_dataset": {
        "dataset-1": [
          {
            "data_object_version_id": "version-1",
            "object_name": "customer",
            "dataset_name": "customer_data",
            "count": 45,
            "attributes": [...]
          }
        ]
      }
    },
    ...
  ],
  "generated_at": "2026-05-31T12:34:56Z"
}
```

---

## Dependency Chain

```
E01 (Backend proposal API) ← foundation
  ├─→ E02 (Scope picker UI)
  ├─→ E03 (Review tree UI)
  ├─→ E04 (Batch creation API)
  └─→ E05 (Batch summary UI)
```

All UI work depends on E01 being deployed. E04 cannot complete without E01's proposal structure. E02–E03–E05 can be parallelized once E01 is testable.

---

## Work Items

### Phase 1: Backend Foundation

#### ONB-1-E01: Implement proposal-generation endpoint

**Status**: ✅ COMPLETE (2026-05-31)

**Epic:** Backend proposal API  
**Title:** `POST /api/rules/v1/onboarding/generate-proposals`  
**Acceptance criteria traced:**
- `ONB-1-AC01` (scope selection)
- `ONB-1-AC02` (metadata-driven proposals)
- `ONB-1-AC03` (grouped structure)
- `ONB-1-AC05` (deduplication)

**Scope:**

1. **Route handler** in `dq-api/fastapi/app/api/routes/onboarding.py` (new file):
   - Accept request body: `{ "scope_type": "workspace|product|dataset|object", "scope_id": "...", "workspace_id": "..." }`
   - Validate scope exists and user has access.
   - Return 400 if scope_type is invalid.

2. **Service layer** in `dq-api/fastapi/app/application/services/onboarding_service.py` (new):
   - `generate_proposals(scope_type, scope_id, workspace_id)` → grouped proposal tree.
   - Traverse metadata catalog (via existing `data_assets_repository` or similar).
   - For each attribute, apply matching rules against `DAMA_TEMPLATES`.
   - Query rules repository to identify already-covered attributes.
   - Build grouped response (template → dataset → object → attributes).

3. **Matching logic** in `dq-api/fastapi/app/domain/onboarding_matching.py` (new):
   - `match_templates_to_attribute(attribute, data_type, name, is_required)` → list of (template_id, check_type, severity).
   - Implement rules table (data type → templates, name patterns → templates, requirement flag → severity override).

4. **Domain model** in `dq-api/fastapi/app/domain/onboarding_models.py` (new):
   ```python
   class ProposedAttribute(BaseModel):
       attribute_id: str
       name: str
       data_type: str
       already_covered: bool
   
   class ProposedObjectGroup(BaseModel):
       data_object_version_id: str
       object_name: str
       dataset_name: str
       count: int
       attributes: list[ProposedAttribute]
   
   class ProposedTemplateGroup(BaseModel):
       template_id: str
       template_name: str
       dimension: str
       total_count: int
       by_dataset: dict[str, list[ProposedObjectGroup]]
   
   class GenerateProposalsResponse(BaseModel):
       scope_type: str
       scope_id: str
       total_attributes: int
       proposals: list[ProposedTemplateGroup]
       generated_at: datetime
   ```

5. **Error handling**:
   - 400 if scope_id does not exist.
   - 401 if user lacks workspace access.
   - 503 with correlation_id if metadata or rules service is unreachable (fail-fast).

6. **Tests** in `dq-api/fastapi/tests/test_onboarding_proposals.py` (new):
   - Test scope selection at all four levels (workspace, product, dataset, object).
   - Test metadata signal matching (data type, name patterns, required flag).
   - Test deduplication: existing active rule excludes proposal from default selection.
   - Test grouped response structure: counts at each level.
   - Test service unavailability: 503 with correlation_id.
   - Mock fixtures: attributes, templates, existing rules.

**Effort estimate:** 3–4 days (matching logic, cross-repository queries, test coverage)

---

### Phase 2: UI Implementation (can start after E01 is deployable)

#### ONB-1-E02: Scope selection UI

**Status**: ✅ COMPLETE (2026-05-31)

**Epic:** User input flow  
**Component:** `dq-ui/src/components/OnboardingRuleScopeSelector.tsx` (new)  
**Acceptance criteria traced:**
- `ONB-1-AC01`

**Delivered files (2026-05-31):**

| File | Description |
| --- | --- |
| `dq-ui/src/components/OnboardingRuleScopeSelector.tsx` | Modal component with four-level scope picker and live summary |
| `dq-ui/src/components/OnboardingRuleScopeSelector.css` | Styling for scope selector UI |
| `dq-ui/src/components/OnboardingRuleScopeSelector.test.tsx` | Unit tests covering scope selection, hierarchy navigation, warnings, API integration |

**Key features implemented:**

1. **Modal dialog** for scope selection with clear layout and footer actions
2. **Four-level scope picker hierarchy:**
   - Workspace (default, always available)
   - Data Product (dropdown populated from DataProductContext)
   - Dataset (cascading dropdown, depends on product selection)
   - Data Object + Version (cascading dropdowns for specific object scope)
3. **Live summary display:**
   - Objects count (dynamic based on scope)
   - Attributes count (calculated from metadata)
   - Separator and clean UI formatting
4. **Warning callout for large scopes:**
   - Appears when attribute count > 500
   - Suggests selecting smaller scope for faster navigation
5. **API integration:**
   - Calls `POST /rulebuilder/v1/onboarding/generate-proposals` endpoint (E01)
   - Includes authentication token from context
   - Sends scope_type, scope_id, workspace_id in request
   - Shows error messages on API failure
   - Displays loading state during proposal generation
6. **Hierarchy navigation:**
   - Uses DataProductContext for data loading
   - Implements cascading dropdowns (product → dataset → object → version)
   - Resets dependent selections when parent changes
   - Calls context's lazy-load methods (loadDatasets, loadDataObjects, loadVersions)
7. **Error handling:**
   - Display error notifications on API failure
   - Clear error message to user
   - Graceful degradation if data is unavailable

**Component API:**

```typescript
interface OnboardingRuleScopeSelectorProps {
  isOpen: boolean
  onClose: () => void
  workspaceId: string
  onProposalsGenerated: (response: OnboardingProposalsResponse) => void
}

interface OnboardingProposalsResponse {
  scope_type: OnboardingScopeType
  scope_id: string
  total_attributes: number
  total_proposals: number
  proposals: any[]
  generated_at: string
}

type OnboardingScopeType = 'workspace' | 'product' | 'dataset' | 'object'
```

**Test coverage:**

- Modal renders when `isOpen` is true, hides when false
- Scope type dropdown defaults to 'workspace'
- Scope type can be changed and cascades through selections
- Cascading dropdowns populate correctly based on parent selection
- Summary counts update dynamically as scope changes
- Warning banner appears only when attribute count > 500
- Proceed button disabled when required selections are missing
- Proceed button enabled for valid workspace scope (no selections needed)
- API call successful: onProposalsGenerated callback invoked
- API call fails: error notification shown
- Modal closes after successful proposal generation
- API request contains correct scope_type, scope_id, workspace_id
- loadDatasets called when product selected
- Proper handling of empty datasets/objects lists

**Scope:**

1. **Scope picker modal** with four-level hierarchy:
   - Workspace (default selected)
   - Data product dropdown (if available)
   - Dataset dropdown (if product selected)
   - Data object dropdown (if dataset selected)

2. **Live summary display:** "X objects · Y attributes selected"

3. **Warning callout:** if scope > 500 attributes, warn user about large proposal set.

4. **Proceed button:** calls E01 endpoint to fetch proposals, passes to E03.

5. **Tests:**
   - Hierarchy navigation (product → dataset → object populates correctly).
   - Summary count updates as scope changes.
   - Warning appears only for large scopes.

**Effort estimate:** 1–1.5 days

---

#### ONB-1-E03: Review tree UI with bulk select

**Status**: ✅ COMPLETE (2026-05-31)

**Epic:** Proposal review  
**Component:** `dq-ui/src/components/OnboardingRuleReview.tsx` (new)  
**Acceptance criteria traced:**
- `ONB-1-AC03` (grouped tree)
- `ONB-1-AC04` (bulk select at three levels)
- `ONB-1-AC05` (already-covered display)

**Delivered files (2026-05-31):**

| File | Description |
| --- | --- |
| `dq-ui/src/components/OnboardingRuleReview.tsx` | Proposal review modal with grouped tree, multi-level bulk select, and sticky summary |
| `dq-ui/src/components/OnboardingRuleReview.css` | Review tree styling including sticky summary and responsive filter layout |
| `dq-ui/src/components/OnboardingRuleReview.test.tsx` | Component tests for bulk select, filters, disabled covered attributes, and lazy-load callback |

**Implementation highlights:**

1. **Grouped progressive-disclosure tree:** template → dataset → data object → attributes, collapsed by default.
2. **Bulk selection at all levels:** template, dataset, object, and individual attributes.
3. **Filter bar:** dimension, template, dataset search, data type, and status (All, Selected, De-selected, Already covered).
4. **Already-covered handling:** covered attributes are disabled, excluded from default selection, and marked with an "already covered" badge.
5. **Sticky summary bar:** selected count, already-covered count, total count, and create-drafts action.
6. **Lazy-load hook for large groups:** when expanding object groups with 50+ attributes, optional callback is invoked to fetch/load from cache.
7. **Canonical contract safety:** component accepts backend snake_case payloads and normalizes at the UI boundary.
8. **Interrupt/resume support:** onboarding scope and review state is saved to session storage with an 8-hour TTL and restored via user prompt, allowing users to resume after inactivity (for example, lunch breaks) unless the snapshot has expired.

**Validation:**

- `npm test -- src/components/OnboardingRuleReview.test.tsx` → **9 passed**

**Scope:**

1. **Virtual-scrolled tree** (use existing `react-window` or similar):
   - Level 1: template group (collapsible row).
   - Level 2: dataset (collapsible row).
   - Level 3: data object (collapsible row).
   - Level 4: individual attributes (individual checkboxes).

2. **Checkboxes at each level:**
   - Template group: select/deselect all in group.
   - Dataset: select/deselect all in dataset within group.
   - Object: select/deselect all in object within group.
   - Attribute: individual toggle.

3. **Filter bar (always visible above tree):**
   - Dimension dropdown.
   - Template group dropdown.
   - Dataset search input.
   - Data type filter.
   - Status filter (All · Selected · De-selected · Already covered).

4. **Sticky summary bar (bottom):**
   - "X rules selected · Y already covered · Z total · [Create X draft rules]"

5. **Already-covered badge:** attributes with existing equivalent rules show as disabled with label "already covered", de-selected by default.

6. **Lazy loading:** groups collapsed by default; expanding a group with 50+ attributes fetches from API or loads from response cache.

7. **Tests:**
   - Bulk select/deselect at each level.
   - Filter application hides non-matching rows.
   - Summary bar updates count in real time.
   - Already-covered attribute shown with badge, unchecked by default.

**Effort estimate:** 2–2.5 days

---

#### ONB-1-E04: Batch creation endpoint

**Status**: ✅ COMPLETE (2026-05-31)

**Epic:** Backend batch creation  
**Title:** `POST /api/rules/v1/onboarding/create-batch`  
**Acceptance criteria traced:**
- `ONB-1-AC06` (draft creation with batch ID tag)
- `ONB-1-AC07` (summary without per-rule inspection)

**Scope:**

1. **Route handler** in `dq-api/fastapi/app/api/routes/onboarding.py`:
   - Accept: `{ "workspace_id": "...", "accepted_proposal_ids": ["prop-1", "prop-2", ...] }`
   - Validate proposal IDs belong to accepted scope.
   - Return 400 if any proposal_id is invalid.

2. **Service layer** in `dq-api/fastapi/app/application/services/onboarding_service.py`:
   - `create_rule_batch(workspace_id, accepted_proposal_ids)` → batch summary.
   - For each proposal_id:
     - Re-check that attribute does not already have an equivalent rule (dedup safety).
     - Create rule with status `draft`, `generated: true`, `onboarding_batch_id: {batch_id}`.
     - Assign attribute to rule.
     - Catch and log failures per rule (do not fail entire batch on one rule error).
   - Return batch summary: created count, skipped count (already covered), failed count with reasons.

3. **Domain model** in `dq-api/fastapi/app/domain/onboarding_models.py`:
   ```python
   class CreateBatchRequest(BaseModel):
       workspace_id: str
       accepted_proposal_ids: list[str]
   
   class BatchRuleOutcome(BaseModel):
       proposal_id: str
       status: Literal["created", "skipped", "failed"]
       rule_id: str | None
       reason: str | None
   
   class CreateBatchResponse(BaseModel):
       batch_id: str
       workspace_id: str
       total_accepted: int
       created: int
       skipped: int
       failed: int
       outcomes: list[BatchRuleOutcome]
       created_at: datetime
   ```

4. **Tests:**
   - Create batch with mixed outcomes (some created, some skipped, some failed).
   - Verify created rules have `generated: true`, `onboarding_batch_id: {batch_id}`, `status: draft`.
   - Verify already-covered rules are skipped with reason "attribute already has equivalent rule".
   - Verify batch does not fail if one rule creation fails; others proceed.

**Effort estimate:** 2 days

**Delivered files (2026-05-31):**

| File | Description |
| --- | --- |
| `dq-api/fastapi/app/domain/entities/onboarding_models.py` | Added CreateBatchRequest, BatchRuleOutcome, CreateBatchResponse contracts |
| `dq-api/fastapi/app/application/services/onboarding_service.py` | Added `create_rule_batch(...)` flow with proposal-id validation, dedup safety re-check, per-proposal outcomes, and batch summary aggregation |
| `dq-api/fastapi/app/api/v1/endpoints/onboarding.py` | Added `POST /rulebuilder/v1/onboarding/create-batch` endpoint with workspace auth check, fail-fast 400 for invalid proposal IDs, and 503 error envelope |
| `dq-api/fastapi/tests/test_onboarding_proposals.py` | Added service-level mixed-outcome and invalid-proposal tests for E04 behavior |

**Implementation highlights:**

1. **Canonical create-batch transport:** new endpoint accepts `workspace_id` and `accepted_proposal_ids`, returns `batch_id`, counts, and per-proposal outcomes.
2. **Proposal-id validation:** each accepted ID must match canonical `template_id::data_object_version_id::attribute_id`, exist in workspace catalog, and still match onboarding template logic.
3. **Dedup safety gate:** before creating each draft, service re-checks equivalent active rule coverage (`attribute_id` + `check_type`) and marks as skipped when already covered.
4. **Draft creation contract:** created rules are `generated=true`, `active=false` (draft lifecycle), and linked to attributes via catalog `add_rule_attributes(...)`.
5. **Batch resilience:** one proposal failure does not abort the batch; created/skipped/failed outcomes are returned for all accepted IDs.

---

#### ONB-1-E05: Batch summary UI

**Status**: ✅ COMPLETE (2026-06-01)

**Epic:** Completion feedback  
**Component:** `dq-ui/src/components/OnboardingBatchSummary.tsx` (new)  
**Acceptance criteria traced:**
- `ONB-1-AC07` (summary display)
- `ONB-1-AC08` (bulk submit option)

**Delivered files (2026-06-01):**

| File | Description |
| --- | --- |
| `dq-ui/src/components/OnboardingBatchSummary.tsx` | Summary modal with progress indicator, count tiles, expandable failures list, and two CTA buttons |
| `dq-ui/src/components/OnboardingBatchSummary.css` | Styling for count tiles (created/skipped/failed), progress bar animation, and failure list |
| `dq-ui/src/components/OnboardingBatchSummary.test.tsx` | 12 tests covering counts, progress, "Go to Rules", "Submit for Approval" (success and partial failure), expandable failures, and snake_case normalization |

**Validation:** `npm test -- src/components/OnboardingBatchSummary.test.tsx` → **12 passed**

**Key features implemented:**

1. **Progress indicator** (animated bar + label) while `isCreatingBatch` is true.
2. **Three count tiles** — Created (green), Skipped (amber), Failed (red) — with the batch ID shown above.
3. **Expandable failure list** — toggle shows `proposalId` + `reason` for each failed outcome.
4. **"Go to Rules"** — calls `onGoToRules(batchId)` so the caller can filter the rule list to the batch.
5. **"Submit for Approval"** — iterates `createdRuleIds`, calls `submitForApproval(ruleId)` from `RuleContext` for each; shows a success banner on completion or an error banner for partial failures. Button hides after first submission attempt.
6. **Canonical snake_case normalization** via `snakeToCamel` at the UI boundary; backend response accepted as-is.

**Scope:**

1. **Summary card display:**
   - Batch ID.
   - Created: X rules.
   - Skipped: Y rules (with count of "already covered").
   - Failed: Z rules (with expandable list of reasons).

2. **Progress indicator** during batch creation (while E04 is executing).

3. **Two next-step buttons:**
   - **Go to Rules** → filter rule list to batch ID, open in Rules view.
   - **Submit for Approval** → bulk-submit all created drafts to approval workflow (requires approval API integration).

4. **Tests:**
   - Summary displays correct counts.
   - "Go to Rules" filters by batch_id.
   - "Submit for Approval" calls approval endpoint for all created rule IDs.

**Effort estimate:** 1.5 days

---

## Testing Strategy

### Unit Tests (per work item)
- Each service function tested in isolation with mocked dependencies.
- Matching logic tested with attribute type and name variations.
- Deduplication logic tested with existing and absent rules.

### Integration Tests (E01 + E04)
- End-to-end: generate proposals → create batch → verify rules created.
- Cross-scope: workspace-level, product-level, dataset-level, object-level.
- Failure scenarios: missing scope, unavailable metadata service, duplicate rule names.

### UI Tests (E02, E03, E05)
- Component snapshot tests (Vitest + React Testing Library).
- User interaction: scope selection flow, tree navigation, bulk select, filter application.
- Filter behavior: filtering by dimension, status, data type.

### Smoke Tests
- End-to-end flow in seeded environment: select scope → review proposals → create batch → verify drafts in rule list.

---

## Implementation Sequence

**Week 1:**
- E01 backend service + tests (3–4 days).
- E02 scope selector UI (1 day).

**Week 2:**
- E03 review tree UI (2–2.5 days) — can start after E01 merged to main.
- E04 batch creation endpoint (2 days) — parallel with E03.

**Week 3:**
- E05 batch summary UI (1.5 days).
- Integration testing + smoke tests (1–2 days).
- Documentation updates: API docs, user guide (already exists).

**Estimated total effort:** 10–12 developer-days.

---

## Blockers and Risks

| Risk | Mitigation |
| --- | --- |
| Metadata catalog slow or unavailable | E01 must implement timeout and fail-fast (503). Test with mocked catalog. |
| Large proposal set (10k+ attributes) | E03 uses virtual scrolling and lazy-loads nested groups. Load test with synthetic proposal set. |
| Attribute → existing rule dedup complex | Separate matching logic; unit test extensively. |
| Approval workflow API contract unclear | Clarify with Governance team before E05 implementation. |

---

## Success Criteria

- [x] E01 deployed and testable via Swagger/Postman.
- [x] E02 merged to main and passing CI.
- [x] E03 merged to main and passing CI.
- [x] E04 merged to main and passing CI (22 backend tests pass).
- [x] E05 merged to main and passing CI (12/12 tests).
- [x] No unhandled exceptions or silent fallbacks in any path (verified 2026-06-01: all `except` blocks in backend onboarding service and endpoint either record a per-rule `failed` outcome or raise an HTTP 4xx/503 with correlation_id; frontend surfaces API errors via banner).
- [x] Smoke test covers end-to-end flow in seeded environment (`scripts/smoke_onboarding_flow.sh`; self-contained — loads connection details from the env file via `--env dev|test|prod`; seeded workspace name `"Retail Banking"` is a baked-in constant, no caller-supplied env vars required).
- [ ] User can complete onboarding flow: select scope → review 500+ proposals → create 200+ drafts in < 2 minutes.
