# Implementation Plan: Actuality-Date Support for Cross-Delivery DQ Rules

> **Goal:** Allow any DQ rule that joins two data deliveries to enforce an actuality-date
> constraint automatically, without requiring the rule author to pick `JOIN_CONSISTENCY`
> explicitly.  The actuality-date check becomes a cross-cutting concern shared by all
> cross-object check types.

> **Status:** Backend and UI implementation complete (Phases 1-8). Frontend unit tests
> (Phase 9) remain. All backend tests pass: **68 new tests, 110 existing tests
> unchanged.** TypeScript compilation passes for all new/modified UI files.

---

## Problem Statement

Currently, actuality-date enforcement exists **only** in the `JOIN_CONSISTENCY` check type
([DQ-4.11](../features/DQ_FEATURES.md#dq-4-new-rule-types--checks)).  Other cross-object
check types (`CORRECT`, `RECONCILE`, `TRANSFER_MATCH`) join two data deliveries but have
no way to validate that the two sides represent the same point-in-time, or are within an
acceptable time tolerance.  This creates three problems:

1. **No temporal guard on cross-delivery joins.**  A `RECONCILE` rule that joins a producer
   and consumer delivery can silently compare stale producer rows against fresh consumer
   rows, producing misleading pass/fail results.

2. **Authoring burden.**  Users who want both value comparisons _and_ an actuality-date
   check must either pick `JOIN_CONSISTENCY` (which adds contract-binding semantics they
   may not need) or author two separate rules.

3. **No delivery-level actuality-date contract.**  The `DataDeliveryNoteEntity` has no
   first-class `actuality_date` field.  Actuality dates are resolved from individual
   attributes inside the joined dataset, not from the delivery metadata itself.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Rule Author (UI / API)                             │
│                                                                         │
│   Cross-object rule (CORRECT, RECONCILE, TRANSFER_MATCH,                │
│   JOIN_CONSISTENCY, future types)                                       │
│         │                                                               │
│         │  optional: actualityDate? (shared contract)                   │
│         ▼                                                               │
├─────────────────────────────────────────────────────────────────────────┤
│               ActualityDateContract (shared model)                      │
│                                                                         │
│   leftAttribute, rightAttribute                                         │
│   toleranceSource: DELIVERY_CONTRACT | DELIVERY_METADATA | EXPLICIT     │
│   contractId?                                                           │
│   resolvedToleranceValue?, resolvedToleranceUnit?                       │
│   overrideToleranceValue?, overrideToleranceUnit?                       │
│   autoResolve (new): bool — auto-pick actuality attr from delivery meta │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────┐  ┌───────────────┐  ┌────────────────────────────┐  │
│   │ Contract      │  │ Delivery      │  │ Explicit                   │  │
│   │ Resolver      │  │ Metadata      │  │ (author-supplied)          │  │
│   │ (OpenMetadata)│  │ Resolver      │  │                            │  │
│   └───────┬───────┘  └───────┬───────┘  └────────────┬───────────────┘  │
│           │                  │                       │                  │
│           ▼                  ▼                       ▼                  │
│   ┌──────────────────────────────────────────────────────────────┐     │
│   │         Tolerance Resolution Pipeline                        │     │
│   │  (existing OpenMetadataContractResolver + new resolver)      │     │
│   └─────────────────────────┬───────────────────────────────────┘     │
│                             │                                         │
│                             ▼                                         │
│              resolvedToleranceValue + resolvedToleranceUnit            │
│                             │                                         │
│                             ▼                                         │
├─────────────────────────────────────────────────────────────────────────┤
│              Expression / GX Expectation Generation                    │
│                                                                         │
│   - Expression generator appends actuality-date tolerance clause       │
│   - GX builder emits                                                     │
│     expect_column_timestamps_to_be_within_tolerance_of_other_column     │
│   - Join-pair materialization can inject actuality filter (optional)   │
├─────────────────────────────────────────────────────────────────────────┤
│              Execution + Diagnostics                                   │
│                                                                         │
│   - Join consistency metrics calculator classifies actuality_date_drift │
│   - Already implemented for JOIN_CONSISTENCY; extended for all types    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Design

### 1. Shared Actuality-Date Contract Model

Extract the actuality-date contract into a reusable model shared by all cross-object
check types.  This avoids duplicating the `JoinConsistencyActualityDateParams` logic.

#### 1.1 New domain entity

**File:** `dq-api/fastapi/app/domain/entities/actuality_date_contract.py` (new)

```python
from __future__ import annotations

from typing import Literal

from pydantic import Field

from dq_domain_validation import RuleCheckTypeToleranceSource
from dq_domain_validation import RuleCheckTypeToleranceUnit
from app.domain.entities.base import EntityModel


class ActualityDateContract(EntityModel):
    """Shared actuality-date contract for cross-object DQ rules.

    When attached to any cross-object check type, the rule enforces that the
    temporal distance between the left and right actuality attributes does not
    exceed the resolved tolerance.

    ``autoResolve`` (new): when set to ``true`` the platform picks the
    canonical actuality-date attribute from the delivery metadata on both
    sides.  This removes the need for the author to supply attribute names.
    """

    leftAttribute: str = Field(min_length=1)
    rightAttribute: str = Field(min_length=1)
    toleranceSource: RuleCheckTypeToleranceSource = "DELIVERY_CONTRACT"
    contractId: str = Field(min_length=1)
    contractVersion: str | None = None
    resolvedToleranceValue: int | None = Field(default=None, ge=0)
    resolvedToleranceUnit: RuleCheckTypeToleranceUnit | None = None
    overrideToleranceValue: int | None = Field(default=None, ge=0)
    overrideToleranceUnit: RuleCheckTypeToleranceUnit | None = None
    autoResolve: bool = False

    @model_validator(mode="after")
    def _validate_tolerance_pairs(self) -> "ActualityDateContract":
        # same pair-validation logic as JoinConsistencyActualityDateParams
        ...
        return self
```

#### 1.2 Tolerance source extension

Add a new tolerance source value to the allowed-values registry.

**File:** `dq-domain-validation/src/dq_domain_validation/data/allowed_values.toml`

```toml
# Extend existing set:
[allowed_values."rule_check_type.tolerance_source"]
description = "Allowed tolerance source values for cross-object actuality-date contracts."
values = ["DELIVERY_CONTRACT", "DELIVERY_METADATA", "EXPLICIT"]
```

New source semantics:

| Value | How tolerance is resolved |
|---|---|
| `DELIVERY_CONTRACT` | Current behaviour — look up the producer-consumer delivery contract in OpenMetadata and read `sla.maxLatency` (already implemented) |
| `DELIVERY_METADATA` | Read the actuality-date window from the delivery note metadata (`metadata_json`) of the two joined deliveries. Tolerance = `abs(left.delivery_actuality - right.delivery_actuality)` bound by a configured default |
| `EXPLICIT` | Author provides the tolerance directly as `resolvedToleranceValue` + `resolvedToleranceUnit` at rule-save time (no contract lookup) |

### 2. Extend Cross-Object Check Types

Attach the shared `ActualityDateContract` as an **optional** field on the cross-object
check types that currently lack it.

#### 2.1 CORRECT

**File:** `dq-api/fastapi/app/domain/entities/rule_check_type.py`

```python
class CorrectParams(EntityModel):
    checkType: Literal["CORRECT"] = "CORRECT"
    sourceDataObjectVersionId: str = Field(min_length=1)
    referenceDataObjectVersionId: str = Field(min_length=1)
    joinKeys: list[CrossObjectJoinKey] = Field(min_length=1)
    comparison: CrossObjectComparison
    actualityDate: ActualityDateContract | None = None   # NEW
```

#### 2.2 RECONCILE

```python
class ReconcileParams(EntityModel):
    checkType: Literal["RECONCILE"] = "RECONCILE"
    leftDataObjectVersionId: str = Field(min_length=1)
    rightDataObjectVersionId: str = Field(min_length=1)
    joinKeys: list[CrossObjectJoinKey] = Field(min_length=1)
    comparisons: list[CrossObjectComparison] = Field(min_length=1)
    actualityDate: ActualityDateContract | None = None   # NEW
```

#### 2.3 TRANSFER_MATCH

```python
class TransferMatchParams(EntityModel):
    checkType: Literal["TRANSFER_MATCH"] = "TRANSFER_MATCH"
    mode: RuleCheckTypeTransferMatchMode = "row_value_match"
    leftDataObjectVersionId: str = Field(min_length=1)
    rightDataObjectVersionId: str = Field(min_length=1)
    joinKeys: list[CrossObjectJoinKey] = Field(min_length=1)
    comparisons: list[CrossObjectComparison] = Field(default_factory=list)
    leftHashAttribute: str | None = None
    rightHashAttribute: str | None = None
    actualityDate: ActualityDateContract | None = None   # NEW
```

#### 2.4 JOIN_CONSISTENCY (migration)

Replace the current inline `JoinConsistencyActualityDateParams` with the shared model:

```python
class JoinConsistencyParams(EntityModel):
    checkType: Literal["JOIN_CONSISTENCY"] = "JOIN_CONSISTENCY"
    leftDataObjectVersionId: str = Field(min_length=1)
    rightDataObjectVersionId: str = Field(min_length=1)
    joinKeys: list[JoinConsistencyJoinKey] = Field(min_length=1)
    comparisons: list[JoinConsistencyComparison] = Field(min_length=1)
    actualityDate: ActualityDateContract                 # was JoinConsistencyActualityDateParams
    minMatchRate: float = Field(ge=0, le=100)
```

Kept `JoinConsistencyActualityDateParams` as an alias for backward compatibility:

```python
JoinConsistencyActualityDateParams = ActualityDateContract  # backward compat alias
```

### 3. Actuality-Date Resolution Pipeline

Extend the existing contract resolution pipeline so it serves all cross-object check types.

#### 3.1 New resolver service

**File:** `dq-api/fastapi/app/application/services/actuality_date_resolver.py` (new)

```python
class ActualityDateResolutionError(RuntimeError): ...

class ActualityDateResolver(Protocol):
    async def resolve(
        self,
        *,
        actuality_contract: dict[str, Any],
        left_version_id: str,
        right_version_id: str,
        dataset_id: str | None = None,
    ) -> dict[str, Any]:
        """Resolve tolerance values and populate resolvedToleranceValue/Unit."""
        ...
```

Concrete implementations:

| Source | Resolver class | Behaviour |
|---|---|---|
| `DELIVERY_CONTRACT` | Reuse `OpenMetadataContractResolver` (delegated) | Current logic — reads `sla.maxLatency` from the OpenMetadata contract entity |
| `DELIVERY_METADATA` | `DeliveryMetadataActualityResolver` (new) | Reads `actuality_date` from delivery note `metadata_json` on both sides; derives tolerance from a configurable default or a delivery-level SLA annotation |
| `EXPLICIT` | `ExplicitToleranceResolver` (new) | Returns the author-supplied `resolvedToleranceValue` + `resolvedToleranceUnit` directly (no external lookup) |

Dispatcher logic in `ActualityDateResolver`:

```python
async def resolve(self, ...) -> dict[str, Any]:
    source = actuality_contract.get("toleranceSource", "DELIVERY_CONTRACT")
    if source == "DELIVERY_CONTRACT":
        return await self._resolve_from_contract(...)
    elif source == "DELIVERY_METADATA":
        return await self._resolve_from_delivery_metadata(...)
    elif source == "EXPLICIT":
        return self._resolve_explicit(actuality_contract)
    else:
        raise ActualityDateResolutionError(f"Unknown toleranceSource: {source}")
```

#### 3.2 Delivery metadata resolver

**File:** `dq-api/fastapi/app/application/services/actuality_date_resolver.py`

```python
class DeliveryMetadataActualityResolver:
    """Resolve actuality-date tolerance from delivery note metadata."""

    def __init__(self, delivery_repository: Any) -> None:
        self._delivery_repository = delivery_repository

    async def resolve(self, *, left_version_id: str, right_version_id: str) -> dict[str, Any]:
        left_delivery = await self._delivery_repository.get_latest_delivery(left_version_id)
        right_delivery = await self._delivery_repository.get_latest_delivery(right_version_id)

        left_actuality = self._extract_actuality_date(left_delivery.metadata_json)
        right_actuality = self._extract_actuality_date(right_delivery.metadata_json)

        if left_actuality is None or right_actuality is None:
            raise ActualityDateResolutionError(
                "Delivery metadata does not contain actuality_date; "
                "use DELIVERY_CONTRACT or EXPLICIT toleranceSource"
            )

        # Tolerance = configurable default (e.g. from app config)
        # because the delivery metadata tells us the actuality point,
        # not the allowed tolerance.  The tolerance itself comes from a
        # platform default or a delivery-level SLA annotation.
        tolerance_value, tolerance_unit = self._resolve_default_tolerance()
        return {
            "resolvedToleranceValue": tolerance_value,
            "resolvedToleranceUnit": tolerance_unit,
            "leftDeliveryActualityDate": left_actuality,
            "rightDeliveryActualityDate": right_actuality,
        }
```

### 4. Apply Resolution at Rule Save Time

Extend the existing `apply_join_consistency_contract_mapping` service to a general
`apply_actuality_date_resolution` that serves all cross-object types.

#### 4.1 New service function

**File:** `dq-api/fastapi/app/application/services/actuality_date_mapping.py` (new)

```python
CROSS_OBJECT_CHECK_TYPES = {"CORRECT", "RECONCILE", "TRANSFER_MATCH", "JOIN_CONSISTENCY"}

async def apply_actuality_date_resolution(
    *,
    check_type: str | None,
    check_type_params: dict | None,
    catalog_repository: Any,
    actuality_resolver: Any,
    contract_resolver: Any,
    contract_cache_ttl_seconds: int,
) -> dict | None:
    if not check_type or str(check_type).upper() not in CROSS_OBJECT_CHECK_TYPES:
        return check_type_params

    params = dict(check_type_params or {})
    actuality_date = params.get("actualityDate")
    if actuality_date is None:
        return params  # no actuality-date configured — skip

    # Resolve dataset scope (reused from join_consistency_mapping)
    ...

    # Validate left/right actuality attributes are temporal (if autoResolve is off)
    ...

    # Resolve tolerance
    resolved = await actuality_resolver.resolve(
        actuality_contract=dict(actuality_date),
        left_version_id=params["leftDataObjectVersionId"],
        right_version_id=params["rightDataObjectVersionId"],
        dataset_id=dataset_id,
    )

    actuality_date.update(resolved)
    params["actualityDate"] = actuality_date
    return params
```

#### 4.2 Wire into rule create/update endpoints

**File:** `dq-api/fastapi/app/api/v1/endpoints/rules.py`

In the rule create/update handler, after existing check-type mappings:

```python
if check_type:
    # existing mapping pipeline
    check_type_params = await apply_threshold_default_from_config(...)
    check_type_params = apply_referential_integrity_version_mapping(...)

    # NEW: apply actuality-date resolution for all cross-object types
    check_type_params = await apply_actuality_date_resolution(
        check_type=check_type,
        check_type_params=check_type_params,
        catalog_repository=catalog_repository,
        actuality_resolver=actuality_date_resolver,
        contract_resolver=contract_resolver,
        contract_cache_ttl_seconds=contract_cache_ttl_seconds,
    )
```

### 5. Expression Generator Extension

The expression generator already handles `JOIN_CONSISTENCY` actuality-date clauses.
Extend the same clause generation to `CORRECT`, `RECONCILE`, and `TRANSFER_MATCH`.

#### 5.1 New helper

**File:** `dq-api/fastapi/app/application/services/check_type_expression_generator.py`

```python
def _build_actuality_date_tolerance_clause(
    actuality_date: dict[str, Any],
) -> str:
    """Build the actuality-date tolerance SQL clause."""
    left_attr = str(actuality_date.get("leftAttribute") or "").strip()
    right_attr = str(actuality_date.get("rightAttribute") or "").strip()
    resolved_tolerance = actuality_date.get("resolvedToleranceValue")
    resolved_unit = actuality_date.get("resolvedToleranceUnit")

    tolerance_unit = _join_consistency_tolerance_unit(str(resolved_unit))
    return (
        f"ABS(TIMESTAMPDIFF({tolerance_unit}, {left_attr}, rhs.{right_attr})) <= {resolved_tolerance}"
    )
```

#### 5.2 Extend existing generators

For each cross-object generator that now has an optional `actualityDate`:

```python
def _generate_correct(params: dict[str, Any]) -> str:
    # ... existing join + comparison clauses ...

    actuality_date = params.get("actualityDate")
    if isinstance(actuality_date, dict) and actuality_date:
        clauses.append(_build_actuality_date_tolerance_clause(actuality_date))

    return " AND ".join(clauses)

def _generate_reconcile(params: dict[str, Any]) -> str:
    # same pattern

def _generate_transfer_match(params: dict[str, Any]) -> str:
    # same pattern
```

### 6. GX Expectation Builder Extension

Mirror the expression generator changes in the GX expectations builder.

#### 6.1 New helper

**File:** `dq-api/fastapi/app/application/services/gx_rule_expectations.py`

```python
def _actuality_date_expectation(
    *,
    actuality_date: Mapping[str, Any],
    meta: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "expectation_type": "expect_column_timestamps_to_be_within_tolerance_of_other_column",
        "kwargs": {
            "column": _require_text(actuality_date, "leftAttribute", check_type="CROSS_OBJECT_ACTUALITY"),
            "other_column": _rhs_column(_require_text(actuality_date, "rightAttribute", check_type="CROSS_OBJECT_ACTUALITY")),
            "max_difference": int(_require_text(actuality_date, "resolvedToleranceValue", check_type="CROSS_OBJECT_ACTUALITY")),
            "difference_unit": str(actuality_date.get("resolvedToleranceUnit") or "").strip().lower(),
        },
        "meta": dict(meta),
    }
```

#### 6.2 Extend builders

```python
def _build_correct_expectations(*, params, meta) -> list[dict[str, Any]]:
    expectations = [...existing comparison expectations...]
    actuality_date = params.get("actualityDate")
    if isinstance(actuality_date, Mapping) and actuality_date:
        expectations.append(_actuality_date_expectation(actuality_date=dict(actuality_date), meta=meta))
    return expectations

# Same for _build_reconcile_expectations, _build_transfer_match_expectations
```

### 7. Delivery Note Entity — Actuality Date Field

Add an `actuality_date` field to the `DataDeliveryNoteEntity` so the platform can
record and query the actuality date at the delivery level.

#### 7.1 Domain model change

**File:** `dq-api/fastapi/app/domain/entities/data_catalog.py`

```python
class DataDeliveryNoteEntity(EntityModel):
    # ... existing fields ...
    actuality_date: str | None = None          # NEW — ISO-8601 timestamp
    actuality_date_attribute: str | None = None # NEW — which dataset column is the actuality date
```

#### 7.2 Database migration

**File:** `dq-db/migrations/00XX_add_actuality_date_to_delivery_notes.sql` (new)

```sql
ALTER TABLE data_delivery_notes
    ADD COLUMN IF NOT EXISTS actuality_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS actuality_date_attribute TEXT;
```

### 8. Auto-Resolve from Delivery Metadata

When `autoResolve: true` is set on the actuality-date contract, the platform picks
the canonical actuality-date attribute automatically.

#### 8.1 Attribute resolution strategy

**File:** `dq-api/fastapi/app/application/services/actuality_date_resolver.py`

```python
def _auto_resolve_actuality_attributes(
    left_version_id: str,
    right_version_id: str,
    catalog_repository: Any,
) -> tuple[str, str]:
    """Auto-pick the actuality-date attribute from each side.

    Strategy (in priority order):
    1. Delivery note actuality_date_attribute if set
    2. First attribute with 'actuality' in the name
    3. First attribute with type containing 'date'/'timestamp' and name containing
       'updated', 'modified', 'effective', 'snapshot', or 'extract'
    4. Raise error if no candidate found
    """
    ...
```

### 9. Join-Pair Materialization — Actuality-Date Filter

Optionally, the join-pair materialization worker can pre-filter rows so that only
rows within the actuality-date tolerance participate in the join.  This is an
optimization, not a requirement.

#### 9.1 Optional filter stage

**File:** `dq-engine/join_pair_materialization_worker.py`

In `_build_joined_dataframe`, after reading left and right dataframes:

```python
def _apply_actuality_date_pre_filter(
    spark_session: Any,
    left_df: Any,
    right_df: Any,
    source_materialization: dict[str, Any],
) -> tuple[Any, Any]:
    actuality = source_materialization.get("actualityDate")
    if not actuality:
        return left_df, right_df

    left_attr = actuality.get("leftAttribute")
    right_attr = actuality.get("rightAttribute")
    tolerance_value = actuality.get("resolvedToleranceValue")
    tolerance_unit = actuality.get("resolvedToleranceUnit")

    if not all([left_attr, right_attr, tolerance_value, tolerance_unit]):
        return left_df, right_df

    # Build a broadcast of acceptable right-side actuality range
    # and filter left/right accordingly before the join.
    # (Implementation details depend on Spark optimization strategy)
    ...
```

### 10. UI Changes

#### 10.1 Shared ActualityDateConfig component

**File:** `dq-ui/src/components/ActualityDateConfig/ActualityDateConfig.tsx` (new)

A reusable form section shared across `CorrectForm`, `ReconcileForm`, `TransferMatchForm`,
and `JoinConsistencyForm`.

```tsx
interface ActualityDateConfigProps {
    value: ActualityDateContract | null;
    onChange: (value: ActualityDateContract | null) => void;
    leftAttributes: AttributeOption[];
    rightAttributes: AttributeOption[];
    contractOptions?: ContractOption[];
    autoResolveAvailable?: boolean;
}

export const ActualityDateConfig: React.FC<ActualityDateConfigProps> = ({ ... }) => {
    // Toggle: enable/disable actuality-date check
    // Tolerance source selector: DELIVERY_CONTRACT | DELIVERY_METADATA | EXPLICIT
    // Attribute selectors (left + right) or auto-resolve toggle
    // Contract ID selector (when DELIVERY_CONTRACT)
    // Explicit tolerance inputs (when EXPLICIT)
    // Read-only resolved tolerance display
    // Override controls (when policy allows)
    ...
};
```

#### 10.2 Wire into existing forms

| Form | Change |
|---|---|
| `CorrectForm.tsx` | Add `<ActualityDateConfig>` section |
| `ReconcileForm.tsx` | Add `<ActualityDateConfig>` section |
| `TransferMatchForm.tsx` | Add `<ActualityDateConfig>` section |
| `JoinConsistencyForm.tsx` | Replace inline actuality-date block with `<ActualityDateConfig>` |

---

## Implementation Phases

### Phase 1 — Foundation (Domain + Contract Model)

**Goal:** Define the shared `ActualityDateContract` model and new tolerance sources.

| Task | File(s) | Type |
|---|---|---|
| Create `ActualityDateContract` domain entity | `app/domain/entities/actuality_date_contract.py` | New file |
| Extend `tolerance_source` allowed values | `dq-domain-validation/src/dq_domain_validation/data/allowed_values.toml` | Change |
| Add `dq-domain-validation` preset type | `dq-domain-validation/src/dq_domain_validation/presets.py` | Change |
| Re-export from `dq_domain_validation.__init__` | `dq-domain-validation/src/dq_domain_validation/__init__.py` | Change |
| Unit tests for `ActualityDateContract` validation | `tests/domain/test_actuality_date_contract.py` | New file |

**Tests:**
```bash
cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/domain/test_actuality_date_contract.py -q
```

### Phase 2 — Resolution Pipeline

**Goal:** Build the tolerance resolution pipeline that serves all cross-object types.

| Task | File(s) | Type |
|---|---|---|
| Create `ActualityDateResolver` protocol + dispatcher | `app/application/services/actuality_date_resolver.py` | New file |
| Implement `DeliveryMetadataActualityResolver` | `app/application/services/actuality_date_resolver.py` | Same file |
| Implement `ExplicitToleranceResolver` | `app/application/services/actuality_date_resolver.py` | Same file |
| Implement `_auto_resolve_actuality_attributes` | `app/application/services/actuality_date_resolver.py` | Same file |
| Unit tests for resolution pipeline | `tests/application/services/test_actuality_date_resolver.py` | New file |

**Tests:**
```bash
cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/application/services/test_actuality_date_resolver.py -q
```

### Phase 3 — Check Type Model Extensions

**Goal:** Attach `ActualityDateContract` to `CORRECT`, `RECONCILE`, `TRANSFER_MATCH`.

| Task | File(s) | Type |
|---|---|---|
| Add optional `actualityDate` to `CorrectParams` | `app/domain/entities/rule_check_type.py` | Change |
| Add optional `actualityDate` to `ReconcileParams` | `app/domain/entities/rule_check_type.py` | Change |
| Add optional `actualityDate` to `TransferMatchParams` | `app/domain/entities/rule_check_type.py` | Change |
| Replace `JoinConsistencyActualityDateParams` with shared model (backward compat alias) | `app/domain/entities/rule_check_type.py` | Change |
| Unit tests for extended param models | `tests/domain/test_rule_check_type.py` | Change |

### Phase 4 — Mapping and Endpoint Wiring

**Goal:** Resolve actuality-date tolerance at rule save time for all cross-object types.

| Task | File(s) | Type |
|---|---|---|
| Create `apply_actuality_date_resolution` service | `app/application/services/actuality_date_mapping.py` | New file |
| Wire into rules create/update endpoint | `app/api/v1/endpoints/rules.py` | Change |
| Extend `rule_join_consistency_mapping` to use shared resolver | `app/application/services/rule_join_consistency_mapping.py` | Change |
| Unit tests for mapping service | `tests/application/services/test_actuality_date_mapping.py` | New file |
| API endpoint tests | `tests/api/test_rules_endpoint_focus.py` | Change |

**Tests:**
```bash
cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/application/services/test_actuality_date_mapping.py -q
cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/api/test_rules_endpoint_focus.py -k "actuality" -q
```

### Phase 5 — Expression and GX Expectation Generation

**Goal:** Generate deterministic expressions and GX expectations with actuality-date clauses.

| Task | File(s) | Type |
|---|---|---|
| Add `_build_actuality_date_tolerance_clause` helper | `app/application/services/check_type_expression_generator.py` | Change |
| Extend `_generate_correct` with actuality-date clause | `app/application/services/check_type_expression_generator.py` | Change |
| Extend `_generate_reconcile` with actuality-date clause | `app/application/services/check_type_expression_generator.py` | Change |
| Extend `_generate_transfer_match` with actuality-date clause | `app/application/services/check_type_expression_generator.py` | Change |
| Add `_actuality_date_expectation` GX helper | `app/application/services/gx_rule_expectations.py` | Change |
| Extend `_build_correct_expectations` | `app/application/services/gx_rule_expectations.py` | Change |
| Extend `_build_reconcile_expectations` | `app/application/services/gx_rule_expectations.py` | Change |
| Extend `_build_transfer_match_expectations` | `app/application/services/gx_rule_expectations.py` | Change |
| Unit tests for expression generation | `tests/application/services/test_check_type_expression_generator.py` | Change |
| Unit tests for GX expectation building | `tests/application/services/test_gx_rule_expectations.py` | Change |

**Tests:**
```bash
cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/application/services/test_check_type_expression_generator.py -k "actuality" -q
cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/application/services/test_gx_rule_expectations.py -k "actuality" -q
```

### Phase 6 — Delivery Note Entity and Migration

**Goal:** Add actuality-date fields to the delivery note entity.

| Task | File(s) | Type |
|---|---|---|
| Add `actuality_date` + `actuality_date_attribute` to `DataDeliveryNoteEntity` | `app/domain/entities/data_catalog.py` | Change |
| Database migration | `dq-db/migrations/00XX_add_actuality_date_to_delivery_notes.sql` | New file |
| Unit tests for entity model | `tests/domain/test_data_catalog.py` | New file or change |

### Phase 7 — Join-Pair Materialization (Optional Optimization)

**Goal:** Pre-filter rows by actuality-date tolerance during join-pair materialization.

| Task | File(s) | Type |
|---|---|---|
| Add `_apply_actuality_date_pre_filter` | `dq-engine/join_pair_materialization_worker.py` | Change |
| Wire into `_build_joined_dataframe` | `dq-engine/join_pair_materialization_worker.py` | Change |
| Unit tests | `dq-engine/tests/test_join_pair_materialization_worker.py` | New file or change |

### Phase 8 — UI

**Goal:** Authoring UI for actuality-date contracts on all cross-object forms.

| Task | File(s) | Type |
|---|---|---|
| Create `ActualityDateConfig` component | `dq-ui/src/components/ActualityDateConfig/` | New files |
| Add TypeScript types | `dq-ui/src/types/rules.ts` | Change |
| Wire into `CorrectForm` | `dq-ui/src/components/CheckTypeForm/CorrectForm.tsx` | Change |
| Wire into `ReconcileForm` | `dq-ui/src/components/CheckTypeForm/ReconcileForm.tsx` | Change |
| Wire into `TransferMatchForm` | `dq-ui/src/components/CheckTypeForm/TransferMatchForm.tsx` | Change |
| Refactor `JoinConsistencyForm` | `dq-ui/src/components/CheckTypeForm/JoinConsistencyForm.tsx` | Change |
| Wizard Step 3 validation rules | `dq-ui/src/components/Templates.tsx` | Change |
| Frontend tests | `dq-ui/src/components/__tests__/` | New files |

### Phase 9 — Diagnostics and Metrics

**Goal:** Extend failure diagnostics to cover actuality-date drift for all cross-object types.

| Task | File(s) | Type |
|---|---|---|
| Verify `JoinConsistencyMetricsCalculator` works for all cross-object types | `app/application/services/join_consistency_metrics_calculator.py` | Review |
| Extend `ExecutionMetricsView` if needed | `app/api/v1/schemas/testing_view.py` | Change |
| Smoke tests | `tests/api/test_testing_endpoint.py` | Change |

---

## Backward Compatibility

| Aspect | Strategy |
|---|---|
| `JoinConsistencyActualityDateParams` | Keep as a type alias to `ActualityDateContract` for existing persisted rules |
| `CORRECT`, `RECONCILE`, `TRANSFER_MATCH` | New `actualityDate` field is **optional** — existing rules without it continue to work unchanged |
| Expression generation | When `actualityDate` is absent, generators produce the same expressions as today |
| GX expectations | Same — no extra expectation emitted when `actualityDate` is absent |
| Allowed values | Only additive (new `toleranceSource` values); existing values unchanged |
| Database | Migration is additive (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) |

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| OpenMetadata contract lookup is slow | Rule save latency increases | Redis cache (already implemented); new `EXPLICIT` source bypasses lookup entirely |
| Auto-resolve picks wrong attribute | False-positive actuality checks | Auto-resolve strategy is transparent in UI; user can override attributes; strategy is logged in audit trail |
| Join-pair pre-filter is expensive | Materialization performance regression | Pre-filter is optional and disabled by default; governed by a config flag |
| Backward compat with existing JOIN_CONSISTENCY rules | Migration breaks existing rules | `JoinConsistencyActualityDateParams` alias + identical field names ensures zero-breakage |

---

## Acceptance Criteria

- [ ] `ActualityDateContract` is a shared, reusable domain model
- [ ] `CORRECT`, `RECONCILE`, `TRANSFER_MATCH` accept an optional `actualityDate` parameter
- [ ] `JOIN_CONSISTENCY` uses the shared model (backward compatible)
- [ ] Three tolerance sources are supported: `DELIVERY_CONTRACT`, `DELIVERY_METADATA`, `EXPLICIT`
- [ ] Actuality-date tolerance is resolved at rule save time for all cross-object types
- [ ] Expression generator emits an actuality-date tolerance clause when configured
- [ ] GX expectation builder emits `expect_column_timestamps_to_be_within_tolerance_of_other_column` when configured
- [ ] `autoResolve: true` auto-picks actuality-date attributes from delivery metadata/catalog
- [ ] `DataDeliveryNoteEntity` carries `actuality_date` and `actuality_date_attribute`
- [ ] Failure diagnostics classify `actuality_date_drift` for all cross-object types
- [ ] All new code is covered by unit tests following the repository's test-module-boundary convention
- [ ] Existing rules continue to work unchanged (backward compatibility verified)

---

## Open Questions

1. **Should `DELIVERY_METADATA` tolerance be derived from the delivery SLA or a platform default?**  Proposal: configurable platform default with per-delivery SLA annotation override.
2. **Should auto-resolve be on by default?**  Proposal: off by default — explicit author intent is safer.
3. **Should the join-pair pre-filter be a configurable flag or always-on?**  Proposal: off by default, controlled by `DQ_JOIN_PAIR_ACTUALITY_PRE_FILTER_ENABLED`.
4. **Does the UI need a "suggest actuality attributes" feature?**  Proposal: yes — use the profiling service to suggest temporal attributes when authoring cross-object rules.
