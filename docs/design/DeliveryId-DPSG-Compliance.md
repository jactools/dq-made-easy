# DeliveryId DPSG Compliance — Design for Redeliveries and Corrections

**Status**: Implemented (Phase 1 — Model + Endpoints)
**Author**: Agent (review pending)
**Related**: [Solution Design — Canonical Data Delivery Phase 1](../../tmp/Solution%20Design%20-%20Canonical%20Data%20Delivery%20Phase%201.pptx), [DPSG Data Immutability Standards V4.1.4]
**Tracked Work Items**: None yet (new workstream)

---

## Implementation Status

**Phase 1 (Model + Endpoints): Implemented**

| Component | Status | Notes |
|-----------|--------|-------|
| Entity model | ✅ Done | `DataDeliveryNoteEntity` extended with 5 new fields |
| View model | ✅ Done | `DataDeliveryNoteView` extended with 5 new fields |
| ORM model | ✅ Done | `DataDeliveryNoteRow` extended with 5 new columns |
| Migration | ✅ Done | `20260721_0001_add_dpsg_redelivery_fields.py` |
| Postgres repository | ✅ Done | Maps new fields from DB rows |
| In-memory repository | ✅ Done | Maps new fields from seed data |
| Endpoints | ✅ Done | `GET /data-deliveries/{id}/occurrences`, `POST /data-deliveries/{id}/correction`, `POST /data-deliveries/{id}/archive` |

**Phase 2 (Migration + Backfill): Not started**

**Phase 3 (Enforcement): Not started**

## Problem

The canonical `DeliveryId` (`{producerSystem}:{dataObjectLogicalName}:{version}:{jobId}`) is a **deterministic business key for a delivery stream**, not a unique delivery occurrence. This causes four compliance gaps against DPSG immutability standards:

| # | Gap | Impact |
|---|-----|--------|
| 1 | DeliveryId does not uniquely identify a delivery event | Daily runs produce identical IDs; consumers cannot distinguish individual deliveries |
| 2 | No explicit supersession/correction relationship | Wrong data → correction → normal delivery: all share the same DeliveryId; no traceability |
| 3 | DeliveryVersion underspecified | Monotonic counter doesn't capture new partitions, archived wrong data, or removal events |
| 4 | No distinction between retries and corrections | Business meaning changes vs identical reprocessing: both collapse into the same counter |

### DPSG Requirement

From the DPSG immutability standard:
> When wrongly prepared data is corrected: the incorrect data is archived, removed from the active area, and the corrected data is ingested as a new delivery.

For Brown Layer Parquet, corrected data lands in a new `EDL_LOAD_DTS` partition and **never overwrites the old one**. Consumers must be able to trace which delivery was wrong, which corrected it, and whether a delivery has been superseded.

---

## Design Principles

1. **DeliveryId stays deterministic** — it remains the business key for a delivery stream. Consumers use it to ask "which deliveries belong to this stream?"
2. **DeliveryTimeEvent is the unique occurrence identifier** — every ingestion, retry, and correction gets a new UUIDv7. This is the primary key for individual deliveries.
3. **Corrections are explicit relationships** — a correction delivery references its predecessor and declares the reason.
4. **No overwrites** — corrections create new delivery records; wrong deliveries are archived (status change), not deleted.
5. **Backward compatible** — existing delivery notes that lack correction metadata continue to work; the new fields are nullable.

---

## Proposed Model

### Delivery Occurrence Record

A new domain concept: **Delivery Occurrence** — an individual delivery event within a delivery stream.

```
DeliveryOccurrence {
    delivery_id: str                  # Deterministic stream key (unchanged)
    delivery_time_event: str          # UUIDv7 — unique occurrence identifier (PRIMARY KEY)
    delivery_version: int             # Monotonic business version within this stream
    delivery_type: DeliveryType       # initial | retry | correction | backfill | deletion | retention
    predecessor_time_event: str | None  # UUIDv7 of the delivery being corrected/replaced
    correction_reason: str | None     # Why a correction was needed
    superseded_by_time_event: str | None  # UUIDv7 of the delivery that supersedes this one
    layer: str                        # brown | gold | silver (inherited from delivery stream)
    storage_location: str | None      # Where the delivery was written
    delivery_location: str | None     # Consumer-facing location
    record_count: int = 0
    size_bytes: int = 0
    checksum: str | None              # Content hash for integrity
    checksum_algorithm: str | None
    delivered_at: str                 # ISO timestamp
    delivered_by: str | None          # Pipeline or agent that produced this delivery
    status: DeliveryStatus            # ingested | validated | archived | superseded
    object_storage_classification: str | None  # synthetic | real
    evidence_classification: str | None        # test | evidence
    metadata_json: dict | None        # Free-form extension space
}

DeliveryType: Enum
    initial     — First delivery for this stream at this point in time
    retry       — Identical reprocessing, no business meaning change
    correction  — Wrong data replaced; business meaning changed
    backfill    — Historic data loaded for a past period
    deletion    — Logical deletion marker (data archived, not deleted)
    retention   — Retention/snapshot event

DeliveryStatus: Enum
    ingested    — Delivery written to storage
    validated   — Controls (DTC, DQ, Guard) have passed
    archived    — Wrong data moved to archive area
    superseded  — Delivery replaced by a correction (status set on predecessor)
```

### Key Relationships

```
┌──────────────────────────────────────────────────────────────┐
│  Delivery Stream: sap:customer:1:daily-load                  │
│  (DeliveryId — deterministic business key)                   │
└──────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
    ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
    │ v1      │          │ v2      │          │ v3      │
    │ initial │──cor───▶│correct  │          │ initial │
    │ UUIDv7-A│         │ UUIDv7-B│          │ UUIDv7-C│
    │ status: │         │status:  │          │ status: │
    │ super-  │         │validated│          │validated│
    │ seded   │         │predecessor: A      │         │
    └─────────┘         │superseded_by: none  │         │
                        └─────────────────────┘         │
                                                         │
                              ┌───────────────────────────┘
                              │
                         ┌────▼────┐
                         │ v4      │
                         │correct  │
                         │ UUIDv7-D│
                         │status:  │
                         │validated│
                         │predecessor: C
                         └─────────┘
```

### Correction Lifecycle

When wrong data is detected:

1. **Wrong delivery ingested** — `uuidv7-A`, type=`initial`, status=`ingested`
2. **Error detected** — DQ/Guard flags the delivery
3. **Wrong delivery archived** — `uuidv7-A` status → `superseded`
4. **Correct delivery ingested** — `uuidv7-B`, type=`correction`, `predecessor_time_event=A`, status=`ingested`
5. **Validation passes** — `uuidv7-B` status → `validated`

Consumers can answer:
- **Which delivery was wrong?** → Query by `predecessor_time_event`
- **Which delivery corrected it?** → Query the predecessor's `superseded_by_time_event`
- **Has this delivery been superseded?** → Check `status == superseded`
- **Is this a retry or a correction?** → Check `delivery_type`

---

## Data Delivery Note Extension

The existing `DataDeliveryNoteEntity` maps directly to the DeliveryOccurrence model. New fields are nullable for backward compatibility:

| Current Field | Status | Change |
|---------------|--------|--------|
| `id` | Keep | Still the primary key (maps to `delivery_time_event`) |
| `data_delivery_id` | Keep | Maps to deterministic `delivery_id` |
| `version` | Keep | Maps to `delivery_version` |
| `storage_location` | Keep | — |
| `delivery_location` | Keep | — |
| `delivered_at` | Keep | — |
| `layer` | Keep | — |
| `object_storage_classification` | Keep | — |
| `evidence_classification` | Keep | — |
| `delivery_status` | Keep | Extended enum: add `superseded` |
| `checksum` | Keep | — |
| `checksum_algorithm` | Keep | — |
| `execution_summary` | Keep | — |
| `execution_references` | Keep | — |
| `metadata_json` | Keep | Extension space |
| **`delivery_type`** | **New** | `DeliveryType` enum |
| **`predecessor_time_event`** | **New** | UUIDv7 reference to corrected delivery |
| **`superseded_by_time_event`** | **New** | UUIDv7 reference to correction |
| **`correction_reason`** | **New** | Free-text reason |
| **`delivered_by`** | **New** | Pipeline/agent identifier |

---

## API Surface

### New/Extended Endpoints

#### `GET /data-deliveries/{delivery_time_event}/note`

Retrieve a delivery note by its unique occurrence ID (UUIDv7). Existing endpoint already supports this pattern via `delivery_id`; the extension adds `delivery_type`, `predecessor_time_event`, `superseded_by_time_event`, and `correction_reason` to the response.

#### `GET /data-deliveries/{delivery_id}/occurrences`

List all delivery occurrences for a delivery stream. Returns a paginated list of `DeliveryOccurrenceView` objects with:

```json
{
  "delivery_id": "sap:customer:1:daily-load",
  "occurrences": [
    {
      "delivery_time_event": "019a...b2c3",
      "delivery_version": 1,
      "delivery_type": "initial",
      "predecessor_time_event": null,
      "superseded_by_time_event": "019a...d4e5",
      "correction_reason": null,
      "status": "superseded",
      "delivered_at": "2026-07-20T00:00:00Z"
    },
    {
      "delivery_time_event": "019a...d4e5",
      "delivery_version": 2,
      "delivery_type": "correction",
      "predecessor_time_event": "019a...b2c3",
      "superseded_by_time_event": null,
      "correction_reason": "Wrong transaction amounts due to currency conversion error",
      "status": "validated",
      "delivered_at": "2026-07-20T06:00:00Z"
    }
  ]
}
```

#### `POST /data-deliveries/{delivery_time_event}/archive`

Archive a delivery (mark as superseded). Required for the DPSG correction workflow:

```json
{
  "reason": "Superseded by correction",
  "superseded_by_time_event": "019a...d4e5"
}
```

#### `POST /data-deliveries/{delivery_id}/correction`

Create a correction delivery reference. Validates that the predecessor exists and is not already superseded:

```json
{
  "delivery_time_event": "019a...d4e5",
  "predecessor_time_event": "019a...b2c3",
  "correction_reason": "Currency conversion error in batch 2026-07-20",
  "delivery_type": "correction",
  "storage_location": "s3://bucket/data/sap/customer/2026-07-20/v2/",
  "record_count": 15234,
  "checksum": "sha256:abc123..."
}
```

---

## Migration Path

### Phase 1 (Current)

Existing delivery notes have no `delivery_type`, `predecessor_time_event`, etc. All existing deliveries are treated as `initial` type with no predecessor.

### Phase 2 (Migration)

1. **Add nullable columns** to `data_delivery_notes` table:
   - `delivery_type` (VARCHAR, default `initial`)
   - `predecessor_time_event` (VARCHAR, nullable, indexed)
   - `superseded_by_time_event` (VARCHAR, nullable, indexed)
   - `correction_reason` (TEXT, nullable)
   - `delivered_by` (VARCHAR, nullable)

2. **Backfill** existing rows: set `delivery_type = 'initial'`, leave predecessor fields null.

3. **Update `DataDeliveryNoteView`** schema with new fields (all optional).

4. **Add `occurrences` endpoint** to list all occurrences for a delivery stream.

### Phase 3 (Enforcement)

- `delivery_type` required for new deliveries
- Correction workflow: archive predecessor before ingesting correction
- `predecessor_time_event` required when `delivery_type = correction`
- Validation: cannot supersede an already-superseded delivery

---

## Impact on Existing Services

| Service | Impact |
|---------|--------|
| **DQ (Rule Execution)** | Rules execute against `delivery_time_event` (unique occurrence), not just `delivery_id`. Existing behavior unchanged — rules already use delivery notes. |
| **DTC (Data Transfer Controls)** | Controls attach to `delivery_time_event` for traceability. |
| **Guard** | Can query `delivery_type = correction` to identify correction deliveries for special handling. |
| **ABS-3 (Delivery-Linked Execution)** | Execution results attach to `delivery_time_event`. Correction deliveries get their own execution results. |
| **ODCS Contracts** | Unchanged. Contracts reference `dataProductId`, not delivery occurrences. |
| **Exception Reports** | Exception analytics resolve delivery notes by `delivery_time_event`. Can distinguish corrections from normal deliveries. |
| **Audit Trail** | Correction events logged with predecessor reference. |

---

## Open Questions

1. **Who generates the UUIDv7?** — Delivery Orchestrator (Phase 1 design) or the ingest pipeline? Recommendation: Delivery Orchestrator to ensure consistency.

2. **Can a correction have multiple predecessors?** — DPSG seems to imply one wrong delivery → one correction. Recommendation: single predecessor for simplicity; multiple predecessors would require a list field.

3. **What about cascading corrections?** — A correction itself has an error and needs another correction. Recommendation: chain via `predecessor_time_event` (UUIDv7-D → UUIDv7-B → UUIDv7-A).

4. **Retention vs Deletion** — DPSG mentions record-level retention. Should this be a delivery type or a separate lifecycle event? Recommendation: separate lifecycle event on the same delivery occurrence.

5. **EMR integration** — The Phase 1 design positions EMR as the Canonical Delivery Registry. Should the delivery occurrence model live in EMR or in the dq-api store? Recommendation: dq-api stores the note; EMR is the authoritative registry. Synchronization via existing metadata flows.

---

## Acceptance Criteria

| ID | Criterion |
|----|-----------|
| DDN-C01 | A delivery note can be retrieved by `delivery_time_event` (UUIDv7) |
| DDN-C02 | All occurrences for a `delivery_id` stream are listable |
| DDN-C03 | A correction delivery references its predecessor via `predecessor_time_event` |
| DDN-C04 | A superseded delivery's `status` is `superseded` and `superseded_by_time_event` points to the correction |
| DDN-C05 | `delivery_type` distinguishes initial, retry, correction, backfill, deletion, retention |
| DDN-C06 | Existing delivery notes without new fields continue to work (backward compatible) |
| DDN-C07 | Correction workflow: predecessor must exist and not already be superseded |
| DDN-C08 | Audit trail records correction events with predecessor reference |
| DDN-C09 | Consumers can query "which delivery corrected delivery X?" and "has delivery X been superseded?" |
| DDN-C10 | Checksum validation ensures correction data differs from predecessor data |

---

## File List

| File | Purpose |
|------|---------|
| `docs/design/DeliveryId-DPSG-Compliance.md` | This design document |
| `dq-api/fastapi/migrations/...` | Add nullable columns to `data_delivery_notes` |
| `dq-api/fastapi/app/domain/entities/data_delivery_note.py` | New fields on entity |
| `dq-api/fastapi/app/api/v1/schemas/data_catalog_view.py` | New fields on view |
| `dq-api/fastapi/app/api/v1/endpoints/data_catalog.py` | New/extended endpoints |
| `dq-api/fastapi/app/infrastructure/repositories/...` | Updated queries |
| `dq-api/fastapi/tests/api/test_data_delivery_notes.py` | New tests |
| `dq-db/mock-data/data-delivery-notes.csv` | Seed data with correction examples |
