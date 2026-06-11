# API-7 Data Delivery Resolution Plan

This note turns the delivery question into an actionable backlog.

Goal: keep the logical execution model on `data_object_version`, but resolve the runtime input from a concrete `data_delivery` so real executions can target the latest delivery or a pinned historical delivery.

## Problem Statement

The current model can describe data products, datasets, data objects, and data object versions. That is enough for logical cataloging, but it is not enough for real execution once delivery events exist.

Real source data arrives as a delivery under a specific data object version, and the executor needs a stable, concrete location for the run. The same physical data may also be reachable through more than one access path.

## Recommended Model Split

- `data_object_version` remains the logical version boundary.
- `data_delivery` becomes the runtime record for one delivered snapshot.
- The executor resolves against a specific delivery, not directly against the version row.
- The execution contract snapshots both the version and the delivery actually used.

## Delivery Note

The delivery table should stay compact and operational. For user-facing context, introduce a separate delivery note concept that describes one concrete delivery in richer detail.

- The delivery note is a storage-independent metadata envelope for a specific delivery.
- It includes the fields already known in `data_delivery` plus additional metadata supplied by the ingestor at delivery time.
- Other services can append their own delivery-specific metadata later, without changing the delivery row itself.
- The note should be readable without direct storage access, so users can inspect delivery details even when the underlying object store is unavailable.
- The note can surface the delivery id, delivery location, delivered at time, counts, checksums, source context, and other provenance details as they become available.

### Delivery Note Model

Keep the delivery note as a separate read model, derived from `data_delivery` and enriched by the ingestor and other services.

- Core identity: `data_delivery_id`, `data_object_version_id`, `delivery_location`, `delivered_at`.
- Operational summary: `delivery_status`, `delivery_format`, `record_count`, `size_bytes`, `file_count`.
- Provenance: `ingestor_name`, `ingestor_run_id`, `source_system`, `source_snapshot_id`, `checksum`, `checksum_algorithm`.
- Extensibility: `metadata_json` for append-only enrichment by downstream services.
- Presentation rule: the UI reads the note, not the storage layer, so the note must be sufficient to explain what the delivery is and who created it.

### Suggested Delivery Note Shape

```json
{
   "id": "dn-001",
   "data_delivery_id": "del-30",
   "data_object_version_id": "dov-1",
   "delivery_location": "s3a://bucket/schema/object/1/LOAD_DTS=20260412T110022000Z",
   "delivered_at": "2026-04-12T11:00:22Z",
   "delivery_status": "completed",
   "delivery_format": "parquet",
   "record_count": 142900,
   "size_bytes": 45200000,
   "file_count": 3,
   "ingestor_name": "data-ingestor",
   "ingestor_run_id": "ing-20260412-1100",
   "source_system": "crm",
   "source_snapshot_id": "snap-20260412-1100",
   "checksum": "b2f3d8...",
   "checksum_algorithm": "sha256",
   "metadata_json": {
      "workspace_id": "retail-banking",
      "batch_id": "20260412-1100",
      "notes": ["validated", "published"]
   }
}
```

### Suggested API Surface

- `GET /data-catalog/v1/data-deliveries/{data_delivery_id}/note` returns the delivery note for one concrete delivery.
- `GET /data-catalog/v1/data-deliveries/{data_delivery_id}` can keep returning the compact delivery row for compatibility.
- `GET /data-catalog/v1/delivery-inventory` can remain the workspace-scoped overview, while the note endpoint becomes the detail view.
- The note endpoint should fail fast if the delivery is unknown, and it should not require object storage access to render the response.

## Execution Modes

- `latest_delivery`: resolve the newest eligible delivery for the active `data_object_version_id`.
- `specific_delivery`: run against an explicit `data_delivery_id`, even if it is not the newest one.

## Actionable Backlog

1. [ ] (API7-DEL-01) Extend the delivery model.
   - Add `data_object_version_id` to `data_deliveries` if it is not already present.
   - Add `data_delivery_id` as the public runtime identifier.
   - Add `delivery_location` as the canonical runtime location.
   - Add `delivered_at`, `delivery_status`, and `delivery_format` or equivalent fields.
   - Add an optional `access_paths_json` or similar structure for alternate read paths to the same physical delivery.

2. [ ] (API7-DEL-02) Stop treating version storage as the only runtime pointer.
   - Keep `data_object_versions.storage_uri` for compatibility if needed.
   - Make delivery resolution the preferred runtime path.
   - Preserve version storage only as a fallback during transition, not as the long-term source of truth.

3. [ ] (API7-DEL-03) Add a delivery resolver.
   - Input: active `data_object_version_id` plus a resolution mode.
   - Output: one resolved delivery with a concrete location and access metadata.
   - Fail fast if no eligible delivery exists.
   - Fail fast if a requested `data_delivery_id` does not belong to the target version.

4. [ ] (API7-DEL-04) Snapshot the resolved delivery into execution.
   - Add `resolved_data_delivery_id` to the run/execution contract.
   - Add `resolved_delivery_location` to the run/execution contract.
   - Include the delivery resolution mode used by the planner or user.

5. [ ] (API7-DEL-05) Support reruns against a pinned delivery.
   - Add an API input for `data_delivery_id` when the user wants a replay.
   - Keep latest-delivery behavior as the default for normal scheduling.
   - Do not silently upgrade a pinned rerun to the latest delivery.

6. [ ] (API7-DEL-06) Update the plan and scheduling flow.
   - Let the plan define the logical scope.
   - Let the execution request choose latest vs pinned delivery resolution.
   - Keep governance separate from delivery selection.

7. [ ] (API7-DEL-07) Update the UI.
   - Show the latest delivery for each active data object version.
   - Provide a rerun path that lets an operator choose an older delivery.
   - Show the resolved delivery id and location before dispatch.

8. [ ] (API7-DEL-08) Validate access-path flexibility.
   - Support multiple read methods for the same physical delivery where needed.
   - Keep the canonical delivery record stable even if the read path changes.
   - Avoid representing alternate access methods as separate deliveries.

9. [ ] (API7-DEL-09) Add migration and compatibility work.
   - Backfill delivery rows from existing generated or imported delivery data.
   - Add indexes for `data_object_version_id`, `data_delivery_id`, and `delivered_at`.
   - Keep the old storage fields readable until the resolver is fully adopted.

10. [ ] (API7-DEL-10) Add tests.
    - Latest delivery resolves correctly.
    - Specific delivery reruns resolve correctly.
    - Missing delivery fails fast.
    - Delivery outside the target version fails fast.
    - Inaccessible delivery fails fast.

11. [ ] (API7-DEL-11) Introduce a delivery note.
   - Define a storage-independent note model for one concrete delivery.
   - Include the core delivery row data plus ingestor-provided metadata.
   - Allow other services to enrich the note without mutating the delivery row.
   - Make the note the preferred user-facing detail view for a delivery.

## Suggested Contract Shape

```json
{
	"source_selection": {
		"mode": "latest_delivery",
		"data_object_version_id": "dov-1",
		"data_delivery_id": null
	},
	"resolved_source": {
		"data_object_version_id": "dov-1",
		"data_delivery_id": "del-30",
		"delivery_location": "s3a://bucket/schema/object/1/LOAD_DTS=20260412T110022000Z"
	}
}
```

## Acceptance Criteria

1. [ ] (API7-DEL-12) A normal run resolves the latest eligible delivery for the active data object version.
2. [ ] (API7-DEL-13) A rerun can target a specific historical `data_delivery_id`.
3. [ ] (API7-DEL-14) The executor uses a concrete delivery location, not just a logical version id.
4. [ ] (API7-DEL-15) The run record stores the exact delivery that was used.
5. [ ] (API7-DEL-16) The system fails fast when a requested delivery is missing or invalid.
6. [ ] (API7-DEL-17) The UI can present a delivery note without requiring storage access.
