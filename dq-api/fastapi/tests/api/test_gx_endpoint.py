from __future__ import annotations

from datetime import UTC, datetime, timedelta
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
import pytest
from fastapi import Response
from fastapi import HTTPException

from app.application.use_cases.execution_queries import build_gx_execution_run_summary
from app.api.v1.endpoints import exception_reports as exception_report_endpoints
from app.api.v1.endpoints import exceptions as exception_endpoints
from app.api.v1.endpoints import execution_monitoring as gx_endpoints
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact
from app.domain.entities.gx_suite import build_gx_artifact_envelope_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_create_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_status_transition_entity
from app.domain.entities.gx_execution_violation import (
    build_gx_execution_violation_entity,
    build_gx_execution_violation_list_entity,
    build_gx_execution_violation_summary_entity,
)
from app.domain.entities import ExceptionRecordCreateEntity
from app.domain.entities.gx_run_plan import build_gx_run_plan_entity
from app.domain.entities.validation_run_plan import build_validation_run_plan_entity_from_gx_run_plan
from app.infrastructure.repositories.in_memory_exception_reason_analytics_projection_repository import InMemoryExceptionReasonAnalyticsProjectionRepository


class _Repo:
    def __init__(self) -> None:
        self.current_user = SimpleNamespace(
            id="user-admin",
            name="Admin User",
            email="admin@example.com",
            granted_scopes=["dq:rules:read"],
            workspace_roles=[],
        )
        self.last_list_kwargs: dict | None = None
        self.last_get_kwargs: dict | None = None
        self.last_save_kwargs: dict | None = None
        self.last_save_violations_kwargs: list[dict] | None = None
        self.last_patch_kwargs: dict | None = None
        self.last_history_kwargs: dict | None = None
        self.last_run_create_kwargs: dict | None = None
        self.last_run_get_kwargs: dict | None = None
        self.last_run_list_kwargs: dict | None = None
        self.last_run_history_kwargs: dict | None = None
        self.last_violation_summary_kwargs: dict | None = None
        self.last_run_plan_create_kwargs: dict | None = None
        self.last_run_plan_list_kwargs: dict | None = None
        self.last_run_plan_activate_kwargs: dict | None = None
        self.last_violation_save_kwargs: dict | None = None
        self.last_reason_analytics_summary_kwargs: dict | None = None
        self._projection_repository = InMemoryExceptionReasonAnalyticsProjectionRepository()
        self._runs: dict[str, dict] = {}
        self._run_plans: dict[str, dict] = {}
        self._violations: dict[tuple[str, str], dict] = {}
        self._transition_events: dict[str, list[dict]] = {}
        self._data_deliveries: list[dict] = [
            {
                "id": "del-31",
                "data_object_id": "do-1",
                "data_object_version_id": "dov_1",
                "version": 1,
                "timestamp": "2026-02-21T15:30:00",
                "delivery_location": "s3a://analytics/do-1/v1/LOAD_DTS=20260221T153000000Z",
            }
        ]
        self.list_payload: list[dict] = [
            {
                "suiteId": "gx_suite_1",
                "suiteVersion": 1,
                "artifactVersion": "v1",
                "assignmentScope": {
                    "dataObjectId": "do_1",
                    "datasetId": None,
                    "dataProductId": None,
                },
                "resolvedExecutionScope": {
                    "dataObjectVersionIds": ["dov_1"],
                },
                "gxSuite": {
                    "expectation_suite_name": "dq_suite",
                    "expectations": [
                        {
                            "expectation_type": "expect_column_values_to_not_be_null",
                            "kwargs": {"column": "order_id"},
                        }
                    ],
                    "meta": {},
                },
                "compiledFrom": {
                    "ruleIds": ["rule_1"],
                    "compilerVersion": "dq-compiler-7.3",
                    "generatedAt": "2026-03-22T10:30:00Z",
                },
                "executionHints": {
                    "recommendedEngine": "pyspark",
                    "primaryKeyFields": ["order_id"],
                },
                "executionContract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "single_object",
                    "traceability": {
                        "ruleId": "rule_1",
                        "ruleVersionId": "rule_version_1",
                        "gxSuiteId": "gx_suite_1",
                        "gxSuiteVersion": 1,
                        "dataObjectVersionId": "dov_1",
                        "sourceRuleExpression": "status = 'ACTIVE'",
                        "compiledExpression": "status = 'ACTIVE'",
                        "artifactKey": "artifact_1",
                    },
                },
            }
        ]
        self.get_payload: dict | None = self.list_payload[0]

    def get_current_user(self, user_id: str | None, claims: dict | None = None):
        _ = user_id
        _ = claims
        return self.current_user

    def get_data_object_version(self, version_id: str):
        if str(version_id) != "dov_1":
            return None
        return SimpleNamespace(id="dov_1", data_object_id="do-1")

    def list_data_sets(self, product_id: str | None = None, workspace: str | None = None):
        _ = product_id
        _ = workspace
        return [SimpleNamespace(id="ds-1", workspace_id="retail-banking")]

    async def get_rule_by_id(self, rule_id: str):
        mapping = {
            "rule_1": SimpleNamespace(id="rule_1", name="Customer Order Completeness"),
            "rule_2": SimpleNamespace(id="rule_2", name="Transfer Match"),
        }
        return mapping.get(rule_id)

    def list_data_objects_catalog(self):
        return [
            SimpleNamespace(id="do-1", name="Orders", dataset_id="ds-1"),
            SimpleNamespace(id="do-2", name="Transfers", dataset_id="ds-2"),
        ]

    def list_data_object_versions(self):
        return [
            SimpleNamespace(id="dov_1", data_object_id="do-1"),
            SimpleNamespace(id="dov_2", data_object_id="do-2"),
        ]

    async def list_suites(self, **kwargs) -> list[dict]:
        self.last_list_kwargs = kwargs
        return [build_gx_artifact_envelope_entity(row) for row in self.list_payload]

    async def list_artifacts(self, **kwargs) -> list[dict]:
        self.last_list_kwargs = kwargs
        return [build_validation_artifact_envelope_from_gx_artifact(row) for row in self.list_payload]

    async def list_suites_for_rule(self, **kwargs) -> list[dict]:
        self.last_list_kwargs = kwargs
        return [build_gx_artifact_envelope_entity(row) for row in self.list_payload]

    async def list_artifacts_for_rule(self, **kwargs) -> list[dict]:
        self.last_list_kwargs = kwargs
        return [build_validation_artifact_envelope_from_gx_artifact(row) for row in self.list_payload]

    def list_data_deliveries(self, version_id: str | None = None) -> list[dict]:
        if version_id is None:
            return list(self._data_deliveries)
        version_selector = str(version_id)
        return [
            row
            for row in self._data_deliveries
            if str(row.get("data_object_version_id") or "") == version_selector or str(row.get("version") or "") == version_selector
        ]

    def get_data_delivery_note(self, delivery_id: str):
        for row in self._data_deliveries:
            if str(row.get("id") or "") != str(delivery_id):
                continue
            return SimpleNamespace(
                id=str(row.get("id") or ""),
                data_delivery_id=str(row.get("id") or ""),
                data_object_id=str(row.get("data_object_id") or ""),
                data_object_version_id=str(row.get("data_object_version_id") or "") or None,
                version=int(row.get("version") or 0),
                timestamp=str(row.get("timestamp") or ""),
                delivery_location=str(row.get("delivery_location") or "") or None,
            )
        return None

    async def get_suite_by_id(self, **kwargs) -> dict | None:
        self.last_get_kwargs = kwargs
        return build_gx_artifact_envelope_entity(self.get_payload) if self.get_payload is not None else None

    async def get_artifact_by_id(self, **kwargs) -> dict | None:
        self.last_get_kwargs = kwargs
        return build_validation_artifact_envelope_from_gx_artifact(self.get_payload) if self.get_payload is not None else None

    async def save_suite(self, **kwargs) -> dict:
        self.last_save_kwargs = kwargs
        if kwargs.get("expected_existing_hash") == "reject":
            raise ValueError("GX suite overwrite conflict: expected hash does not match current artifact")
        envelope = kwargs["envelope"]
        return envelope.model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(envelope, "model_dump") else dict(envelope)

    async def save_artifact(self, **kwargs) -> dict:
        self.last_save_kwargs = kwargs
        if kwargs.get("expected_existing_hash") == "reject":
            raise ValueError("GX suite overwrite conflict: expected hash does not match current artifact")
        envelope = kwargs["envelope"]
        return envelope.model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(envelope, "model_dump") else dict(envelope)

    async def patch_suite_status(self, **kwargs) -> dict | None:
        self.last_patch_kwargs = kwargs
        if kwargs.get("suite_id") == "missing-suite":
            return None
        item = dict(self.get_payload or {})
        item["status"] = kwargs["new_status"]
        return item

    async def patch_artifact_status(self, **kwargs) -> dict | None:
        self.last_patch_kwargs = kwargs
        if kwargs.get("artifact_id") == "missing-suite":
            return None
        item = dict(self.get_payload or {})
        item["status"] = kwargs["new_status"]
        return build_validation_artifact_envelope_from_gx_artifact(item)

    async def list_suite_status_history(self, **kwargs) -> list[dict]:
        self.last_history_kwargs = kwargs
        if kwargs.get("suite_id") == "missing-suite":
            return []
        return [
            {
                "suiteId": kwargs["suite_id"],
                "suiteVersion": 1,
                "fromStatus": None,
                "toStatus": "active",
                "changedBy": "user-1",
                "changedAt": "2026-03-22T10:00:00Z",
                "reason": None,
            },
            {
                "suiteId": kwargs["suite_id"],
                "suiteVersion": 1,
                "fromStatus": "active",
                "toStatus": "deprecated",
                "changedBy": "user-2",
                "changedAt": "2026-03-22T11:00:00Z",
                "reason": "superseded by v2",
            },
        ]

    async def list_artifact_status_history(self, **kwargs) -> list[dict]:
        self.last_history_kwargs = kwargs
        if kwargs.get("artifact_id") == "missing-suite":
            return []
        artifact_id = kwargs.get("artifact_id")
        return [
            {
                "validationArtifactId": artifact_id,
                "validationArtifactVersion": 1,
                "fromStatus": None,
                "toStatus": "active",
                "changedBy": "user-1",
                "changedAt": "2026-03-22T10:00:00Z",
                "reason": None,
            },
            {
                "validationArtifactId": artifact_id,
                "validationArtifactVersion": 1,
                "fromStatus": "active",
                "toStatus": "deprecated",
                "changedBy": "user-2",
                "changedAt": "2026-03-22T11:00:00Z",
                "reason": "superseded by v2",
            },
        ]

    async def create_run(self, run=None, **kwargs) -> dict:
        if run is not None:
            kwargs = run.model_dump(by_alias=True, exclude_none=False)
        self.last_run_create_kwargs = kwargs
        run_id = str(kwargs["run_id"])
        record = {
            "id": run_id,
            "suiteId": kwargs.get("suite_id"),
            "suiteVersion": kwargs.get("suite_version"),
            "ruleId": kwargs.get("rule_id"),
            "ruleVersionId": kwargs.get("rule_version_id"),
            "correlationId": kwargs["correlation_id"],
            "requestedBy": kwargs["requested_by"],
            "engineType": kwargs["engine_type"],
            "engineTarget": kwargs["engine_target"],
            "executionShape": kwargs["execution_shape"],
            "status": kwargs["status"],
            "submittedAt": kwargs["submitted_at"],
            "startedAt": kwargs.get("started_at"),
            "completedAt": kwargs.get("completed_at"),
            "createdAt": kwargs["submitted_at"],
            "updatedAt": kwargs["submitted_at"],
            "executionContract": kwargs["execution_contract"],
            "handoffPayload": kwargs.get("handoff_payload"),
            "resolvedDataDeliveryId": (kwargs["execution_contract"] or {}).get("resolved_data_delivery_id") or (kwargs["execution_contract"] or {}).get("resolvedDataDeliveryId"),
            "runPlanId": (kwargs.get("handoff_payload") or {}).get("run_plan_id") or (kwargs.get("handoff_payload") or {}).get("runPlanId"),
            "runPlanVersionId": (kwargs.get("handoff_payload") or {}).get("run_plan_version_id") or (kwargs.get("handoff_payload") or {}).get("runPlanVersionId"),
            "resultSummary": kwargs.get("result_summary") or {},
            "diagnostics": kwargs.get("diagnostics") or [],
            "failureCode": kwargs.get("failure_code"),
            "failureMessage": kwargs.get("failure_message"),
            "statusHistory": [
                {
                    "id": f"hist-{run_id}",
                    "runId": run_id,
                    "fromStatus": None,
                    "toStatus": kwargs["status"],
                    "changedBy": kwargs["requested_by"],
                    "changedAt": kwargs["submitted_at"],
                    "reason": kwargs.get("status_reason"),
                    "details": kwargs.get("status_details") or {},
                }
            ],
        }
        self._runs[run_id] = record
        return record

    async def get_run(self, run_id: str):
        self.last_run_get_kwargs = {"run_id": run_id}
        run = self._runs.get(str(run_id))
        if run is None:
            return None
        return build_gx_execution_run_entity(run)

    async def list_runs(self, query=None, **kwargs):
        if query is not None:
            if hasattr(query, "model_dump"):
                kwargs = dict(query.model_dump(by_alias=True))
            else:
                kwargs = dict(query)
        self.last_run_list_kwargs = kwargs
        rows = list(self._runs.values())
        submitted_after = kwargs.get("submitted_after")
        submitted_before = kwargs.get("submitted_before")
        suite_id = kwargs.get("suite_id")
        rule_id = kwargs.get("rule_id")
        status = kwargs.get("status")
        filtered = []
        for row in rows:
            submitted_at = datetime.fromisoformat(str(row.get("submittedAt") or row.get("createdAt")).replace("Z", "+00:00"))
            if submitted_after is not None and submitted_at < submitted_after:
                continue
            if submitted_before is not None and submitted_at > submitted_before:
                continue
            if suite_id is not None and row.get("suiteId") != suite_id:
                continue
            if rule_id is not None and row.get("ruleId") != rule_id:
                continue
            if status is not None and row.get("status") != status:
                continue
            filtered.append(build_gx_execution_run_entity(dict(row)))
        filtered.sort(key=lambda item: str(item.submittedAt or ""), reverse=True)
        return filtered
    async def list_run_status_history(self, run_id: str):
        self.last_run_history_kwargs = {"run_id": run_id}
        run = await self.get_run(run_id)
        if run is None:
            return []
        return list(run.statusHistory)

    async def record_run_status_transition(self, transition=None, **kwargs):
        if transition is not None:
            kwargs = transition.model_dump(by_alias=True, exclude_none=False)
        run_id = str(kwargs["run_id"])
        run = self._runs.get(run_id)
        if run is None:
            raise ValueError(f"GX execution run '{run_id}' not found")

        run["status"] = kwargs["new_status"]
        if kwargs.get("started_at") is not None:
            run["startedAt"] = kwargs["started_at"]
        if kwargs.get("completed_at") is not None:
            run["completedAt"] = kwargs["completed_at"]
        if kwargs.get("execution_progress") is not None:
            run["executionProgress"] = kwargs["execution_progress"]
        if kwargs.get("result_summary") is not None:
            run["resultSummary"] = kwargs["result_summary"]
        if kwargs.get("diagnostics") is not None:
            run["diagnostics"] = kwargs["diagnostics"]
        if kwargs.get("failure_code") is not None:
            run["failureCode"] = kwargs["failure_code"]
        if kwargs.get("failure_message") is not None:
            run["failureMessage"] = kwargs["failure_message"]

        run["updatedAt"] = kwargs.get("completed_at") or kwargs.get("started_at") or run["updatedAt"]
        run["statusHistory"].append(
            {
                "id": f"hist-{run_id}-{len(run['statusHistory']) + 1}",
                "runId": run_id,
                "fromStatus": None,
                "toStatus": kwargs["new_status"],
                "changedBy": kwargs.get("changed_by"),
                "changedAt": kwargs.get("completed_at") or kwargs.get("started_at") or run["updatedAt"],
                "reason": kwargs.get("reason"),
                "details": kwargs.get("details") or {},
            }
        )
        run = await self.get_run(run_id)
        assert run is not None
        return run

    async def save_violation(self, **kwargs) -> dict:
        saved = await self.save_violations([kwargs])
        self.last_violation_save_kwargs = kwargs
        return saved[0] if saved else {}

    async def save_violations(self, violations: list[dict]) -> list[dict]:
        self.last_save_violations_kwargs = list(violations)
        saved: list[dict] = []
        projection_records: list[ExceptionRecordCreateEntity] = []
        for kwargs in violations:
            payload = kwargs.model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(kwargs, "model_dump") else dict(kwargs)
            violation_id = str(payload.get("id") or payload.get("violation_id") or f"vio-{len(self._violations) + 1}")
            run_record = self._runs.get(str(payload.get("execution_run_id") or payload.get("executionRunId") or ""))
            run_execution_contract = dict(run_record.get("executionContract") or {}) if isinstance(run_record, dict) else {}
            run_traceability = dict(run_execution_contract.get("traceability") or {}) if isinstance(run_execution_contract.get("traceability"), dict) else {}
            run_handoff_payload = dict(run_record.get("handoffPayload") or {}) if isinstance(run_record, dict) else {}
            run_status_details = dict(run_record.get("statusDetails") or {}) if isinstance(run_record, dict) else {}
            ops_metadata = dict(payload.get("opsMetadata") or payload.get("ops_metadata") or {})
            record = {
                "id": violation_id,
                "dataObjectVersionId": payload.get("dataObjectVersionId") or payload["data_object_version_id"],
                "executionRunId": payload.get("executionRunId") or payload["execution_run_id"],
                "ruleId": payload.get("ruleId") or payload["rule_id"],
                "dataPrimaryKey": payload.get("dataPrimaryKey") or payload["data_primary_key"],
                "violationReason": payload.get("violationReason") or payload["violation_reason"],
                "opsMetadata": payload.get("opsMetadata") or payload.get("ops_metadata") or {},
                "detectedAt": payload.get("detectedAt") or payload.get("detected_at"),
                "createdAt": payload.get("detectedAt") or payload.get("detected_at") or "2026-04-10T08:00:00Z",
                "updatedAt": payload.get("detectedAt") or payload.get("detected_at") or "2026-04-10T08:00:00Z",
            }
            self._violations[(payload.get("data_object_version_id") or payload.get("dataObjectVersionId"), violation_id)] = record
            saved.append(build_gx_execution_violation_entity(record))
            if not ops_metadata.get("validation_artifact_id") and isinstance(run_record, dict):
                ops_metadata["validation_artifact_id"] = run_record.get("suiteId")
            if not ops_metadata.get("validation_artifact_version") and isinstance(run_record, dict):
                ops_metadata["validation_artifact_version"] = run_record.get("suiteVersion")
            if not ops_metadata.get("rule_version_id") and isinstance(run_record, dict):
                ops_metadata["rule_version_id"] = run_record.get("ruleVersionId")
            if not ops_metadata.get("engine_type") and isinstance(run_record, dict):
                ops_metadata["engine_type"] = run_record.get("engineType") or "gx"
            if not ops_metadata.get("delivery_id"):
                ops_metadata["delivery_id"] = run_execution_contract.get("resolvedDataDeliveryId")
            if not ops_metadata.get("execution_plan_id"):
                ops_metadata["execution_plan_id"] = str(run_handoff_payload.get("run_plan_id") or run_status_details.get("run_plan_id") or "") or None
            if not ops_metadata.get("execution_plan_version_id"):
                ops_metadata["execution_plan_version_id"] = str(run_handoff_payload.get("run_plan_version_id") or "") or None
            record_identifier_value = str(ops_metadata.get("record_identifier_value") or payload.get("data_primary_key") or payload.get("dataPrimaryKey") or "").strip()
            record_identifier_type = str(ops_metadata.get("record_identifier_type") or "primary_key").strip() or "primary_key"
            reason_code = str(ops_metadata.get("reason_code") or "").strip()
            reason_text = str(ops_metadata.get("reason_text") or payload.get("violation_reason") or "").strip()
            if not record_identifier_value or not reason_code or not reason_text:
                continue
            data_object_version_id = str(payload.get("data_object_version_id") or payload.get("dataObjectVersionId") or run_traceability.get("dataObjectVersionId") or "").strip()
            execution_run_id = str(payload.get("execution_run_id") or payload.get("executionRunId") or "").strip()
            rule_id = str(payload.get("rule_id") or payload.get("ruleId") or "").strip()
            engine_type = str(ops_metadata.get("engine_type") or "gx").strip() or "gx"
            validation_artifact_id = str(ops_metadata.get("validation_artifact_id") or "").strip()
            if not data_object_version_id or not execution_run_id or not rule_id or not validation_artifact_id:
                continue
            validation_artifact_version = int(ops_metadata.get("validation_artifact_version") or 1)
            projection_records.append(
                ExceptionRecordCreateEntity(
                    id=violation_id,
                    dataObjectVersionId=data_object_version_id,
                    executionRunId=execution_run_id,
                    ruleId=rule_id,
                    recordIdentifierType=record_identifier_type,
                    recordIdentifierValue=record_identifier_value,
                    reasonCode=reason_code,
                    reasonText=reason_text,
                    failureClass=str(ops_metadata.get("failure_class") or "") or None,
                    detectedAt=str(record.get("detectedAt") or "") or None,
                    opsMetadata={
                        **ops_metadata,
                        "validation_artifact_id": validation_artifact_id,
                        "validation_artifact_version": validation_artifact_version,
                        "record_identifier_type": record_identifier_type,
                        "record_identifier_value": record_identifier_value,
                        "engine_type": engine_type,
                    },
                )
            )
        if saved:
            self.last_violation_save_kwargs = violations[-1]
        if projection_records:
            await self._projection_repository.persist_exception_records(projection_records)
        return saved

    async def get_violation(self, data_object_version_id: str, violation_id: str) -> dict | None:
        record = self._violations.get((data_object_version_id, violation_id))
        return build_gx_execution_violation_entity(record) if record is not None else None

    async def list_violations(
        self,
        data_object_version_id: str,
        execution_run_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        rows = [
            row
            for (scope, _), row in self._violations.items()
            if scope == data_object_version_id and (execution_run_id is None or row["executionRunId"] == execution_run_id)
        ]
        rows.sort(key=lambda item: item.get("detectedAt") or "")
        total = len(rows)
        return build_gx_execution_violation_list_entity({"data": rows[offset : offset + limit], "total": total})

    async def summarize_violations(self, **kwargs) -> dict:
        self.last_violation_summary_kwargs = kwargs
        normalized_scope_ids = {str(value).strip() for value in kwargs.get("data_object_version_ids") or [] if str(value).strip()}
        normalized_run_ids = {str(value).strip() for value in kwargs.get("execution_run_ids") or [] if str(value).strip()}
        normalized_reason_codes = {str(value).strip() for value in kwargs.get("reason_codes") or [] if str(value).strip()}
        detected_after = datetime.fromisoformat(str(kwargs.get("detected_after") or "").replace("Z", "+00:00")) if kwargs.get("detected_after") else None
        detected_before = datetime.fromisoformat(str(kwargs.get("detected_before") or "").replace("Z", "+00:00")) if kwargs.get("detected_before") else None
        bucket_origin = datetime.fromisoformat(str(kwargs.get("bucket_origin") or "").replace("Z", "+00:00")) if kwargs.get("bucket_origin") else None
        bucket_size_seconds = int(kwargs.get("bucket_size_seconds") or 0)
        bucket_count = int(kwargs.get("bucket_count") or 0)

        filtered_rows: list[dict] = []
        for (scope, _), row in self._violations.items():
            if scope not in normalized_scope_ids or not row.get("executionRunId"):
                continue
            run_id = str(row.get("executionRunId") or "").strip()
            if run_id not in normalized_run_ids:
                continue
            detected_at = datetime.fromisoformat(str(row.get("detectedAt") or "").replace("Z", "+00:00")) if row.get("detectedAt") else None
            if detected_after is not None and (detected_at is None or detected_at < detected_after):
                continue
            if detected_before is not None and (detected_at is None or detected_at > detected_before):
                continue
            filtered_rows.append(row)

        trend_totals: dict[str, int] = {}
        rule_totals: dict[str, int] = {}
        data_object_totals: dict[str, int] = {}
        reason_totals: dict[tuple[str, str], int] = {}
        reason_trend_totals: dict[tuple[str, str, str], int] = {}
        runs_with_failures: set[str] = set()
        for row in filtered_rows:
            run_id = str(row.get("executionRunId") or "").strip()
            rule_id = str(row.get("ruleId") or "").strip()
            data_object_version_id = str(row.get("dataObjectVersionId") or "").strip()
            ops_metadata = dict(row.get("opsMetadata") or {})
            reason_code = str(ops_metadata.get("reason_code") or "").strip()
            reason_text = str(ops_metadata.get("reason_text") or "").strip()
            if not reason_code or not reason_text:
                raise RuntimeError(
                    "GX exception reason analytics require canonical reason_code and reason_text metadata"
                )
            if normalized_reason_codes and reason_code not in normalized_reason_codes:
                continue
            detected_at = datetime.fromisoformat(str(row.get("detectedAt") or "").replace("Z", "+00:00")) if row.get("detectedAt") else None
            if run_id:
                runs_with_failures.add(run_id)
            if rule_id:
                rule_totals[rule_id] = rule_totals.get(rule_id, 0) + 1
            if data_object_version_id:
                data_object_totals[data_object_version_id] = data_object_totals.get(data_object_version_id, 0) + 1
            reason_key = (reason_code, reason_text)
            reason_totals[reason_key] = reason_totals.get(reason_key, 0) + 1
            if detected_at is not None and bucket_origin is not None and bucket_size_seconds > 0 and bucket_count > 0:
                bucket_index = int((detected_at - bucket_origin).total_seconds() // bucket_size_seconds)
                bucket_index = max(0, min(bucket_count - 1, bucket_index))
                bucket_start = (bucket_origin + timedelta(seconds=bucket_index * bucket_size_seconds)).isoformat()
                trend_totals[bucket_start] = trend_totals.get(bucket_start, 0) + 1
                reason_bucket_key = (bucket_start, reason_code, reason_text)
                reason_trend_totals[reason_bucket_key] = reason_trend_totals.get(reason_bucket_key, 0) + 1

        return build_gx_execution_violation_summary_entity({
            "total_failed_records": sum(reason_totals.values()),
            "runs_with_failures": len(runs_with_failures),
            "trend_totals": [
                {"bucket_start": bucket_start, "total": total}
                for bucket_start, total in sorted(trend_totals.items())
            ],
            "rule_totals": [
                {"rule_id": rule_id, "total": total}
                for rule_id, total in sorted(rule_totals.items(), key=lambda item: (-item[1], item[0]))[:5]
            ],
            "data_object_totals": [
                {"data_object_version_id": data_object_version_id, "total": total}
                for data_object_version_id, total in sorted(data_object_totals.items(), key=lambda item: (-item[1], item[0]))[:5]
            ],
            "reason_totals": [
                {"reason_code": reason_code, "reason_text": reason_text, "total": total}
                for (reason_code, reason_text), total in sorted(reason_totals.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))[:5]
            ],
            "reason_trend_totals": [
                {"bucket_start": bucket_start, "reason_code": reason_code, "reason_text": reason_text, "total": total}
                for (bucket_start, reason_code, reason_text), total in sorted(reason_trend_totals.items(), key=lambda item: (item[0][0], -item[1], item[0][1], item[0][2]))
            ],
        })

    async def persist_exception_records(self, exception_records):
        return await self._projection_repository.persist_exception_records(exception_records)

    async def summarize_reason_analytics(self, **kwargs):
        self.last_reason_analytics_summary_kwargs = kwargs
        return await self._projection_repository.summarize_reason_analytics(**kwargs)

    async def create_plan(self, **kwargs):
        self.last_run_plan_create_kwargs = kwargs
        run_plan_id = str(kwargs["run_plan_id"])
        run_plan_version_id = str(kwargs["run_plan_version_id"])
        scope_selector = kwargs["scope_selector"].model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(kwargs["scope_selector"], "model_dump") else dict(kwargs["scope_selector"])
        if "validation_artifact_selection" in kwargs:
            validation_artifact_selection = kwargs["validation_artifact_selection"]
            gx_suite_selection = {
                "selectionMode": validation_artifact_selection.selectionMode,
                "scopeSelector": validation_artifact_selection.scopeSelector.model_dump(mode="python", by_alias=False, exclude_none=False),
                "suiteRefs": [
                    {"suiteId": item.artifactId, "suiteVersion": item.artifactVersion, "engineType": item.engineType}
                    for item in validation_artifact_selection.artifactRefs
                ],
                "groupedExecutionPlan": (
                    validation_artifact_selection.groupedExecutionPlan.model_dump(mode="python", by_alias=False, exclude_none=False)
                    if validation_artifact_selection.groupedExecutionPlan is not None
                    else None
                ),
            }
        else:
            gx_suite_selection = kwargs["gx_suite_selection"].model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(kwargs["gx_suite_selection"], "model_dump") else dict(kwargs["gx_suite_selection"])
        suite_snapshot_payload = kwargs.get("artifact_snapshot", kwargs.get("suite_snapshot"))
        suite_snapshot = suite_snapshot_payload.model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(suite_snapshot_payload, "model_dump") else dict(suite_snapshot_payload)
        suite_id = kwargs.get("artifact_id", kwargs.get("suite_id"))
        suite_version = kwargs.get("artifact_version", kwargs.get("suite_version"))
        execution_contract_snapshot = kwargs.get("execution_contract_snapshot")
        if hasattr(execution_contract_snapshot, "model_dump"):
            execution_contract_snapshot = execution_contract_snapshot.model_dump(mode="python", by_alias=False, exclude_none=False)
        schedule_definition = kwargs["schedule_definition"].model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(kwargs["schedule_definition"], "model_dump") else dict(kwargs["schedule_definition"])
        plan = {
            "runPlanId": run_plan_id,
            "businessKey": run_plan_id,
            "workspaceId": kwargs["workspace_id"],
            "scopeSelector": scope_selector,
            "planningMode": kwargs["planning_mode"],
            "currentActiveVersionId": None,
            "status": kwargs["status"],
            "createdBy": kwargs.get("created_by"),
            "createdAt": "2026-04-10T08:00:00Z",
            "updatedAt": "2026-04-10T08:00:00Z",
            "activatedBy": None,
            "activatedAt": None,
            "lastDispatchedRunId": None,
            "pendingVersionId": run_plan_version_id,
            "pendingVersionGovernanceState": "draft",
            "versions": [
                {
                    "runPlanVersionId": run_plan_version_id,
                    "runPlanId": run_plan_id,
                    "governanceState": "draft",
                    "gxSuiteSelection": gx_suite_selection,
                    "suiteId": suite_id,
                    "suiteVersion": suite_version,
                    "suiteSnapshot": suite_snapshot,
                    "executionContractSnapshot": execution_contract_snapshot,
                    "scheduleDefinition": schedule_definition,
                    "validationStatus": kwargs.get("validation_status") or "not_requested",
                    "reviewStatus": kwargs.get("review_status"),
                    "effectiveFrom": kwargs.get("effective_from"),
                    "supersedesVersionId": kwargs.get("supersedes_version_id"),
                    "createdBy": kwargs.get("created_by"),
                    "createdAt": "2026-04-10T08:00:00Z",
                }
            ],
        }
        self._transition_events[run_plan_id] = [
            {
                "id": f"{run_plan_id}-event-1",
                "runPlanId": run_plan_id,
                "runPlanVersionId": run_plan_version_id,
                "action": "created",
                "fromState": None,
                "toState": "draft",
                "actorId": kwargs.get("created_by"),
                "correlationId": kwargs.get("correlation_id"),
                "effectiveFrom": kwargs.get("effective_from"),
                "details": {
                    "planning_mode": kwargs.get("planning_mode"),
                    "workspace_id": kwargs.get("workspace_id"),
                    "supersedes_version_id": kwargs.get("supersedes_version_id"),
                },
                "occurredAt": "2026-04-10T08:00:00Z",
            }
        ]
        self._run_plans[run_plan_id] = plan
        plan = await self.get_plan(run_plan_id)
        assert plan is not None
        return plan

    async def get_plan(self, run_plan_id: str):
        plan = self._run_plans.get(run_plan_id)
        if plan is None:
            return None
        return build_validation_run_plan_entity_from_gx_run_plan(
            build_gx_run_plan_entity({**dict(plan), "transitionEvents": list(self._transition_events.get(run_plan_id, []))})
        )

    async def create_plan_version(self, **kwargs):
        plan = self._run_plans.get(kwargs["run_plan_id"])
        if plan is None:
            raise ValueError("plan not found")
        if "validation_artifact_selection" in kwargs:
            validation_artifact_selection = kwargs["validation_artifact_selection"]
            gx_suite_selection = {
                "selectionMode": validation_artifact_selection.selectionMode,
                "scopeSelector": validation_artifact_selection.scopeSelector.model_dump(mode="python", by_alias=False, exclude_none=False),
                "suiteRefs": [
                    {"suiteId": item.artifactId, "suiteVersion": item.artifactVersion, "engineType": item.engineType}
                    for item in validation_artifact_selection.artifactRefs
                ],
                "groupedExecutionPlan": (
                    validation_artifact_selection.groupedExecutionPlan.model_dump(mode="python", by_alias=False, exclude_none=False)
                    if validation_artifact_selection.groupedExecutionPlan is not None
                    else None
                ),
            }
        else:
            gx_suite_selection = kwargs["gx_suite_selection"].model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(kwargs["gx_suite_selection"], "model_dump") else dict(kwargs["gx_suite_selection"])
        suite_snapshot_payload = kwargs.get("artifact_snapshot", kwargs.get("suite_snapshot"))
        suite_snapshot = suite_snapshot_payload.model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(suite_snapshot_payload, "model_dump") else dict(suite_snapshot_payload)
        suite_id = kwargs.get("artifact_id", kwargs.get("suite_id"))
        suite_version = kwargs.get("artifact_version", kwargs.get("suite_version"))
        execution_contract_snapshot = kwargs.get("execution_contract_snapshot")
        if hasattr(execution_contract_snapshot, "model_dump"):
            execution_contract_snapshot = execution_contract_snapshot.model_dump(mode="python", by_alias=False, exclude_none=False)
        schedule_definition = kwargs["schedule_definition"].model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(kwargs["schedule_definition"], "model_dump") else dict(kwargs["schedule_definition"])
        version = {
            "runPlanVersionId": kwargs["run_plan_version_id"],
            "runPlanId": kwargs["run_plan_id"],
            "governanceState": "draft",
            "gxSuiteSelection": gx_suite_selection,
            "suiteId": suite_id,
            "suiteVersion": suite_version,
            "suiteSnapshot": suite_snapshot,
            "executionContractSnapshot": execution_contract_snapshot,
            "scheduleDefinition": schedule_definition,
            "validationStatus": kwargs.get("validation_status") or "not_requested",
            "reviewStatus": kwargs.get("review_status"),
            "effectiveFrom": kwargs.get("effective_from"),
            "supersedesVersionId": kwargs.get("supersedes_version_id"),
            "createdBy": kwargs.get("created_by"),
            "createdAt": "2026-04-10T08:03:00Z",
        }
        plan["versions"].append(version)
        plan["updatedAt"] = "2026-04-10T08:03:00Z"
        if plan.get("currentActiveVersionId") is None:
            plan["status"] = "draft"
        plan["pendingVersionId"] = version["runPlanVersionId"]
        plan["pendingVersionGovernanceState"] = "draft"
        self._transition_events.setdefault(kwargs["run_plan_id"], []).append(
            {
                "id": f"{kwargs['run_plan_id']}-event-{len(self._transition_events.get(kwargs['run_plan_id'], [])) + 1}",
                "runPlanId": kwargs["run_plan_id"],
                "runPlanVersionId": kwargs["run_plan_version_id"],
                "action": "version_created",
                "fromState": None,
                "toState": "draft",
                "actorId": kwargs.get("created_by"),
                "correlationId": kwargs.get("correlation_id"),
                "effectiveFrom": kwargs.get("effective_from"),
                "details": {"supersedes_version_id": kwargs.get("supersedes_version_id")},
                "occurredAt": "2026-04-10T08:03:00Z",
            }
        )
        plan = await self.get_plan(kwargs["run_plan_id"])
        assert plan is not None
        return plan

    async def list_plans(self, **kwargs):
        self.last_run_plan_list_kwargs = kwargs
        rows = []
        for plan in self._run_plans.values():
            if kwargs.get("workspace_id") and plan["workspaceId"] != kwargs["workspace_id"]:
                continue
            if kwargs.get("business_key") and plan.get("businessKey") != kwargs["business_key"]:
                continue
            if kwargs.get("status") and plan["status"] != kwargs["status"]:
                continue
            artifact_id = kwargs.get("artifact_id", kwargs.get("suite_id"))
            if artifact_id and not any(version["suiteId"] == artifact_id for version in plan["versions"]):
                continue
            rows.append(
                build_validation_run_plan_entity_from_gx_run_plan(
                    build_gx_run_plan_entity({**dict(plan), "transitionEvents": list(self._transition_events.get(plan["runPlanId"], []))})
                )
            )
        return rows

    async def transition_plan_version(self, **kwargs):
        plan = self._run_plans.get(kwargs["run_plan_id"])
        if plan is None:
            raise ValueError("plan not found")
        version = next(
            (item for item in plan["versions"] if item["runPlanVersionId"] == kwargs["run_plan_version_id"]),
            None,
        )
        if version is None:
            raise ValueError("version not found")

        target_state = kwargs["target_state"]
        current_state = version["governanceState"]
        if target_state == "pending_validation":
            version["governanceState"] = "pending_validation"
            version["validationStatus"] = "pending"
            version["reviewStatus"] = None
        elif target_state == "validation_failed":
            version["governanceState"] = "validation_failed"
            version["validationStatus"] = "failed"
            version["reviewStatus"] = None
        elif target_state == "pending_review":
            version["governanceState"] = "pending_review"
            version["validationStatus"] = "passed"
            version["reviewStatus"] = "pending"
        elif target_state == "approved_pending_activation":
            version["governanceState"] = "approved_pending_activation"
            version["validationStatus"] = "passed"
            version["reviewStatus"] = "approved"
            if kwargs.get("effective_from"):
                version["effectiveFrom"] = kwargs["effective_from"]
        elif target_state in {"activation-requested", "deactivation-requested"}:
            version["governanceState"] = target_state
        elif target_state == "cancelled":
            version["governanceState"] = "cancelled"
            version["reviewStatus"] = "cancelled"
        plan["status"] = "active" if plan["currentActiveVersionId"] is not None else target_state
        plan["updatedAt"] = "2026-04-10T08:04:00Z"
        plan["pendingVersionId"] = version["runPlanVersionId"] if version["governanceState"] != "active" else None
        plan["pendingVersionGovernanceState"] = version["governanceState"] if version["governanceState"] != "active" else None
        self._transition_events.setdefault(kwargs["run_plan_id"], []).append(
            {
                "id": f"{kwargs['run_plan_id']}-event-{len(self._transition_events.get(kwargs['run_plan_id'], [])) + 1}",
                "runPlanId": kwargs["run_plan_id"],
                "runPlanVersionId": kwargs["run_plan_version_id"],
                "action": "transitioned",
                "fromState": current_state,
                "toState": target_state,
                "actorId": kwargs.get("updated_by"),
                "correlationId": kwargs.get("correlation_id"),
                "effectiveFrom": kwargs.get("effective_from"),
                "details": {"target_state": target_state},
                "occurredAt": "2026-04-10T08:04:00Z",
            }
        )
        plan = await self.get_plan(kwargs["run_plan_id"])
        assert plan is not None
        return plan

    async def activate_plan(self, **kwargs):
        self.last_run_plan_activate_kwargs = kwargs
        plan = self._run_plans.get(kwargs["run_plan_id"])
        if plan is None:
            raise ValueError("plan not found")
        previous_active_version_id = plan["currentActiveVersionId"]
        if previous_active_version_id and previous_active_version_id != kwargs["run_plan_version_id"]:
            for version in plan["versions"]:
                if version["runPlanVersionId"] == previous_active_version_id:
                    version["governanceState"] = "superseded"
                    version["reviewStatus"] = "superseded"
                    self._transition_events.setdefault(kwargs["run_plan_id"], []).append(
                        {
                            "id": f"{kwargs['run_plan_id']}-event-{len(self._transition_events.get(kwargs['run_plan_id'], [])) + 1}",
                            "runPlanId": kwargs["run_plan_id"],
                            "runPlanVersionId": previous_active_version_id,
                            "action": "superseded",
                            "fromState": "active",
                            "toState": "superseded",
                            "actorId": kwargs.get("activated_by"),
                            "correlationId": kwargs.get("correlation_id"),
                            "effectiveFrom": None,
                            "details": {"superseded_by": kwargs["run_plan_version_id"]},
                            "occurredAt": "2026-04-10T08:05:00Z",
                        }
                    )
        plan["status"] = "active"
        plan["currentActiveVersionId"] = kwargs["run_plan_version_id"]
        plan["activatedBy"] = kwargs.get("activated_by")
        plan["activatedAt"] = "2026-04-10T08:05:00Z"
        plan["lastDispatchedRunId"] = kwargs.get("dispatched_run_id")
        plan["updatedAt"] = "2026-04-10T08:05:00Z"
        plan["pendingVersionId"] = None
        plan["pendingVersionGovernanceState"] = None
        for version in plan["versions"]:
            if version["runPlanVersionId"] == kwargs["run_plan_version_id"]:
                version["governanceState"] = "active"
        self._transition_events.setdefault(kwargs["run_plan_id"], []).append(
            {
                "id": f"{kwargs['run_plan_id']}-event-{len(self._transition_events.get(kwargs['run_plan_id'], [])) + 1}",
                "runPlanId": kwargs["run_plan_id"],
                "runPlanVersionId": kwargs["run_plan_version_id"],
                "action": "activated",
                "fromState": "approved_pending_activation",
                "toState": "active",
                "actorId": kwargs.get("activated_by"),
                "correlationId": kwargs.get("correlation_id"),
                "effectiveFrom": None,
                "details": {"dispatched_run_id": kwargs.get("dispatched_run_id")},
                "occurredAt": "2026-04-10T08:05:00Z",
            }
        )
        plan = await self.get_plan(kwargs["run_plan_id"])
        assert plan is not None
        return plan


class _AppConfigRepo:
    def __init__(self, **kwargs: Any) -> None:
        self._config = SimpleNamespace(**kwargs)

    def get_app_config(self) -> SimpleNamespace:
        return self._config


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.is_success = 200 <= status_code < 300
        self.reason_phrase = "OK" if self.is_success else "Error"
        self.text = payload if isinstance(payload, str) else str(payload)

    def json(self) -> Any:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, posts: list[tuple[str, Any, dict[str, str]]], response: _FakeResponse) -> None:
        self._posts = posts
        self._response = response

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def post(self, url: str, json: Any, headers: dict[str, str] | None = None) -> _FakeResponse:
        self._posts.append((url, json, headers or {}))
        return self._response


def _request(user_id: str = "user-admin", *, correlation_id: str | None = None) -> SimpleNamespace:
    headers = {"X-Correlation-ID": correlation_id} if correlation_id else {}
    return SimpleNamespace(headers=headers, state=SimpleNamespace(user_id=user_id, auth_claims={}))


def _patch_gx_redis_url(monkeypatch: pytest.MonkeyPatch, redis_url: str | None) -> None:
    monkeypatch.setattr(gx_endpoints.gx_queue_service, "resolve_redis_url", lambda settings: redis_url)
    if redis_url is not None:
        monkeypatch.setattr(
            gx_endpoints._gx_runtime_api,
            "resolve_execution_queue_key",
            lambda: "dq-gx:execution-dispatch",
        )
        monkeypatch.setattr(
            gx_endpoints._gx_runtime_api,
            "resolve_join_pair_materialization_queue_key",
            lambda: "dq-gx:join-pair-materialize",
        )


def _patch_gx_worker_heartbeat(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    async def _patched(
        redis_url: str,
        *,
        queue_key: str,
        heartbeat_key: str,
        expected_ttl_seconds: int,
        unavailable_error: str,
        unavailable_message: str,
        status_failed_error: str,
        status_failed_message: str,
        async_redis_module,
        sync_redis_module,
        logger,
    ) -> None:
        await handler(redis_url, queue_key)

    monkeypatch.setattr(gx_endpoints.gx_queue_service, "assert_worker_heartbeat", _patched)


def _patch_gx_redis_lpush(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    async def _patched(redis_url: str, queue_key: str, payload: dict, **kwargs) -> None:
        await handler(redis_url, queue_key, payload)

    monkeypatch.setattr(gx_endpoints.gx_queue_service, "redis_lpush", _patched)


@pytest.mark.anyio
async def test_list_gx_suites_by_data_object() -> None:
    repo = _Repo()

    out = await gx_endpoints.list_gx_suites(
        data_object_id="do_1",
        data_object_version_id=None,
        dataset_id=None,
        data_product_id=None,
        status="active",
        latest_only=True,
        repository=repo,
    )

    assert len(out) == 1
    assert out[0].suiteId == "gx_suite_1"
    assert repo.last_list_kwargs == {
        "data_object_id": "do_1",
        "data_object_version_id": None,
        "dataset_id": None,
        "data_product_id": None,
        "status": "active",
        "latest_only": True,
    }


@pytest.mark.anyio
async def test_list_gx_suites_by_data_object_version() -> None:
    repo = _Repo()

    out = await gx_endpoints.list_gx_suites(
        data_object_id=None,
        data_object_version_id="dov_1",
        dataset_id=None,
        data_product_id=None,
        status="deprecated",
        latest_only=False,
        repository=repo,
    )

    assert len(out) == 1
    assert out[0].resolvedExecutionScope.dataObjectVersionIds == ["dov_1"]
    assert repo.last_list_kwargs == {
        "data_object_id": None,
        "data_object_version_id": "dov_1",
        "dataset_id": None,
        "data_product_id": None,
        "status": "deprecated",
        "latest_only": False,
    }


@pytest.mark.anyio
async def test_list_gx_suites_by_rule_id() -> None:
    repo = _Repo()

    out = await gx_endpoints.list_gx_suites_for_rule(
        rule_id="rule_1",
        status="active",
        latest_only=True,
        repository=repo,
    )

    assert len(out) == 1
    assert out[0].suiteId == "gx_suite_1"
    assert repo.last_list_kwargs == {
        "rule_id": "rule_1",
        "status": "active",
        "latest_only": True,
    }


@pytest.mark.anyio
async def test_adhoc_runs_requires_selector(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={})

    async def _worker_available(redis_url: str, queue_key: str) -> None:
        return None

    _patch_gx_redis_url(monkeypatch, "redis://example")
    _patch_gx_worker_heartbeat(monkeypatch, _worker_available)

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.create_adhoc_gx_suite_runs(
            request=request,
            request_body=gx_endpoints.GxAdhocSuiteRunsRequestView.model_validate({}),
            repository=repo,
            execution_run_repository=repo,
        )

    assert error.value.status_code == 422
    assert isinstance(error.value.detail, dict)
    assert error.value.detail["error"] == "missing_selector"


@pytest.mark.anyio
async def test_adhoc_runs_enqueues_dispatch_with_overrides(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={"X-Correlation-ID": "corr-adhoc-1"})
    captured: list[dict] = []

    async def _fake_redis_lpush(redis_url: str, queue_key: str, payload: dict) -> None:
        captured.append({"redis_url": redis_url, "queue_key": queue_key, "payload": payload})

    async def _worker_available(redis_url: str, queue_key: str) -> None:
        return None

    _patch_gx_redis_url(monkeypatch, "redis://example")
    _patch_gx_redis_lpush(monkeypatch, _fake_redis_lpush)
    _patch_gx_worker_heartbeat(monkeypatch, _worker_available)
    monkeypatch.setattr(gx_endpoints, "get_data_catalog_repository", lambda: repo)

    body = gx_endpoints.GxAdhocSuiteRunsRequestView.model_validate(
        {
            "data_object_version_id": "dov_1",
            "rule_ids": ["rule_1"],
            "target_data_object_version_ids": ["dov_1"],
            "source_override_uri": "s3a://dq-test-data/data_object_version_id=dov_1/attr_hash=all/sample_count=1000/format=parquet",
            "source_override_format": "parquet",
        }
    )

    out = await gx_endpoints.create_adhoc_gx_suite_runs(
        request=request,
        request_body=body,
        repository=repo,
        execution_run_repository=repo,
    )

    assert len(out) == 1
    assert out[0].suiteId == "gx_suite_1"
    assert isinstance(out[0].runId, str)
    assert out[0].runId
    assert captured
    dispatched = captured[0]["payload"]
    assert dispatched["correlation_id"] == "corr-adhoc-1"
    assert dispatched.get("execution_scope_override") == ["dov_1"]
    assert "source_overrides_by_data_object_version_id" in dispatched
    assert dispatched["source_overrides_by_data_object_version_id"]["dov_1"]["format"] == "parquet"


@pytest.mark.anyio
async def test_adhoc_join_pair_runs_enqueue_materialization_handoff(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={"X-Correlation-ID": "corr-join-etl-1"})
    captured: list[dict] = []
    join_pair_suite = {
        **repo.list_payload[0],
        "executionContract": {
            "engineType": "gx",
            "engineTarget": "pyspark",
            "executionShape": "join_pair",
            "traceability": {
                "ruleId": "rule_1",
                "ruleVersionId": "rule_version_1",
                "gxSuiteId": "gx_suite_1",
                "gxSuiteVersion": 1,
                "dataObjectVersionId": "dov_1",
            },
            "sourceMaterialization": {
                "landingZoneArtifactId": "lz_gx_suite_1",
                "landingZoneVersionId": "lzv_1",
                "outputLocation": "s3://dq-landing-zone-retail-banking/gx/join-pairs/suite_id=gx_suite_1/suite_version=1/format=parquet",
                "joinType": "inner",
                "joinKeys": ["order_id"],
                "joinKeyPairs": [{"leftAttribute": "order_id", "rightAttribute": "order_id"}],
                "leftSource": {"dataObjectId": "do-left", "dataObjectVersionId": "dov_1", "datasetId": "ds-left"},
                "rightSource": {"dataObjectId": "do-right", "dataObjectVersionId": "dov_2", "datasetId": "ds-right"},
            },
        },
        "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1", "dov_2"]},
    }
    repo.list_payload = [join_pair_suite]

    async def _fake_redis_lpush(redis_url: str, queue_key: str, payload: dict) -> None:
        captured.append({"redis_url": redis_url, "queue_key": queue_key, "payload": payload})

    async def _worker_available(redis_url: str, queue_key: str) -> None:
        return None

    _patch_gx_redis_url(monkeypatch, "redis://example")
    _patch_gx_redis_lpush(monkeypatch, _fake_redis_lpush)
    _patch_gx_worker_heartbeat(monkeypatch, _worker_available)
    monkeypatch.setattr(gx_endpoints, "get_data_catalog_repository", lambda: repo)

    out = await gx_endpoints.create_adhoc_gx_suite_runs(
        request=request,
        request_body=gx_endpoints.GxAdhocSuiteRunsRequestView.model_validate(
            {
                "data_object_version_id": "dov_1",
                "target_data_object_version_ids": ["dov_1"],
            }
        ),
        repository=repo,
        execution_run_repository=repo,
    )

    assert len(out) == 1
    assert out[0].queueKey == "dq-gx:join-pair-materialize"
    assert captured[0]["queue_key"] == "dq-gx:join-pair-materialize"
    assert captured[0]["payload"]["next_dispatch_payload"]["queue_key"] == "dq-gx:execution-dispatch"
    assert repo.last_run_create_kwargs is not None
    assert repo.last_run_create_kwargs["handoff_payload"]["queue_key"] == "dq-gx:join-pair-materialize"
    assert repo.last_run_create_kwargs["status_details"]["pre_dispatch_phase"] == "join_pair_materialization"
    assert repo.last_run_create_kwargs["handoff_payload"]["status_details"]["pre_dispatch_phase"] == "join_pair_materialization"


@pytest.mark.anyio
async def test_create_gx_run_plan_creates_draft_snapshot() -> None:
    repo = _Repo()

    out = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    assert out.status == "draft"
    assert out.businessKey == out.runPlanId
    assert out.workspaceId == "retail-banking"
    assert out.versions[0].governanceState == "draft"
    assert out.versions[0].suiteId == "gx_suite_1"
    assert out.versions[0].scheduleDefinition.scheduledAt == "2026-04-10T10:30:00+00:00"
    assert [event.action for event in out.transitionEvents] == ["created"]
    assert repo.last_run_plan_create_kwargs is not None


@pytest.mark.anyio
async def test_create_gx_run_plan_records_gx_telemetry(monkeypatch) -> None:
    repo = _Repo()
    captured: list[dict[str, object]] = []

    def _record(*, surface: str, operation: str, result: str, status_code: int, duration_ms: float, engine_target=None, execution_shape=None) -> None:
        captured.append(
            {
                "surface": surface,
                "operation": operation,
                "result": result,
                "status_code": status_code,
                "duration_ms": duration_ms,
            }
        )

    monkeypatch.setattr(gx_endpoints, "record_gx_operation_metric", _record)

    await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    assert captured
    assert captured[0]["surface"] == "gx_api"
    assert captured[0]["operation"] == "create_run_plan"
    assert captured[0]["result"] == "succeeded"
    assert captured[0]["status_code"] == 201


@pytest.mark.anyio
async def test_list_gx_run_plans_filters_by_workspace() -> None:
    repo = _Repo()
    await repo.create_plan(
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-1",
        workspace_id="retail-banking",
        scope_selector={"assignmentScope": {"dataObjectId": "do_1"}, "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1"]}},
        planning_mode="single_suite",
        status="draft",
        created_by="user-1",
        gx_suite_selection={"selectionMode": "single_suite", "suiteId": "gx_suite_1", "suiteVersion": 1},
        suite_id="gx_suite_1",
        suite_version=1,
        suite_snapshot=repo.get_payload,
        execution_contract_snapshot=repo.get_payload["executionContract"],
        schedule_definition={"scheduledAt": "2026-04-10T10:30:00Z"},
    )
    await repo.create_plan(
        run_plan_id="run-plan-2",
        run_plan_version_id="run-plan-version-2",
        workspace_id="payments",
        scope_selector={"assignmentScope": {"dataObjectId": "do_1"}, "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1"]}},
        planning_mode="single_suite",
        status="draft",
        created_by="user-1",
        gx_suite_selection={"selectionMode": "single_suite", "suiteId": "gx_suite_1", "suiteVersion": 1},
        suite_id="gx_suite_1",
        suite_version=1,
        suite_snapshot=repo.get_payload,
        execution_contract_snapshot=repo.get_payload["executionContract"],
        schedule_definition={"scheduledAt": "2026-04-10T10:30:00Z"},
    )

    out = await gx_endpoints.list_gx_run_plans(
        workspace_id="retail-banking",
        business_key=None,
        suite_id=None,
        status=None,
        repository=repo,
    )

    assert [item.runPlanId for item in out] == ["run-plan-1"]
    assert [item.businessKey for item in out] == ["run-plan-1"]
    assert repo.last_run_plan_list_kwargs == {"workspace_id": "retail-banking", "business_key": None, "status": None, "artifact_id": None}


@pytest.mark.anyio
async def test_list_gx_run_plans_filters_by_business_key() -> None:
    repo = _Repo()
    await repo.create_plan(
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-1",
        workspace_id="retail-banking",
        scope_selector={"assignmentScope": {"dataObjectId": "do_1"}, "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1"]}},
        planning_mode="single_suite",
        status="draft",
        created_by="user-1",
        gx_suite_selection={"selectionMode": "single_suite", "suiteId": "gx_suite_1", "suiteVersion": 1},
        suite_id="gx_suite_1",
        suite_version=1,
        suite_snapshot=repo.get_payload,
        execution_contract_snapshot=repo.get_payload["executionContract"],
        schedule_definition={"scheduledAt": "2026-04-10T10:30:00Z"},
    )
    await repo.create_plan(
        run_plan_id="run-plan-2",
        run_plan_version_id="run-plan-version-2",
        workspace_id="payments",
        scope_selector={"assignmentScope": {"dataObjectId": "do_1"}, "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1"]}},
        planning_mode="single_suite",
        status="draft",
        created_by="user-1",
        gx_suite_selection={"selectionMode": "single_suite", "suiteId": "gx_suite_1", "suiteVersion": 1},
        suite_id="gx_suite_1",
        suite_version=1,
        suite_snapshot=repo.get_payload,
        execution_contract_snapshot=repo.get_payload["executionContract"],
        schedule_definition={"scheduledAt": "2026-04-10T10:30:00Z"},
    )

    out = await gx_endpoints.list_gx_run_plans(
        workspace_id=None,
        business_key="run-plan-2",
        suite_id=None,
        status=None,
        repository=repo,
    )

    assert [item.runPlanId for item in out] == ["run-plan-2"]
    assert [item.businessKey for item in out] == ["run-plan-2"]
    assert repo.last_run_plan_list_kwargs == {"workspace_id": None, "business_key": "run-plan-2", "status": None, "artifact_id": None}


@pytest.mark.anyio
async def test_get_gx_run_plan_returns_detail() -> None:
    repo = _Repo()
    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    out = await gx_endpoints.get_gx_run_plan(created.runPlanId, repository=repo)

    assert out.runPlanId == created.runPlanId
    assert out.businessKey == created.businessKey
    assert len(out.versions) == 1


@pytest.mark.anyio
async def test_get_gx_run_plan_not_found_records_gx_failure(monkeypatch) -> None:
    repo = _Repo()
    op_calls: list[dict[str, object]] = []
    failure_calls: list[dict[str, object]] = []

    def _record(*, surface: str, operation: str, result: str, status_code: int, duration_ms: float, engine_target=None, execution_shape=None) -> None:
        op_calls.append(
            {
                "surface": surface,
                "operation": operation,
                "result": result,
                "status_code": status_code,
            }
        )

    def _increment(*, surface: str, operation: str, reason: str) -> None:
        failure_calls.append(
            {
                "surface": surface,
                "operation": operation,
                "reason": reason,
            }
        )

    monkeypatch.setattr(gx_endpoints, "record_gx_operation_metric", _record)
    monkeypatch.setattr(gx_endpoints, "increment_gx_failure", _increment)

    with pytest.raises(HTTPException, match="not found"):
        await gx_endpoints.get_gx_run_plan("missing-run-plan", repository=repo)

    assert failure_calls == [{"surface": "gx_api", "operation": "get_run_plan", "reason": "run_plan_not_found"}]
    assert op_calls == [{"surface": "gx_api", "operation": "get_run_plan", "result": "failed", "status_code": 404}]


@pytest.mark.anyio
async def test_create_gx_run_plan_version_appends_new_draft_version() -> None:
    repo = _Repo()
    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    out = await gx_endpoints.create_gx_run_plan_version(
        run_plan_id=created.runPlanId,
        request_body=gx_endpoints.GxRunPlanVersionCreateRequestView.model_validate(
            {
                "suite_id": "gx_suite_1",
                "suite_version": 2,
                "scheduled_at": "2026-04-11T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    assert out.status == "draft"
    assert len(out.versions) == 2
    assert out.pendingVersionGovernanceState == "draft"
    assert out.versions[-1].scheduleDefinition.scheduledAt == "2026-04-11T10:30:00+00:00"
    assert out.versions[-1].supersedesVersionId == created.versions[0].runPlanVersionId


@pytest.mark.anyio
async def test_list_gx_run_plans_filters_by_suite() -> None:
    repo = _Repo()
    await repo.create_plan(
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-1",
        workspace_id="retail-banking",
        scope_selector={"assignmentScope": {"dataObjectId": "do_1"}, "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1"]}},
        planning_mode="single_suite",
        status="draft",
        created_by="user-1",
        gx_suite_selection={"selectionMode": "single_suite", "suiteId": "gx_suite_1", "suiteVersion": 1},
        suite_id="gx_suite_1",
        suite_version=1,
        suite_snapshot=repo.get_payload,
        execution_contract_snapshot=repo.get_payload["executionContract"],
        schedule_definition={"scheduledAt": "2026-04-10T10:30:00Z"},
    )
    await repo.create_plan(
        run_plan_id="run-plan-2",
        run_plan_version_id="run-plan-version-2",
        workspace_id="retail-banking",
        scope_selector={"assignmentScope": {"dataObjectId": "do_1"}, "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1"]}},
        planning_mode="single_suite",
        status="draft",
        created_by="user-1",
        gx_suite_selection={"selectionMode": "single_suite", "suiteId": "gx_suite_other", "suiteVersion": 1},
        suite_id="gx_suite_other",
        suite_version=1,
        suite_snapshot={**repo.get_payload, "suiteId": "gx_suite_other"},
        execution_contract_snapshot=repo.get_payload["executionContract"],
        schedule_definition={"scheduledAt": "2026-04-10T10:30:00Z"},
    )

    out = await gx_endpoints.list_gx_run_plans(
        workspace_id="retail-banking",
        business_key=None,
        suite_id="gx_suite_1",
        status=None,
        repository=repo,
    )

    assert [item.runPlanId for item in out] == ["run-plan-1"]


@pytest.mark.anyio
async def test_activate_gx_run_plan_version_schedules_dispatch(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={"X-Correlation-ID": "corr-plan-1"})
    captured: list[dict] = []

    async def _fake_redis_lpush(redis_url: str, queue_key: str, payload: dict) -> None:
        captured.append({"redis_url": redis_url, "queue_key": queue_key, "payload": payload})

    async def _worker_available(redis_url: str, queue_key: str) -> None:
        return None

    _patch_gx_redis_url(monkeypatch, "redis://example")
    _patch_gx_redis_lpush(monkeypatch, _fake_redis_lpush)
    _patch_gx_worker_heartbeat(monkeypatch, _worker_available)
    monkeypatch.setattr(gx_endpoints, "get_data_catalog_repository", lambda: repo)

    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    transitioned = await gx_endpoints.transition_gx_run_plan_version_governance_state(
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({
            "target_state": "pending_validation",
        }),
        run_plan_repository=repo,
    )
    transitioned = await gx_endpoints.transition_gx_run_plan_version_governance_state(
        run_plan_id=transitioned.runPlanId,
        run_plan_version_id=transitioned.versions[0].runPlanVersionId,
        request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({
            "target_state": "pending_review",
        }),
        run_plan_repository=repo,
    )
    transitioned = await gx_endpoints.transition_gx_run_plan_version_governance_state(
        run_plan_id=transitioned.runPlanId,
        run_plan_version_id=transitioned.versions[0].runPlanVersionId,
        request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({
            "target_state": "approved_pending_activation",
        }),
        run_plan_repository=repo,
    )

    out = await gx_endpoints.activate_gx_run_plan_version(
        request=request,
        run_plan_id=transitioned.runPlanId,
        run_plan_version_id=transitioned.versions[0].runPlanVersionId,
        run_plan_repository=repo,
        execution_run_repository=repo,
    )

    assert out.plan.status == "active"
    assert out.plan.currentActiveVersionId == created.versions[0].runPlanVersionId
    assert out.dispatch["correlation_id"] == "corr-plan-1"
    assert out.dispatch["engine_type"] == "gx"
    assert out.plan.lastDispatchedRunId == out.dispatch["queue_message_id"]
    assert out.plan.transitionEvents[-1].action == "activated"
    assert repo.last_run_create_kwargs is not None
    assert repo.last_run_create_kwargs["engine_type"] == "gx"
    assert repo.last_run_create_kwargs["execution_contract"]["engine_type"] == "gx"
    assert captured
    assert captured[0]["payload"]["engine_type"] == "gx"

@pytest.mark.anyio
async def test_transition_run_plan_version_governance_states() -> None:
    repo = _Repo()
    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    pending_validation = await gx_endpoints.transition_gx_run_plan_version_governance_state(
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({"target_state": "pending_validation"}),
        run_plan_repository=repo,
    )
    assert pending_validation.status == "pending_validation"
    assert pending_validation.versions[0].governanceState == "pending_validation"

    pending_review = await gx_endpoints.transition_gx_run_plan_version_governance_state(
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({"target_state": "pending_review"}),
        run_plan_repository=repo,
    )
    assert pending_review.status == "pending_review"
    assert pending_review.versions[0].governanceState == "pending_review"

    approved = await gx_endpoints.transition_gx_run_plan_version_governance_state(
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({"target_state": "approved_pending_activation"}),
        run_plan_repository=repo,
    )
    assert approved.status == "approved_pending_activation"
    assert approved.versions[0].governanceState == "approved_pending_activation"
    assert approved.transitionEvents[-1].action == "transitioned"


@pytest.mark.anyio
async def test_validate_run_plan_version_updates_status_to_pending_review() -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={})

    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    validated = await gx_endpoints.validate_gx_run_plan_version(
        request=request,
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        run_plan_repository=repo,
    )

    assert validated.validationStatus == "passed"
    assert validated.plan.versions[0].governanceState == "pending_review"
    assert validated.plan.versions[0].validationStatus == "passed"
    assert validated.plan.versions[0].reviewStatus == "pending"
    assert "Review is now pending" in validated.message


@pytest.mark.anyio
async def test_validate_run_plan_version_rejects_malformed_suite_snapshot() -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={})

    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    repo._run_plans[created.runPlanId]["versions"][0]["suiteSnapshot"] = {
        "suiteId": "gx-inventory",
        "suiteVersion": 1,
        "dataObjectVersionId": "dov-24",
    }

    validated = await gx_endpoints.validate_gx_run_plan_version(
        request=request,
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        run_plan_repository=repo,
    )

    assert validated.validationStatus == "failed"
    assert validated.plan.versions[0].governanceState == "validation_failed"
    assert validated.plan.versions[0].validationStatus == "failed"
    assert validated.plan.versions[0].reviewStatus is None
    assert validated.diagnostics[0].code == "invalid_suite_snapshot"
    assert "invalid suite snapshot" in validated.message.lower()


@pytest.mark.anyio
async def test_validate_run_plan_version_rejects_missing_execution_contract_snapshot() -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={})

    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    repo._run_plans[created.runPlanId]["versions"][0]["executionContractSnapshot"] = None

    validated = await gx_endpoints.validate_gx_run_plan_version(
        request=request,
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        run_plan_repository=repo,
    )

    assert validated.validationStatus == "failed"
    assert validated.plan.versions[0].governanceState == "validation_failed"
    assert validated.diagnostics[0].code == "missing_execution_contract_snapshot"
    assert "execution contract snapshot" in validated.message.lower()


@pytest.mark.anyio
async def test_validate_grouped_scope_run_plan_version_rejects_invalid_grouped_suite_snapshot() -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={})

    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "planning_mode": "grouped_scope",
                "data_object_version_id": "dov_1",
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
        grouped_execution_planner=gx_endpoints.GroupedExecutionPlanner(),
    )

    repo._run_plans[created.runPlanId]["versions"][0]["suiteSnapshot"] = {
        "groupedExecutionPlan": {"suiteCount": 1, "batchCount": 1},
        "suiteEnvelopes": [
            {
                "suiteId": "gx-invalid",
                "suiteVersion": 1,
            }
        ],
    }
    repo._run_plans[created.runPlanId]["versions"][0]["executionContractSnapshot"] = {
        "engineTarget": "pyspark",
        "executionShape": "grouped_scope",
        "traceability": {
            "ruleId": "rule_1",
            "ruleVersionId": "rule_version_1",
            "gxSuiteId": "gx_suite_1",
            "gxSuiteVersion": 1,
        },
    }

    validated = await gx_endpoints.validate_gx_run_plan_version(
        request=request,
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        run_plan_repository=repo,
    )

    assert validated.validationStatus == "failed"
    assert validated.plan.versions[0].governanceState == "validation_failed"
    assert validated.diagnostics[0].code == "invalid_grouped_suite_snapshot"
    assert "grouped suite snapshot" in validated.message.lower()


@pytest.mark.anyio
async def test_activate_run_plan_version_rejects_malformed_suite_snapshot() -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={})

    async def _fake_redis_lpush(redis_url: str, queue_key: str, payload: dict) -> None:
        return None

    async def _worker_available(redis_url: str, queue_key: str) -> None:
        return None

    monkeypatch = pytest.MonkeyPatch()
    _patch_gx_redis_url(monkeypatch, "redis://example")
    _patch_gx_redis_lpush(monkeypatch, _fake_redis_lpush)
    _patch_gx_worker_heartbeat(monkeypatch, _worker_available)
    monkeypatch.setattr(gx_endpoints, "get_data_catalog_repository", lambda: repo)

    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    transitioned = await gx_endpoints.transition_gx_run_plan_version_governance_state(
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({
            "target_state": "pending_validation",
        }),
        run_plan_repository=repo,
    )
    transitioned = await gx_endpoints.transition_gx_run_plan_version_governance_state(
        run_plan_id=transitioned.runPlanId,
        run_plan_version_id=transitioned.versions[0].runPlanVersionId,
        request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({
            "target_state": "pending_review",
        }),
        run_plan_repository=repo,
    )
    transitioned = await gx_endpoints.transition_gx_run_plan_version_governance_state(
        run_plan_id=transitioned.runPlanId,
        run_plan_version_id=transitioned.versions[0].runPlanVersionId,
        request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({
            "target_state": "approved_pending_activation",
        }),
        run_plan_repository=repo,
    )

    repo._run_plans[transitioned.runPlanId]["versions"][0]["suiteSnapshot"] = {
        "suiteId": "gx-inventory",
        "suiteVersion": 1,
        "dataObjectVersionId": "dov-24",
    }

    with pytest.raises(HTTPException) as excinfo:
        await gx_endpoints.activate_gx_run_plan_version(
            request=request,
            run_plan_id=transitioned.runPlanId,
            run_plan_version_id=transitioned.versions[0].runPlanVersionId,
            run_plan_repository=repo,
            execution_run_repository=repo,
        )

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail["error"] == "invalid_suite_snapshot"
    assert excinfo.value.detail["run_plan_id"] == transitioned.runPlanId
    assert excinfo.value.detail["run_plan_version_id"] == transitioned.versions[0].runPlanVersionId

    monkeypatch.undo()


@pytest.mark.anyio
async def test_transition_to_activation_requested_creates_pending_approval() -> None:
    repo = _Repo()
    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    created_approvals: list[dict] = []

    class _ApprovalsRepo:
        def list_approvals(self, workspace_id: str | None = None) -> list[dict]:
            return []

        def create_approval(self, payload: dict, actor_id: str | None = None) -> dict:
            created_approvals.append({"payload": dict(payload), "actor_id": actor_id})
            return {"id": "approval-1", **payload, "requester_id": actor_id}

    transitioned = await gx_endpoints.transition_gx_run_plan_version_governance_state(
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({"target_state": "activation-requested"}),
        approvals_repository=_ApprovalsRepo(),
        run_plan_repository=repo,
    )

    assert transitioned.status == "activation-requested"
    assert transitioned.versions[0].governanceState == "activation-requested"
    assert created_approvals and created_approvals[0]["payload"]["gx_run_plan_id"] == created.runPlanId
    assert created_approvals[0]["payload"]["gx_run_plan_version_id"] == created.versions[0].runPlanVersionId
    assert created_approvals[0]["payload"]["request_type"] == "activation"
    assert created_approvals[0]["payload"]["status"] == "pending"


@pytest.mark.anyio
async def test_transition_to_activation_requested_rejects_existing_pending_dict_approval() -> None:
    repo = _Repo()
    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )

    class _ApprovalsRepo:
        def list_approvals(self, workspace_id: str | None = None) -> list[dict]:
            return [
                {
                    "id": "approval-1",
                    "rule_id": "",
                    "gx_run_plan_id": created.runPlanId,
                    "gx_run_plan_version_id": created.versions[0].runPlanVersionId,
                    "request_type": "activation",
                    "status": "pending",
                    "workspace_id": "retail-banking",
                }
            ]

        def create_approval(self, payload: dict, actor_id: str | None = None) -> dict:
            raise AssertionError("create_approval should not be called when a pending request already exists")

    with pytest.raises(HTTPException) as excinfo:
        await gx_endpoints.transition_gx_run_plan_version_governance_state(
            run_plan_id=created.runPlanId,
            run_plan_version_id=created.versions[0].runPlanVersionId,
            request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({"target_state": "activation-requested"}),
            approvals_repository=_ApprovalsRepo(),
            run_plan_repository=repo,
        )

    assert excinfo.value.status_code == 409
    assert created.versions[0].runPlanVersionId in str(excinfo.value.detail)


@pytest.mark.anyio
async def test_active_run_plan_spawns_new_pending_branch_version() -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={})

    async def _fake_redis_lpush(redis_url: str, queue_key: str, payload: dict) -> None:
        return None

    async def _worker_available(redis_url: str, queue_key: str) -> None:
        return None

    monkeypatch = pytest.MonkeyPatch()
    _patch_gx_redis_url(monkeypatch, "redis://example")
    _patch_gx_redis_lpush(monkeypatch, _fake_redis_lpush)
    _patch_gx_worker_heartbeat(monkeypatch, _worker_available)
    monkeypatch.setattr(gx_endpoints, "get_data_catalog_repository", lambda: repo)

    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )
    for target_state in ("pending_validation", "pending_review", "approved_pending_activation"):
        created = await gx_endpoints.transition_gx_run_plan_version_governance_state(
            run_plan_id=created.runPlanId,
            run_plan_version_id=created.versions[0].runPlanVersionId,
            request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({"target_state": target_state}),
            run_plan_repository=repo,
        )
    activated = await gx_endpoints.activate_gx_run_plan_version(
        request=request,
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        run_plan_repository=repo,
        execution_run_repository=repo,
    )

    branched = await gx_endpoints.create_gx_run_plan_version(
        run_plan_id=activated.plan.runPlanId,
        request_body=gx_endpoints.GxRunPlanVersionCreateRequestView.model_validate(
            {
                "suite_id": "gx_suite_1",
                "suite_version": 2,
                "scheduled_at": "2026-04-11T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
    )
    monkeypatch.undo()

    assert branched.status == "active"
    assert branched.currentActiveVersionId == activated.plan.currentActiveVersionId
    assert branched.pendingVersionGovernanceState == "draft"
    assert branched.versions[-1].supersedesVersionId == activated.plan.currentActiveVersionId


@pytest.mark.anyio
async def test_create_grouped_scope_run_plan_uses_run_plan_shape() -> None:
    repo = _Repo()

    out = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "planning_mode": "grouped_scope",
                "data_object_version_id": "dov_1",
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
        grouped_execution_planner=gx_endpoints.GroupedExecutionPlanner(),
    )

    assert out.planningMode == "grouped_scope"
    assert out.versions[0].gxSuiteSelection.selectionMode == "grouped_scope"
    assert out.versions[0].gxSuiteSelection.suiteRefs[0].engineType == "gx"
    assert out.versions[0].suiteId is None


@pytest.mark.anyio
async def test_activate_grouped_scope_run_plan_enqueues_grouped_dispatch(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={"X-Correlation-ID": "corr-grouped-plan-1"})
    captured: list[dict] = []

    async def _fake_redis_lpush(redis_url: str, queue_key: str, payload: dict) -> None:
        captured.append({"redis_url": redis_url, "queue_key": queue_key, "payload": payload})

    async def _worker_available(redis_url: str, queue_key: str) -> None:
        return None

    _patch_gx_redis_url(monkeypatch, "redis://example")
    _patch_gx_redis_lpush(monkeypatch, _fake_redis_lpush)
    _patch_gx_worker_heartbeat(monkeypatch, _worker_available)
    monkeypatch.setattr(gx_endpoints, "get_data_catalog_repository", lambda: repo)

    created = await gx_endpoints.create_gx_run_plan(
        request_body=gx_endpoints.GxRunPlanCreateRequestView.model_validate(
            {
                "workspace_id": "retail-banking",
                "planning_mode": "grouped_scope",
                "data_object_version_id": "dov_1",
                "scheduled_at": "2026-04-10T10:30:00Z",
            }
        ),
        artifact_repository=repo,
        run_plan_repository=repo,
        grouped_execution_planner=gx_endpoints.GroupedExecutionPlanner(),
    )
    for target_state in ("pending_validation", "pending_review", "approved_pending_activation"):
        created = await gx_endpoints.transition_gx_run_plan_version_governance_state(
            run_plan_id=created.runPlanId,
            run_plan_version_id=created.versions[0].runPlanVersionId,
            request_body=gx_endpoints.GxRunPlanGovernanceTransitionRequestView.model_validate({"target_state": target_state}),
            run_plan_repository=repo,
        )

    out = await gx_endpoints.activate_gx_run_plan_version(
        request=request,
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        run_plan_repository=repo,
        execution_run_repository=repo,
    )

    assert out.plan.status == "active"
    assert out.dispatch["execution_shape"] == "grouped_scope"
    assert out.dispatch["correlation_id"] == "corr-grouped-plan-1"
    assert repo.last_run_create_kwargs is not None
    assert repo.last_run_create_kwargs["execution_shape"] == "grouped_scope"
    assert repo.last_run_create_kwargs["suite_id"] is None
    assert captured


@pytest.mark.anyio
async def test_list_gx_suites_rejects_multiple_primary_scopes() -> None:
    repo = _Repo()

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.list_gx_suites(
            data_object_id="do_1",
            data_object_version_id=None,
            dataset_id="ds_1",
            data_product_id=None,
            status="active",
            latest_only=True,
            repository=repo,
        )

    assert error.value.status_code == 400


@pytest.mark.anyio
async def test_create_gx_assistance_request_uses_configured_itsm_system(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[tuple[str, Any, dict[str, str]]] = []
    fake_response = _FakeResponse(200, {"ticket_number": "HAL-4242", "ticket_url": "https://itsm.example.com/tickets/4242"})

    class FakeAsyncClient(_FakeAsyncClient):
        def __init__(self, timeout: float | None = None) -> None:
            super().__init__(posts, fake_response)

    monkeypatch.setattr(gx_endpoints.httpx, "AsyncClient", FakeAsyncClient)

    response = await gx_endpoints.create_gx_assistance_request(
        request_view=gx_endpoints.GxAssistanceRequestView.model_validate(
            {
                "run_plan_id": "run-plan-1",
                "run_plan_version_id": "run-plan-version-1",
                "workspace_id": "retail-banking",
                "error_message": "Validation failed for run plan version 'run-plan-version-1'",
                "diagnostics": [],
            }
        ),
        request=SimpleNamespace(headers={}),
        app_config_repository=_AppConfigRepo(
            assistanceRequestMode="itsm",
            assistanceRequestEmailAddress="prototype@jaccloud.nl",
            assistanceRequestItsmSystem="Zammad",
            assistanceRequestItsmEndpointUrl="https://itsm.example.com/api/v1/tickets",
            assistanceRequestItsmAuthToken="zammad-api-token",
        ),
    )

    assert response.deliveryMode == "itsm"
    assert response.ticketNumber == "HAL-4242"
    assert response.ticketSystem == "Zammad"
    assert posts[0][0] == "https://itsm.example.com/api/v1/tickets"
    assert posts[0][1]["it_system"] == "Zammad"
    assert posts[0][2]["Authorization"] == "Token token=zammad-api-token"


@pytest.mark.anyio
async def test_create_gx_assistance_request_requires_itsm_system(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _AppConfigRepo(
        assistanceRequestMode="itsm",
        assistanceRequestEmailAddress="prototype@jaccloud.nl",
        assistanceRequestItsmSystem="",
        assistanceRequestItsmEndpointUrl="https://itsm.example.com/api/v1/tickets",
    )

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.create_gx_assistance_request(
            request_view=gx_endpoints.GxAssistanceRequestView.model_validate(
                {
                    "run_plan_id": "run-plan-1",
                    "run_plan_version_id": "run-plan-version-1",
                    "workspace_id": "retail-banking",
                    "error_message": "Validation failed for run plan version 'run-plan-version-1'",
                    "diagnostics": [],
                }
            ),
            request=SimpleNamespace(headers={}),
            app_config_repository=repo,
        )

    assert error.value.status_code == 400
    assert error.value.detail["error"] == "itsm_system_missing"


@pytest.mark.anyio
async def test_create_gx_assistance_request_requires_zammad_api_token(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _AppConfigRepo(
        assistanceRequestMode="itsm",
        assistanceRequestEmailAddress="prototype@jaccloud.nl",
        assistanceRequestItsmSystem="Zammad",
        assistanceRequestItsmEndpointUrl="https://itsm.example.com/api/v1/tickets",
        assistanceRequestItsmAuthToken="",
    )

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.create_gx_assistance_request(
            request_view=gx_endpoints.GxAssistanceRequestView.model_validate(
                {
                    "run_plan_id": "run-plan-1",
                    "run_plan_version_id": "run-plan-version-1",
                    "workspace_id": "retail-banking",
                    "error_message": "Validation failed for run plan version 'run-plan-version-1'",
                    "diagnostics": [],
                }
            ),
            request=SimpleNamespace(headers={}),
            app_config_repository=repo,
        )

    assert error.value.status_code == 400
    assert error.value.detail["error"] == "itsm_auth_token_missing"


@pytest.mark.anyio
async def test_create_gx_assistance_request_requires_email_recipient() -> None:
    repo = _AppConfigRepo(
        assistanceRequestMode="email",
        assistanceRequestEmailAddress="",
    )

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.create_gx_assistance_request(
            request_view=gx_endpoints.GxAssistanceRequestView.model_validate(
                {
                    "run_plan_id": "run-plan-1",
                    "run_plan_version_id": "run-plan-version-1",
                    "workspace_id": "retail-banking",
                    "error_message": "Validation failed for run plan version 'run-plan-version-1'",
                    "diagnostics": [],
                }
            ),
            request=SimpleNamespace(headers={}),
            app_config_repository=repo,
        )

    assert error.value.status_code == 400
    assert error.value.detail["error"] == "assistance_email_missing"


@pytest.mark.anyio
async def test_list_gx_suites_rejects_invalid_odcs_data_product() -> None:
    repo = _Repo()

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.list_gx_suites(
            data_object_id=None,
            data_object_version_id=None,
            dataset_id=None,
            data_product_id="sales-001",
            status="active",
            latest_only=True,
            repository=repo,
        )

    assert error.value.status_code == 400


@pytest.mark.anyio
async def test_get_gx_suite_returns_payload_and_forwards_suite_version() -> None:
    repo = _Repo()

    out = await gx_endpoints.get_gx_suite(
        suite_id="gx_suite_1",
        suite_version=2,
        status="disabled",
        repository=repo,
    )

    assert out.suiteId == "gx_suite_1"
    assert repo.last_get_kwargs == {
        "artifact_id": "gx_suite_1",
        "artifact_version": 2,
        "status": "disabled",
    }


@pytest.mark.anyio
async def test_get_gx_suite_returns_404_when_not_found() -> None:
    repo = _Repo()
    repo.get_payload = None

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.get_gx_suite(
            suite_id="missing-suite",
            suite_version=None,
            status="active",
            repository=repo,
        )

    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_get_gx_suite_rejects_invalid_suite_version() -> None:
    repo = _Repo()

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.get_gx_suite(
            suite_id="gx_suite_1",
            suite_version=0,
            status="active",
            repository=repo,
        )

    assert error.value.status_code == 400


@pytest.mark.anyio
async def test_start_gx_suite_run_returns_handoff_payload(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={"X-Correlation-ID": "corr-test-123"})
    monkeypatch.setattr(gx_endpoints, "get_data_catalog_repository", lambda: repo)

    out = await gx_endpoints.start_gx_suite_run(
        request=request,
        suite_id="gx_suite_1",
        suite_version=2,
        status="active",
        repository=repo,
        execution_run_repository=repo,
    )

    assert out.suiteId == "gx_suite_1"
    assert out.suiteVersion == 1
    assert out.correlationId == "corr-test-123"
    assert out.engineType == "gx"
    assert out.handoffStatus == "accepted"
    assert out.executionShape == "single_object"
    assert repo.last_get_kwargs == {
        "suite_id": "gx_suite_1",
        "suite_version": 2,
        "status": "active",
    }
    assert repo.last_run_create_kwargs is not None
    assert repo.last_run_create_kwargs["status"] == "pending"
    assert repo.last_run_create_kwargs["suite_id"] == "gx_suite_1"
    assert repo.last_run_create_kwargs["rule_id"] == "rule_1"
    assert repo.last_run_create_kwargs["execution_contract"]["traceability"]["source_rule_expression"] == "status = 'ACTIVE'"
    assert repo.last_run_create_kwargs["execution_contract"]["traceability"]["compiled_expression"] == "status = 'ACTIVE'"
    assert repo.last_run_create_kwargs["execution_contract"]["traceability"]["artifact_key"] == "artifact_1"
    assert repo.last_run_create_kwargs["execution_contract"]["resolved_data_object_version_id"] == "dov_1"
    assert repo.last_run_create_kwargs["execution_contract"]["resolved_data_delivery_id"] == "del-31"
    assert repo.last_run_create_kwargs["execution_contract"]["resolved_delivery_location"] == "s3a://analytics/do-1/v1/LOAD_DTS=20260221T153000000Z"
    assert repo.last_run_create_kwargs["engine_type"] == "gx"
    assert repo.last_run_create_kwargs["status_details"]["handoff_status"] == "accepted"


@pytest.mark.anyio
async def test_get_gx_execution_run_returns_persisted_run(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={})
    monkeypatch.setattr(gx_endpoints, "get_data_catalog_repository", lambda: repo)
    created = await gx_endpoints.start_gx_suite_run(
        request=request,
        suite_id="gx_suite_1",
        suite_version=2,
        status="active",
        repository=repo,
        execution_run_repository=repo,
    )

    out = await gx_endpoints.get_gx_execution_run(
        run_id=created.runId,
        repository=repo,
    )

    assert out.id == created.runId
    assert out.status == "pending"
    assert out.ruleId == "rule_1"
    assert out.statusHistory[0].toStatus == "pending"
    assert repo.last_run_get_kwargs == {"run_id": created.runId}


@pytest.mark.anyio
async def test_get_gx_execution_run_status_history_returns_entries(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={})
    monkeypatch.setattr(gx_endpoints, "get_data_catalog_repository", lambda: repo)
    created = await gx_endpoints.start_gx_suite_run(
        request=request,
        suite_id="gx_suite_1",
        suite_version=2,
        status="active",
        repository=repo,
        execution_run_repository=repo,
    )

    out = await gx_endpoints.get_gx_execution_run_status_history(
        run_id=created.runId,
        repository=repo,
    )

    assert len(out) == 1
    assert out[0].runId == created.runId
    assert out[0].toStatus == "pending"
    assert repo.last_run_history_kwargs == {"run_id": created.runId}


def test_build_run_summary_includes_failed_record_count() -> None:
    summary = build_gx_execution_run_summary(
        run=build_gx_execution_run_entity({
            "id": "run-123",
            "ruleId": "rule_1",
            "correlationId": "corr-123",
            "requestedBy": "user-admin",
            "engineType": "gx",
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "status": "succeeded",
            "submittedAt": "2026-04-20T09:00:00Z",
            "createdAt": "2026-04-20T09:00:00Z",
            "updatedAt": "2026-04-20T09:05:00Z",
            "resultSummary": {
                "results": [
                    {"ok": False},
                    {"violationCount": "4"},
                ],
            },
        }),
        rule_name_by_id={"rule_1": "Customer Order Completeness"},
        data_object_name_by_id={},
        data_object_name_by_version_id={},
    )

    assert summary.ruleName == "Customer Order Completeness"
    assert summary.failedRecordCount == 5


@pytest.mark.anyio
async def test_get_gx_execution_exception_analytics_aggregates_persisted_violations() -> None:
    repo = _Repo()
    window_end = datetime.now(UTC)
    first_run_time = window_end - timedelta(hours=2)
    second_run_time = window_end - timedelta(hours=1)

    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-123",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "rule_id": "rule_1",
                "rule_version_id": "rule_version_1",
                "correlation_id": "corr-123",
                "requested_by": "user-admin",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "succeeded",
                "submitted_at": first_run_time.isoformat(),
                "execution_contract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "single_object",
                    "traceability": {
                        "dataObjectVersionId": "dov_1",
                        "ruleId": "rule_1",
                    }
                },
            }
        )
    )
    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-456",
                "suite_id": "gx_suite_2",
                "suite_version": 1,
                "rule_id": None,
                "rule_version_id": None,
                "correlation_id": "corr-456",
                "requested_by": "user-admin",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "grouped_scope",
                "status": "succeeded",
                "submitted_at": second_run_time.isoformat(),
                "execution_contract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "grouped_scope",
                    "traceability": {
                        "dataObjectVersionId": "dov_1",
                    }
                },
            }
        )
    )
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-123",
                "rule_id": "rule_1",
                "data_primary_key": "pk-1",
                "violation_reason": "missing value",
                "ops_metadata": {
                    "reason_code": "expect_column_values_to_not_be_null",
                    "reason_text": "customer_id must not be null",
                },
                "detected_at": (first_run_time + timedelta(minutes=1)).isoformat(),
            },
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-456",
                "rule_id": "rule_2",
                "data_primary_key": "pk-2",
                "violation_reason": "mismatch",
                "ops_metadata": {
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (second_run_time + timedelta(minutes=1)).isoformat(),
            },
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-456",
                "rule_id": "rule_2",
                "data_primary_key": "pk-3",
                "violation_reason": "mismatch",
                "ops_metadata": {
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (second_run_time + timedelta(minutes=2)).isoformat(),
            },
        ]
    )

    out = await gx_endpoints.get_gx_execution_exception_analytics(
        request=SimpleNamespace(headers={}),
        lookback_amount=720,
        lookback_unit="hours",
        status=None,
        rule_name=None,
        data_object_name=None,
        search=None,
        reason_code=None,
        suite_id=None,
        data_object_version_id=None,
        rule_version_id=None,
        repository=repo,
        run_plan_repository=repo,
        projection_repository=repo,
        rules_repository=repo,
        data_catalog_repository=repo,
        suite_repository=repo,
    )

    assert out.totalFailedRecords == 3
    assert out.runsWithFailures == 2
    assert sum(bucket.total for bucket in out.trendBuckets) == 3
    assert out.topRules[0].ruleId == "rule_2"
    assert out.topRules[0].ruleName == "Transfer Match"
    assert out.topRules[0].total == 2
    assert out.topDataObjects[0].dataObjectVersionId == "dov_1"
    assert out.topDataObjects[0].dataObjectName == "Orders"
    assert out.topDataObjects[0].total == 3
    assert out.topReasons[0].reasonCode == "value_mismatch"
    assert out.topReasons[0].reasonText == "customer_id differs from golden source"
    assert out.topReasons[0].total == 2
    assert len(out.reasonTrendBuckets) == 2
    assert sum(bucket.total for bucket in out.reasonTrendBuckets if bucket.reasonCode == "value_mismatch") == 2
    assert sum(bucket.total for bucket in out.reasonTrendBuckets if bucket.reasonCode == "expect_column_values_to_not_be_null") == 1
    assert len(out.reasonFluctuations) == 2
    assert out.reasonFluctuations[0].reasonCode == "value_mismatch"
    assert out.reasonFluctuations[0].direction == "flat"
    assert out.reasonFluctuations[0].netChange == 0
    assert repo.last_reason_analytics_summary_kwargs is not None
    assert repo.last_reason_analytics_summary_kwargs["data_object_version_ids"] == ["dov_1"]
    assert repo.last_reason_analytics_summary_kwargs["execution_run_ids"] == ["run-123", "run-456"]


@pytest.mark.anyio
async def test_get_gx_execution_exception_analytics_filters_reason_code() -> None:
    repo = _Repo()
    window_end = datetime.now(UTC)
    first_run_time = window_end - timedelta(hours=2)
    second_run_time = window_end - timedelta(hours=1)

    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-123",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "rule_id": "rule_1",
                "rule_version_id": "rule_version_1",
                "correlation_id": "corr-123",
                "requested_by": "user-admin",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "succeeded",
                "submitted_at": first_run_time.isoformat(),
                "execution_contract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "single_object",
                    "traceability": {
                        "dataObjectVersionId": "dov_1",
                        "ruleId": "rule_1",
                    }
                },
            }
        )
    )
    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-456",
                "suite_id": "gx_suite_2",
                "suite_version": 1,
                "rule_id": None,
                "rule_version_id": None,
                "correlation_id": "corr-456",
                "requested_by": "user-admin",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "grouped_scope",
                "status": "succeeded",
                "submitted_at": second_run_time.isoformat(),
                "execution_contract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "grouped_scope",
                    "traceability": {
                        "dataObjectVersionId": "dov_1",
                    }
                },
            }
        )
    )
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-123",
                "rule_id": "rule_1",
                "data_primary_key": "pk-1",
                "violation_reason": "missing value",
                "ops_metadata": {
                    "reason_code": "expect_column_values_to_not_be_null",
                    "reason_text": "customer_id must not be null",
                },
                "detected_at": (first_run_time + timedelta(minutes=1)).isoformat(),
            },
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-456",
                "rule_id": "rule_2",
                "data_primary_key": "pk-2",
                "violation_reason": "mismatch",
                "ops_metadata": {
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (second_run_time + timedelta(minutes=1)).isoformat(),
            },
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-456",
                "rule_id": "rule_2",
                "data_primary_key": "pk-3",
                "violation_reason": "mismatch",
                "ops_metadata": {
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (second_run_time + timedelta(minutes=2)).isoformat(),
            },
        ]
    )

    out = await gx_endpoints.get_gx_execution_exception_analytics(
        request=SimpleNamespace(headers={}),
        lookback_amount=720,
        lookback_unit="hours",
        status=None,
        rule_name=None,
        data_object_name=None,
        search=None,
        reason_code="value_mismatch",
        suite_id=None,
        data_object_version_id=None,
        rule_version_id=None,
        repository=repo,
        run_plan_repository=repo,
        projection_repository=repo,
        rules_repository=repo,
        data_catalog_repository=repo,
        suite_repository=repo,
    )

    assert out.totalFailedRecords == 2
    assert [item.reasonCode for item in out.topReasons] == ["value_mismatch"]
    assert all(item.reasonCode == "value_mismatch" for item in out.reasonTrendBuckets)
    assert len(out.reasonFluctuations) == 1
    assert out.reasonFluctuations[0].reasonCode == "value_mismatch"
    assert repo.last_reason_analytics_summary_kwargs is not None
    assert repo.last_reason_analytics_summary_kwargs["reason_codes"] == ["value_mismatch"]


@pytest.mark.anyio
async def test_get_gx_execution_run_statistics_returns_engine_agnostic_breakdowns() -> None:
    repo = _Repo()
    repo._runs["run-stat-1"] = {
        "id": "run-stat-1",
        "suiteId": "gx-suite-1",
        "suiteVersion": 1,
        "ruleId": "rule_1",
        "correlationId": "corr-stat-1",
        "requestedBy": "user-admin",
        "engineType": "neutral-runtime",
        "engineTarget": "pyspark",
        "executionShape": "single_object",
        "status": "running",
        "submittedAt": "2026-04-16T09:45:00Z",
        "createdAt": "2026-04-16T09:45:00Z",
        "updatedAt": "2026-04-16T09:45:00Z",
        "executionContract": {
            "engineType": "neutral-runtime",
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "traceability": {
                "dataObjectVersionId": "dov_1",
                "ruleId": "rule_1",
            },
        },
    }
    repo._runs["run-stat-2"] = {
        "id": "run-stat-2",
        "suiteId": "gx-suite-2",
        "suiteVersion": 1,
        "ruleId": "rule_2",
        "correlationId": "corr-stat-2",
        "requestedBy": "user-admin",
        "engineType": "batch-runtime",
        "engineTarget": "spark",
        "executionShape": "grouped_scope",
        "status": "succeeded",
        "submittedAt": "2026-04-16T09:30:00Z",
        "createdAt": "2026-04-16T09:30:00Z",
        "updatedAt": "2026-04-16T09:30:00Z",
        "executionContract": {
            "engineType": "batch-runtime",
            "engineTarget": "spark",
            "executionShape": "grouped_scope",
            "traceability": {
                "dataObjectVersionId": "dov_2",
                "ruleId": "rule_2",
            },
        },
    }

    out = await gx_endpoints.get_gx_execution_run_statistics(
        request=_request(),
        lookback_amount=720,
        lookback_unit="hours",
        recent_limit=1,
        run_plan_id=None,
        repository=repo,
        run_plan_repository=repo,
        rules_repository=repo,
        data_catalog_repository=repo,
        suite_repository=repo,
    )

    assert out.totalRuns == 2
    assert out.runningRuns == 1
    assert out.succeededRuns == 1
    assert [row.name for row in out.statusBreakdown] == ["running", "succeeded"]
    assert [row.name for row in out.engineTargetBreakdown] == ["pyspark", "spark"]
    assert [row.name for row in out.executionShapeBreakdown] == ["grouped_scope", "single_object"]
    assert len(out.recentRuns) == 1
    assert out.recentRuns[0].id == "run-stat-1"


@pytest.mark.anyio
async def test_list_exception_facts_returns_canonical_contract_page() -> None:
    repo = _Repo()
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-100",
                "rule_id": "rule_1",
                "data_primary_key": "pk-1",
                "violation_reason": "customer_id differs from golden source",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "suite_id": "gx_suite_1",
                    "suite_version": 1,
                    "rule_version_id": "rule_version_1",
                    "correlation_id": "corr-100",
                    "engine_type": "gx",
                    "execution_plan_id": "run-plan-1",
                    "execution_plan_version_id": "run-plan-version-3",
                    "delivery_id": "delivery-1",
                    "record_identifier_type": "business_key",
                    "record_identifier_value": "sales_order_number=SO-42",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                    "failure_class": "data_quality_assertion_failed",
                    "expectation_type": "expect_column_pair_values_to_be_equal",
                },
                "detected_at": "2026-04-10T08:01:00Z",
            }
        ]
    )

    out = await exception_endpoints.list_exception_facts(
        request=_request(),
        data_object_version_id="dov_1",
        execution_run_id=None,
        limit=25,
        offset=0,
        admin_repository=repo,
        data_catalog_repository=repo,
        violation_repository=repo,
    )

    assert len(out.data) == 1
    assert out.data[0].exceptionFactId == "vio-1"
    assert out.data[0].exceptionFactContractVersion == "v1"
    assert out.data[0].engineType == "gx"
    assert out.data[0].executionScope.executionRunId == "run-100"
    assert out.data[0].executionScope.dataObjectVersionId == "dov_1"
    assert out.data[0].executionScope.executionPlanId == "run-plan-1"
    assert out.data[0].artifactScope.validationArtifactId == "gx_suite_1"
    assert out.data[0].artifactScope.validationArtifactVersion == 1
    assert out.data[0].ruleScope.ruleId == "rule_1"
    assert out.data[0].ruleScope.ruleVersionId == "rule_version_1"
    assert out.data[0].recordReference.identifierType == "business_key"
    assert out.data[0].recordReference.identifierValue == "sales_order_number=SO-42"
    assert out.data[0].failure.reasonCode == "value_mismatch"
    assert out.data[0].failure.reasonText == "customer_id differs from golden source"
    assert out.data[0].engineMetadata["expectation_type"] == "expect_column_pair_values_to_be_equal"
    assert out.pagination.total == 1
    assert out.pagination.total_pages == 1


@pytest.mark.anyio
async def test_get_exception_fact_returns_canonical_contract() -> None:
    repo = _Repo()
    repo._runs["run-200"] = {
        "id": "run-200",
        "requestedBy": "user-admin",
        "correlationId": "corr-200",
        "engineType": "gx",
        "engineTarget": "pyspark",
        "executionShape": "single_object",
        "status": "succeeded",
        "submittedAt": "2026-04-10T08:02:00Z",
        "createdAt": "2026-04-10T08:02:00Z",
        "updatedAt": "2026-04-10T08:02:00Z",
        "executionContract": {
            "engineType": "gx",
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "traceability": {
                "dataObjectVersionId": "dov_1",
                "ruleId": "rule_1",
                "ruleVersionId": "rule_version_1",
            },
        },
        "statusHistory": [],
    }
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-200",
                "rule_id": "rule_1",
                "data_primary_key": "pk-2",
                "violation_reason": "customer_id must not be null",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "suite_id": "gx_suite_1",
                    "suite_version": 1,
                    "rule_version_id": "rule_version_1",
                    "correlation_id": "corr-200",
                    "engine_type": "gx",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-2",
                    "reason_code": "expect_column_values_to_not_be_null",
                    "reason_text": "customer_id must not be null",
                },
                "detected_at": "2026-04-10T08:02:00Z",
            }
        ]
    )

    out = await exception_endpoints.get_exception_fact(
        request=_request(),
        exception_fact_id="vio-1",
        data_object_version_id="dov_1",
        admin_repository=repo,
        data_catalog_repository=repo,
        execution_run_repository=repo,
        violation_repository=repo,
    )

    assert out.exceptionFactId == "vio-1"
    assert out.executionScope.executionRunId == "run-200"
    assert out.recordReference.identifierType == "primary_key"
    assert out.recordReference.identifierValue == "row-2"
    assert out.failure.reasonCode == "expect_column_values_to_not_be_null"
    assert out.correlationId == "corr-200"


@pytest.mark.anyio
async def test_get_exception_fact_denies_non_owner_detail_access() -> None:
    repo = _Repo()
    repo.current_user = SimpleNamespace(
        id="user-other",
        name="Other User",
        email="other@example.com",
        granted_scopes=["dq:rules:read"],
        workspace_roles=[],
    )
    repo._runs["run-200"] = {
        "id": "run-200",
        "requestedBy": "user-admin",
        "correlationId": "corr-200",
        "engineType": "gx",
        "engineTarget": "pyspark",
        "executionShape": "single_object",
        "status": "succeeded",
        "submittedAt": "2026-04-10T08:02:00Z",
        "createdAt": "2026-04-10T08:02:00Z",
        "updatedAt": "2026-04-10T08:02:00Z",
        "executionContract": {
            "engineType": "gx",
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "traceability": {
                "dataObjectVersionId": "dov_1",
                "ruleId": "rule_1",
                "ruleVersionId": "rule_version_1",
            },
        },
        "statusHistory": [],
    }
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-200",
                "rule_id": "rule_1",
                "data_primary_key": "pk-2",
                "violation_reason": "customer_id must not be null",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "suite_id": "gx_suite_1",
                    "suite_version": 1,
                    "rule_version_id": "rule_version_1",
                    "correlation_id": "corr-200",
                    "engine_type": "gx",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-2",
                    "reason_code": "expect_column_values_to_not_be_null",
                    "reason_text": "customer_id must not be null",
                },
                "detected_at": "2026-04-10T08:02:00Z",
            }
        ]
    )

    with pytest.raises(HTTPException) as error:
        await exception_endpoints.get_exception_fact(
            request=_request(user_id="user-other"),
            exception_fact_id="vio-1",
            data_object_version_id="dov_1",
            admin_repository=repo,
            data_catalog_repository=repo,
            execution_run_repository=repo,
            violation_repository=repo,
        )

    assert error.value.status_code == 403
    assert error.value.detail["error"] == "exception_fact_access_denied"
    assert error.value.detail["execution_run_id"] == "run-200"
    assert error.value.detail["workspace_id"] == "retail-banking"


@pytest.mark.anyio
async def test_list_exception_facts_fails_fast_on_incomplete_contract_row() -> None:
    repo = _Repo()
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-300",
                "rule_id": "rule_1",
                "data_primary_key": "pk-3",
                "violation_reason": "customer_id must not be null",
                "ops_metadata": {
                    "engine_type": "gx",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-3",
                    "reason_code": "expect_column_values_to_not_be_null",
                    "reason_text": "customer_id must not be null",
                },
                "detected_at": "2026-04-10T08:03:00Z",
            }
        ]
    )

    with pytest.raises(HTTPException) as error:
        await exception_endpoints.list_exception_facts(
            request=_request(correlation_id="corr-exc-1"),
            data_object_version_id="dov_1",
            execution_run_id=None,
            limit=25,
            offset=0,
            admin_repository=repo,
            data_catalog_repository=repo,
            violation_repository=repo,
        )

    assert error.value.status_code == 500
    assert error.value.detail["error"] == "exception_fact_contract_unavailable"
    assert error.value.detail["correlation_id"] == "corr-exc-1"


@pytest.mark.anyio
async def test_get_exception_reason_analytics_uses_neutral_route() -> None:
    repo = _Repo()
    window_end = datetime.now(UTC)
    first_run_time = window_end - timedelta(hours=2)
    second_run_time = window_end - timedelta(hours=1)

    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-123",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "rule_id": "rule_1",
                "rule_version_id": "rule_version_1",
                "correlation_id": "corr-123",
                "requested_by": "user-admin",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "succeeded",
                "submitted_at": first_run_time.isoformat(),
                "execution_contract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "single_object",
                    "traceability": {
                        "dataObjectVersionId": "dov_1",
                        "ruleId": "rule_1",
                    }
                },
            }
        )
    )
    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-456",
                "suite_id": "gx_suite_2",
                "suite_version": 1,
                "rule_id": None,
                "rule_version_id": None,
                "correlation_id": "corr-456",
                "requested_by": "user-admin",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "grouped_scope",
                "status": "succeeded",
                "submitted_at": second_run_time.isoformat(),
                "execution_contract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "grouped_scope",
                    "traceability": {
                        "dataObjectVersionId": "dov_1",
                    }
                },
            }
        )
    )
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-123",
                "rule_id": "rule_1",
                "data_primary_key": "pk-1",
                "violation_reason": "missing value",
                "ops_metadata": {
                    "reason_code": "expect_column_values_to_not_be_null",
                    "reason_text": "customer_id must not be null",
                },
                "detected_at": (first_run_time + timedelta(minutes=1)).isoformat(),
            },
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-456",
                "rule_id": "rule_2",
                "data_primary_key": "pk-2",
                "violation_reason": "mismatch",
                "ops_metadata": {
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (second_run_time + timedelta(minutes=1)).isoformat(),
            },
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-456",
                "rule_id": "rule_2",
                "data_primary_key": "pk-3",
                "violation_reason": "mismatch",
                "ops_metadata": {
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (second_run_time + timedelta(minutes=2)).isoformat(),
            },
        ]
    )

    out = await exception_endpoints.get_exception_reason_analytics(
        request=SimpleNamespace(headers={}),
        lookback_amount=48,
        lookback_unit="hours",
        status=None,
        rule_name=None,
        data_object_name=None,
        search=None,
        reason_code=None,
        suite_id="gx_suite_1",
        data_object_version_id="dov_1",
        rule_version_id="rule_version_1",
        repository=repo,
        run_plan_repository=repo,
        projection_repository=repo,
        rules_repository=repo,
        data_catalog_repository=repo,
        suite_repository=repo,
    )

    assert out.totalFailedRecords == 1
    assert [item.reasonCode for item in out.topReasons] == ["expect_column_values_to_not_be_null"]
    assert len(out.reasonFluctuations) == 1
    assert out.reasonFluctuations[0].reasonCode == "expect_column_values_to_not_be_null"
    assert repo.last_reason_analytics_summary_kwargs is not None
    assert repo.last_reason_analytics_summary_kwargs["execution_run_ids"] == ["run-123"]


@pytest.mark.anyio
async def test_get_delivery_exception_summary_returns_reason_counts_by_reason() -> None:
    repo = _Repo()
    current_time = datetime.now(UTC)
    await repo.create_run(
        run_id="run-delivery-1",
        suite_id="gx_suite_1",
        suite_version=1,
        rule_id="rule_1",
        rule_version_id="rule_version_1",
        correlation_id="corr-delivery-1",
        requested_by="user-1",
        engine_type="gx",
        engine_target="pyspark",
        execution_shape="single_object",
        status="failed",
        submitted_at=(current_time - timedelta(hours=2)).isoformat(),
        execution_contract={
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "resolved_data_delivery_id": "del-31",
            "resolved_data_object_version_id": "dov_1",
            "traceability": {"data_object_version_id": "dov_1"},
        },
    )
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-delivery-1",
                "rule_id": "rule_1",
                "data_primary_key": "pk-1",
                "violation_reason": "customer_id differs from golden source",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "rule_version_id": "rule_version_1",
                    "engine_type": "gx",
                    "delivery_id": "del-31",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (current_time - timedelta(hours=1, minutes=30)).isoformat(),
            },
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-delivery-1",
                "rule_id": "rule_1",
                "data_primary_key": "pk-2",
                "violation_reason": "customer_id differs from golden source",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "rule_version_id": "rule_version_1",
                    "engine_type": "gx",
                    "delivery_id": "del-31",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (current_time - timedelta(hours=1)).isoformat(),
            },
        ]
    )

    out = await exception_report_endpoints.get_delivery_exception_summary(
        request=SimpleNamespace(headers={}, state=SimpleNamespace(user_id=None, auth_claims=None)),
        delivery_id="del-31",
        lookback_amount=24,
        lookback_unit="hours",
        status=None,
        rule_name=None,
        data_object_name=None,
        search=None,
        reason_code=None,
        suite_id=None,
        data_object_version_id=None,
        rule_version_id=None,
        repository=repo,
        projection_repository=repo,
        rules_repository=repo,
        data_catalog_repository=repo,
        admin_repository=repo,
    )

    assert out.deliveryId == "del-31"
    assert out.dataObjectVersionId == "dov_1"
    assert out.executionRunIds == ["run-delivery-1"]
    assert out.dataObjectVersionIds == ["dov_1"]
    assert out.analytics.totalFailedRecords == 2
    assert out.analytics.topReasons[0].reasonCode == "value_mismatch"
    assert out.analytics.topReasons[0].total == 2


@pytest.mark.anyio
async def test_get_execution_plan_exception_summary_returns_reason_fluctuations() -> None:
    repo = _Repo()
    current_time = datetime.now(UTC)
    await repo.create_run(
        run_id="run-plan-1a",
        suite_id="gx_suite_1",
        suite_version=1,
        rule_id="rule_1",
        rule_version_id="rule_version_1",
        correlation_id="corr-plan-1a",
        requested_by="user-1",
        engine_type="gx",
        engine_target="pyspark",
        execution_shape="single_object",
        status="failed",
        submitted_at=(current_time - timedelta(hours=6)).isoformat(),
        execution_contract={
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "resolved_data_object_version_id": "dov_1",
            "traceability": {"data_object_version_id": "dov_1"},
        },
        handoff_payload={
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "run_plan_id": "run-plan-1",
        },
    )
    await repo.create_run(
        run_id="run-plan-1b",
        suite_id="gx_suite_1",
        suite_version=1,
        rule_id="rule_1",
        rule_version_id="rule_version_1",
        correlation_id="corr-plan-1b",
        requested_by="user-1",
        engine_type="gx",
        engine_target="pyspark",
        execution_shape="single_object",
        status="failed",
        submitted_at=(current_time - timedelta(hours=2)).isoformat(),
        execution_contract={
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "resolved_data_object_version_id": "dov_1",
            "traceability": {"data_object_version_id": "dov_1"},
        },
        handoff_payload={
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "run_plan_id": "run-plan-1",
        },
    )
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-plan-1a",
                "rule_id": "rule_1",
                "data_primary_key": "pk-1",
                "violation_reason": "customer_id differs from golden source",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "rule_version_id": "rule_version_1",
                    "engine_type": "gx",
                    "execution_plan_id": "run-plan-1",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (current_time - timedelta(hours=5, minutes=30)).isoformat(),
            },
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-plan-1b",
                "rule_id": "rule_1",
                "data_primary_key": "pk-2",
                "violation_reason": "customer_id differs from golden source",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "rule_version_id": "rule_version_1",
                    "engine_type": "gx",
                    "execution_plan_id": "run-plan-1",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (current_time - timedelta(hours=1, minutes=30)).isoformat(),
            },
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-plan-1b",
                "rule_id": "rule_1",
                "data_primary_key": "pk-3",
                "violation_reason": "customer_id differs from golden source",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "rule_version_id": "rule_version_1",
                    "engine_type": "gx",
                    "execution_plan_id": "run-plan-1",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (current_time - timedelta(hours=1)).isoformat(),
            },
        ]
    )

    class _PlanRepo:
        async def get_plan(self, run_plan_id: str):
            return SimpleNamespace(runPlanId=run_plan_id, currentActiveVersionId="run-plan-version-3")

    out = await exception_report_endpoints.get_execution_plan_exception_summary(
        request=SimpleNamespace(headers={}, state=SimpleNamespace(user_id=None, auth_claims=None)),
        execution_plan_id="run-plan-1",
        lookback_amount=24,
        lookback_unit="hours",
        status=None,
        rule_name=None,
        data_object_name=None,
        search=None,
        reason_code="value_mismatch",
        suite_id=None,
        data_object_version_id=None,
        rule_version_id=None,
        repository=repo,
        projection_repository=repo,
        rules_repository=repo,
        data_catalog_repository=repo,
        validation_run_plan_repository=_PlanRepo(),
        admin_repository=repo,
    )

    assert out.executionPlanId == "run-plan-1"
    assert out.currentActiveVersionId == "run-plan-version-3"
    assert out.executionRunIds == ["run-plan-1a", "run-plan-1b"]
    assert out.dataObjectVersionIds == ["dov_1"]
    assert out.analytics.totalFailedRecords == 3
    assert out.analytics.reasonFluctuations[0].reasonCode == "value_mismatch"
    assert out.analytics.reasonFluctuations[0].netChange > 0
    assert repo.last_reason_analytics_summary_kwargs is not None
    assert repo.last_reason_analytics_summary_kwargs["reason_codes"] == ["value_mismatch"]


@pytest.mark.anyio
async def test_export_delivery_exception_summary_returns_markdown_attachment() -> None:
    repo = _Repo()
    current_time = datetime.now(UTC)
    await repo.create_run(
        run_id="run-delivery-export-1",
        suite_id="gx_suite_1",
        suite_version=1,
        rule_id="rule_1",
        rule_version_id="rule_version_1",
        correlation_id="corr-delivery-export-1",
        requested_by="user-1",
        engine_type="gx",
        engine_target="pyspark",
        execution_shape="single_object",
        status="failed",
        submitted_at=(current_time - timedelta(hours=2)).isoformat(),
        execution_contract={
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "resolved_data_delivery_id": "del-31",
            "resolved_data_object_version_id": "dov_1",
            "traceability": {"data_object_version_id": "dov_1"},
        },
    )
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-delivery-export-1",
                "rule_id": "rule_1",
                "data_primary_key": "pk-1",
                "violation_reason": "customer_id differs from golden source",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "rule_version_id": "rule_version_1",
                    "engine_type": "gx",
                    "delivery_id": "del-31",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (current_time - timedelta(hours=1)).isoformat(),
            }
        ]
    )

    response = await exception_report_endpoints.export_delivery_exception_summary(
        request=SimpleNamespace(headers={}, state=SimpleNamespace(user_id=None, auth_claims=None)),
        delivery_id="del-31",
        format="markdown",
        lookback_amount=24,
        lookback_unit="hours",
        status=None,
        rule_name=None,
        data_object_name=None,
        search=None,
        reason_code=None,
        repository=repo,
        projection_repository=repo,
        rules_repository=repo,
        data_catalog_repository=repo,
        admin_repository=repo,
    )

    assert isinstance(response, Response)
    assert response.media_type == "text/markdown"
    assert response.headers["content-disposition"] == "attachment; filename=delivery-exception-summary-del-31.md"
    assert b"Exception Summary Report: delivery del-31" in response.body
    assert b"value_mismatch" in response.body


@pytest.mark.anyio
async def test_export_delivery_exception_summary_redacts_identifiers_for_reader_role() -> None:
    repo = _Repo()
    repo.current_user = SimpleNamespace(
        id="user-reader",
        name="Reader User",
        email="reader@example.com",
        granted_scopes=[],
        workspace_roles=[SimpleNamespace(workspace_id="retail-banking", role="exception-fact-reader")],
    )
    current_time = datetime.now(UTC)
    await repo.create_run(
        run_id="run-delivery-export-reader",
        suite_id="gx_suite_1",
        suite_version=1,
        rule_id="rule_1",
        rule_version_id="rule_version_1",
        correlation_id="corr-delivery-export-reader",
        requested_by="user-1",
        engine_type="gx",
        engine_target="pyspark",
        execution_shape="single_object",
        status="failed",
        submitted_at=(current_time - timedelta(hours=2)).isoformat(),
        execution_contract={
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "resolved_data_delivery_id": "del-31",
            "resolved_data_object_version_id": "dov_1",
            "traceability": {"data_object_version_id": "dov_1"},
        },
    )
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-delivery-export-reader",
                "rule_id": "rule_1",
                "data_primary_key": "pk-1",
                "violation_reason": "customer_id differs from golden source",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "rule_version_id": "rule_version_1",
                    "engine_type": "gx",
                    "delivery_id": "del-31",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (current_time - timedelta(hours=1)).isoformat(),
            }
        ]
    )

    response = await exception_report_endpoints.export_delivery_exception_summary(
        request=SimpleNamespace(headers={}, state=SimpleNamespace(user_id=None, auth_claims=None)),
        delivery_id="del-31",
        format="markdown",
        lookback_amount=24,
        lookback_unit="hours",
        status=None,
        rule_name=None,
        data_object_name=None,
        search=None,
        reason_code=None,
        repository=repo,
        projection_repository=repo,
        rules_repository=repo,
        data_catalog_repository=repo,
        admin_repository=repo,
    )

    assert isinstance(response, Response)
    assert response.media_type == "text/markdown"
    assert b"value_mismatch" in response.body
    assert b"run-delivery-export-reader" not in response.body
    assert b"dov_1" not in response.body
    assert b"Execution runs: none" in response.body
    assert b"Data object versions: none" in response.body


@pytest.mark.anyio
async def test_export_execution_plan_exception_summary_returns_csv_attachment() -> None:
    repo = _Repo()
    current_time = datetime.now(UTC)
    await repo.create_run(
        run_id="run-plan-export-1a",
        suite_id="gx_suite_1",
        suite_version=1,
        rule_id="rule_1",
        rule_version_id="rule_version_1",
        correlation_id="corr-plan-export-1a",
        requested_by="user-1",
        engine_type="gx",
        engine_target="pyspark",
        execution_shape="single_object",
        status="failed",
        submitted_at=(current_time - timedelta(hours=6)).isoformat(),
        execution_contract={
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "resolved_data_object_version_id": "dov_1",
            "traceability": {"data_object_version_id": "dov_1"},
        },
        handoff_payload={
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "run_plan_id": "run-plan-1",
        },
    )
    await repo.create_run(
        run_id="run-plan-export-1b",
        suite_id="gx_suite_1",
        suite_version=1,
        rule_id="rule_1",
        rule_version_id="rule_version_1",
        correlation_id="corr-plan-export-1b",
        requested_by="user-1",
        engine_type="gx",
        engine_target="pyspark",
        execution_shape="single_object",
        status="failed",
        submitted_at=(current_time - timedelta(hours=2)).isoformat(),
        execution_contract={
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "resolved_data_object_version_id": "dov_1",
            "traceability": {"data_object_version_id": "dov_1"},
        },
        handoff_payload={
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "run_plan_id": "run-plan-1",
        },
    )
    await repo.save_violations(
        [
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-plan-export-1a",
                "rule_id": "rule_1",
                "data_primary_key": "pk-1",
                "violation_reason": "customer_id differs from golden source",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "rule_version_id": "rule_version_1",
                    "engine_type": "gx",
                    "execution_plan_id": "run-plan-1",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (current_time - timedelta(hours=5, minutes=30)).isoformat(),
            },
            {
                "data_object_version_id": "dov_1",
                "execution_run_id": "run-plan-export-1b",
                "rule_id": "rule_1",
                "data_primary_key": "pk-2",
                "violation_reason": "customer_id differs from golden source",
                "ops_metadata": {
                    "validation_artifact_id": "gx_suite_1",
                    "validation_artifact_version": 1,
                    "rule_version_id": "rule_version_1",
                    "engine_type": "gx",
                    "execution_plan_id": "run-plan-1",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                },
                "detected_at": (current_time - timedelta(hours=1)).isoformat(),
            },
        ]
    )

    class _PlanRepo:
        async def get_plan(self, run_plan_id: str):
            return SimpleNamespace(runPlanId=run_plan_id, currentActiveVersionId="run-plan-version-3")

    response = await exception_report_endpoints.export_execution_plan_exception_summary(
        request=SimpleNamespace(headers={}, state=SimpleNamespace(user_id=None, auth_claims=None)),
        execution_plan_id="run-plan-1",
        format="csv",
        lookback_amount=24,
        lookback_unit="hours",
        status=None,
        rule_name=None,
        data_object_name=None,
        search=None,
        reason_code="value_mismatch",
        repository=repo,
        projection_repository=repo,
        rules_repository=repo,
        data_catalog_repository=repo,
        validation_run_plan_repository=_PlanRepo(),
        admin_repository=repo,
    )

    assert isinstance(response, Response)
    assert response.media_type == "text/csv"
    assert response.headers["content-disposition"] == "attachment; filename=execution-plan-exception-summary-run-plan-1.csv"
    assert b"scope_kind,scope_id,reason_code,reason_text,total_failed_records" in response.body
    assert b"execution_plan,run-plan-1,value_mismatch" in response.body



async def _seed_report_run(repo: _Repo, *, run_id: str = "run-report-1", engine_type: str = "gx") -> dict:
    return await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": run_id,
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "rule_id": "rule_1",
                "rule_version_id": "rule_version_1",
                "correlation_id": "corr-report-1",
                "requested_by": "user-1",
                "engine_type": engine_type,
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "pending",
                "submitted_at": "2026-04-10T08:00:00Z",
                "execution_contract": {
                    "engineType": engine_type,
                    "engineTarget": "pyspark",
                    "executionShape": "single_object",
                    "resolvedDataDeliveryId": "delivery-1",
                    "resolvedDeliveryLocation": "s3://deliveries/orders/2026-04-10",
                    "deliveryResolutionMode": "specific_delivery",
                    "run_plan_id": "run-plan-1",
                    "run_plan_version_id": "run-plan-version-3",
                    "traceability": {
                        "dataObjectVersionId": "dov_1",
                        "ruleId": "rule_1",
                        "ruleVersionId": "rule_version_1",
                        "gxSuiteId": "gx_suite_1",
                        "gxSuiteVersion": 1,
                        "artifactKey": "artifact_1",
                    },
                },
                "handoff_payload": {
                    "runId": run_id,
                    "correlationId": "corr-report-1",
                    "engineType": engine_type,
                    "run_plan_id": "run-plan-1",
                    "run_plan_version_id": "run-plan-version-3",
                    "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1"]},
                    "delivery_snapshot": {
                        "engine_type": engine_type,
                        "resolved_data_object_version_id": "dov_1",
                        "resolved_data_delivery_id": "delivery-1",
                        "resolved_delivery_location": "s3://deliveries/orders/2026-04-10",
                        "delivery_resolution_mode": "specific_delivery",
                    },
                },
                "result_summary": {},
                "diagnostics": [],
            }
        )
    )


@pytest.mark.anyio
async def test_report_gx_execution_run_persists_diagnostics_as_violations() -> None:
    repo = _Repo()
    await _seed_report_run(repo)

    out = await gx_endpoints.report_gx_execution_run(
        run_id="run-report-1",
        body=gx_endpoints.GxExecutionRunReportRequestView.model_validate(
            {
                "new_status": "failed",
                "changed_by": "worker-1",
                "result_summary": {
                    "results": [
                        {
                            "dataObjectVersionId": "dov_1",
                            "ok": False,
                        }
                    ]
                },
                "diagnostics": [
                    {
                        "dataObjectVersionId": "dov_1",
                        "rowIdentifier": "order_id=42",
                        "reason": "expectation_failed",
                        "expectationType": "expect_column_values_to_not_be_null",
                        "message": "Expectation failed",
                    }
                ],
                "failure_code": "GX_VALIDATION_FAILED",
                "failure_message": "One or more expectations failed",
            }
        ),
        repository=repo,
        violation_repository=repo,
        projection_repository=None,
    )

    assert out.status == "failed"
    assert out.resultSummary == {"results": [{"dataObjectVersionId": "dov_1", "ok": False}]}
    assert repo.last_run_create_kwargs is not None
    assert repo.last_save_violations_kwargs is not None
    assert len(repo.last_save_violations_kwargs) == 1
    assert repo.last_violation_save_kwargs is not None
    assert repo.last_violation_save_kwargs.dataObjectVersionId == "dov_1"
    assert repo.last_violation_save_kwargs.violationReason == "Expectation failed"
    assert repo.last_violation_save_kwargs.dataPrimaryKey == "order_id=42"
    assert repo.last_violation_save_kwargs.opsMetadata["record_identifier_type"] == "business_key"
    assert repo.last_violation_save_kwargs.opsMetadata["record_identifier_value"] == "order_id=42"
    assert repo.last_violation_save_kwargs.opsMetadata["reason_code"] == "completeness_not_null_violation"
    assert repo.last_violation_save_kwargs.opsMetadata["reason_text"] == "Expectation failed"
    assert repo.last_violation_save_kwargs.opsMetadata["engine_type"] == "gx"
    assert repo.last_violation_save_kwargs.opsMetadata["expectation_type"] == "expect_column_values_to_not_be_null"
    assert repo.last_violation_save_kwargs.opsMetadata["delivery_id"] == "delivery-1"
    assert repo.last_violation_save_kwargs.opsMetadata["delivery_location"] == "s3://deliveries/orders/2026-04-10"
    assert repo.last_violation_save_kwargs.opsMetadata["execution_plan_id"] == "run-plan-1"
    assert repo.last_violation_save_kwargs.opsMetadata["execution_plan_version_id"] == "run-plan-version-3"
    assert repo.last_violation_save_kwargs.opsMetadata["validation_artifact_id"] == "gx_suite_1"
    assert repo.last_violation_save_kwargs.opsMetadata["validation_artifact_version"] == 1
    assert repo.last_violation_save_kwargs.opsMetadata["artifact_key"] == "artifact_1"
    assert repo.last_violation_save_kwargs.opsMetadata["failure_class"] == "expectation_failed"


@pytest.mark.anyio
async def test_report_gx_execution_run_does_not_persist_generic_failure_violation_when_diagnostics_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _Repo()
    await _seed_report_run(repo, run_id="run-report-2")

    def _unexpected_exception_storage_service(**_: Any) -> None:
        raise AssertionError("exception storage should not be initialized when diagnostics are absent")

    monkeypatch.setattr(gx_endpoints, "build_exception_storage_service", _unexpected_exception_storage_service)

    out = await gx_endpoints.report_gx_execution_run(
        run_id="run-report-2",
        body=gx_endpoints.GxExecutionRunReportRequestView.model_validate(
            {
                "new_status": "failed",
                "changed_by": "worker-1",
                "result_summary": {
                    "results": [
                        {
                            "data_object_version_id": "dov_1",
                            "ok": False,
                        }
                    ]
                },
                "diagnostics": [],
                "failure_code": "GX_WORKER_EXECUTION_ERROR",
                "failure_message": "Worker failed before diagnostics were available",
            }
        ),
        repository=repo,
        violation_repository=repo,
        projection_repository=None,
    )

    assert out.status == "failed"
    assert repo.last_save_violations_kwargs is None
    assert repo.last_violation_save_kwargs is None


@pytest.mark.anyio
async def test_report_gx_execution_run_persists_dataset_level_diagnostic_without_record_identifier() -> None:
    repo = _Repo()
    await _seed_report_run(repo, run_id="run-report-3")

    updated = await gx_endpoints.report_gx_execution_run(
        run_id="run-report-3",
        body=gx_endpoints.GxExecutionRunReportRequestView.model_validate(
            {
                "new_status": "failed",
                "changed_by": "worker-1",
                "result_summary": {
                    "results": [
                        {
                            "dataObjectVersionId": "dov_1",
                            "ok": False,
                        }
                    ]
                },
                "diagnostics": [
                    {
                        "dataObjectVersionId": "dov_1",
                        "reason": "expectation_failed",
                        "message": "Expectation failed",
                    }
                ],
                "failure_code": "GX_VALIDATION_FAILED",
                "failure_message": "One or more expectations failed",
            }
        ),
        repository=repo,
        violation_repository=repo,
        projection_repository=None,
    )

    assert updated.status == "failed"
    assert repo.last_save_violations_kwargs is not None
    assert len(repo.last_save_violations_kwargs) == 1
    assert repo.last_violation_save_kwargs is not None
    assert repo.last_violation_save_kwargs.opsMetadata["record_identifier_type"] == "data_object_version"
    assert repo.last_violation_save_kwargs.opsMetadata["record_identifier_value"] == "dov_1"


@pytest.mark.anyio
async def test_report_gx_execution_run_rejects_diagnostic_without_normalized_reason() -> None:
    repo = _Repo()
    await _seed_report_run(repo, run_id="run-report-3b")

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.report_gx_execution_run(
            run_id="run-report-3b",
            body=gx_endpoints.GxExecutionRunReportRequestView.model_validate(
                {
                    "new_status": "failed",
                    "changed_by": "worker-1",
                    "result_summary": {
                        "results": [
                            {
                                "dataObjectVersionId": "dov_1",
                                "ok": False,
                            }
                        ]
                    },
                    "diagnostics": [
                        {
                            "dataObjectVersionId": "dov_1",
                            "rowIdentifier": "order_id=42",
                        }
                    ],
                }
            ),
            repository=repo,
            violation_repository=repo,
            projection_repository=None,
        )

    assert error.value.status_code == 503
    assert error.value.detail["error"] == "violation_persistence_unavailable"
    assert "normalized failure reason" in error.value.detail["message"]


@pytest.mark.anyio
async def test_report_gx_execution_run_rejects_engine_without_exception_fact_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _Repo()
    await _seed_report_run(repo, run_id="run-report-4", engine_type="soda")

    def _unexpected_exception_storage_service(**_: Any) -> None:
        raise AssertionError("exception storage should not be initialized when engine capability gate fails")

    monkeypatch.setattr(gx_endpoints, "build_exception_storage_service", _unexpected_exception_storage_service)

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.report_gx_execution_run(
            run_id="run-report-4",
            body=gx_endpoints.GxExecutionRunReportRequestView.model_validate(
                {
                    "new_status": "failed",
                    "changed_by": "worker-1",
                    "result_summary": {
                        "results": [
                            {
                                "dataObjectVersionId": "dov_1",
                                "ok": False,
                            }
                        ]
                    },
                    "diagnostics": [
                        {
                            "dataObjectVersionId": "dov_1",
                            "rowIdentifier": "order_id=42",
                            "reason": "expectation_failed",
                            "message": "Expectation failed",
                        }
                    ],
                    "failure_code": "SODA_VALIDATION_FAILED",
                    "failure_message": "One or more checks failed",
                }
            ),
            repository=repo,
            violation_repository=repo,
            projection_repository=None,
        )

    assert error.value.status_code == 503
    assert error.value.detail["error"] == "violation_persistence_unavailable"
    assert error.value.detail["engine_type"] == "soda"
    assert error.value.detail["capability_error"] == "row_level_exception_facts_unsupported"
    assert "does not support row-level exception facts" in error.value.detail["message"]
    assert repo.last_save_violations_kwargs is None


@pytest.mark.anyio
async def test_start_gx_suite_run_returns_404_when_not_found() -> None:
    repo = _Repo()
    repo.get_payload = None
    request = SimpleNamespace(headers={})

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.start_gx_suite_run(
            request=request,
            suite_id="missing-suite",
            suite_version=None,
            status="active",
            repository=repo,
            execution_run_repository=repo,
        )

    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_start_gx_suite_run_rejects_missing_execution_contract() -> None:
    repo = _Repo()
    repo.get_payload = {**repo.list_payload[0], "executionContract": None}
    request = SimpleNamespace(headers={})

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.start_gx_suite_run(
            request=request,
            suite_id="gx_suite_1",
            suite_version=None,
            status="active",
            repository=repo,
            execution_run_repository=repo,
        )

    assert error.value.status_code == 422
    assert isinstance(error.value.detail, dict)
    assert error.value.detail["error"] == "gx_suite_not_runnable"
    assert error.value.detail["reason"] == "missing_execution_contract"


@pytest.mark.anyio
async def test_start_gx_suite_run_rejects_empty_expectations() -> None:
    repo = _Repo()
    broken_suite = {**repo.list_payload[0]}
    broken_gx_suite = {**broken_suite["gxSuite"], "expectations": []}
    broken_suite["gxSuite"] = broken_gx_suite
    repo.get_payload = broken_suite
    request = SimpleNamespace(headers={})

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.start_gx_suite_run(
            request=request,
            suite_id="gx_suite_1",
            suite_version=None,
            status="active",
            repository=repo,
            execution_run_repository=repo,
        )

    assert error.value.status_code == 422
    assert isinstance(error.value.detail, dict)
    assert error.value.detail["error"] == "gx_suite_not_runnable"
    assert error.value.detail["reason"] == "empty_expectations"


@pytest.mark.anyio
async def test_schedule_gx_suite_run_queues_dispatch_payload(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={"X-Correlation-ID": "corr-sched-123"})
    scheduled_at = datetime(2026, 4, 6, 13, 15, tzinfo=UTC)
    captured: dict[str, object] = {}

    async def _fake_redis_lpush(redis_url: str, queue_key: str, payload: dict) -> None:
        captured["redis_url"] = redis_url
        captured["queue_key"] = queue_key
        captured["payload"] = payload

    async def _worker_available(redis_url: str, queue_key: str) -> None:
        return None

    _patch_gx_redis_url(monkeypatch, "redis://example")
    _patch_gx_redis_lpush(monkeypatch, _fake_redis_lpush)
    _patch_gx_worker_heartbeat(monkeypatch, _worker_available)
    monkeypatch.setattr(gx_endpoints, "get_data_catalog_repository", lambda: repo)

    out = await gx_endpoints.schedule_gx_suite_run(
        request=request,
        suite_id="gx_suite_1",
        request_body=SimpleNamespace(scheduledAt=scheduled_at),
        suite_version=2,
        status="active",
        repository=repo,
        execution_run_repository=repo,
    )

    assert out.suiteId == "gx_suite_1"
    assert out.dispatchMode == "queued"
    assert out.executorTarget == "dq-engine"
    assert out.queueKey == "dq-gx:execution-dispatch"
    assert out.businessKey == "corr-sched-123"
    assert out.correlationId == "corr-sched-123"
    assert out.model_dump(by_alias=True)["business_key"] == "corr-sched-123"
    assert "run_id" not in out.model_dump(by_alias=True)
    assert "queue_message_id" not in out.model_dump(by_alias=True)
    assert out.scheduledAt == scheduled_at.isoformat()
    assert captured["redis_url"] == "redis://example"
    assert captured["queue_key"] == "dq-gx:execution-dispatch"
    assert captured["payload"]["queue_message_id"] == out.runId
    assert captured["payload"]["scheduled_at"] == scheduled_at.isoformat()
    assert repo.last_run_create_kwargs is not None
    assert repo.last_run_create_kwargs["status"] == "pending"
    assert repo.last_run_create_kwargs["status_details"]["dispatch_mode"] == "queued"
    assert repo.last_run_create_kwargs["handoff_payload"]["status_details"]["dispatch_mode"] == "queued"


@pytest.mark.anyio
async def test_schedule_join_pair_gx_suite_run_queues_materialization_handoff(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={"X-Correlation-ID": "corr-sched-join-123"})
    scheduled_at = datetime(2026, 4, 6, 13, 15, tzinfo=UTC)
    captured: dict[str, object] = {}
    join_pair_suite = {
        **repo.list_payload[0],
        "executionContract": {
            "engineType": "gx",
            "engineTarget": "pyspark",
            "executionShape": "join_pair",
            "traceability": {
                "ruleId": "rule_1",
                "ruleVersionId": "rule_version_1",
                "gxSuiteId": "gx_suite_1",
                "gxSuiteVersion": 1,
                "dataObjectVersionId": "dov_1",
            },
            "sourceMaterialization": {
                "landingZoneArtifactId": "lz_gx_suite_1",
                "landingZoneVersionId": "lzv_1",
                "outputLocation": "s3://dq-landing-zone-retail-banking/gx/join-pairs/suite_id=gx_suite_1/suite_version=1/format=parquet",
                "joinType": "inner",
                "joinKeys": ["order_id"],
                "joinKeyPairs": [{"leftAttribute": "order_id", "rightAttribute": "order_id"}],
                "leftSource": {"dataObjectId": "do-left", "dataObjectVersionId": "dov_1", "datasetId": "ds-left"},
                "rightSource": {"dataObjectId": "do-right", "dataObjectVersionId": "dov_2", "datasetId": "ds-right"},
            },
        },
        "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1", "dov_2"]},
    }
    repo.get_payload = join_pair_suite

    async def _fake_redis_lpush(redis_url: str, queue_key: str, payload: dict) -> None:
        captured["redis_url"] = redis_url
        captured["queue_key"] = queue_key
        captured["payload"] = payload

    async def _worker_available(redis_url: str, queue_key: str) -> None:
        return None

    _patch_gx_redis_url(monkeypatch, "redis://example")
    _patch_gx_redis_lpush(monkeypatch, _fake_redis_lpush)
    _patch_gx_worker_heartbeat(monkeypatch, _worker_available)
    monkeypatch.setattr(gx_endpoints, "get_data_catalog_repository", lambda: repo)

    out = await gx_endpoints.schedule_gx_suite_run(
        request=request,
        suite_id="gx_suite_1",
        request_body=SimpleNamespace(scheduledAt=scheduled_at),
        suite_version=2,
        status="active",
        repository=repo,
        execution_run_repository=repo,
    )

    assert out.queueKey == "dq-gx:join-pair-materialize"
    assert captured["queue_key"] == "dq-gx:join-pair-materialize"
    assert captured["payload"]["next_dispatch_payload"]["queue_key"] == "dq-gx:execution-dispatch"
    assert repo.last_run_create_kwargs is not None
    assert repo.last_run_create_kwargs["handoff_payload"]["queue_key"] == "dq-gx:join-pair-materialize"
    assert repo.last_run_create_kwargs["status_details"]["pre_dispatch_phase"] == "join_pair_materialization"
    assert repo.last_run_create_kwargs["handoff_payload"]["status_details"]["pre_dispatch_phase"] == "join_pair_materialization"


@pytest.mark.anyio
async def test_schedule_gx_suite_run_rejects_missing_dispatch_queue(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={})
    scheduled_at = datetime(2026, 4, 6, 13, 15, tzinfo=UTC)

    _patch_gx_redis_url(monkeypatch, None)

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.schedule_gx_suite_run(
            request=request,
            suite_id="gx_suite_1",
            request_body=SimpleNamespace(scheduledAt=scheduled_at),
            suite_version=None,
            status="active",
            repository=repo,
            execution_run_repository=repo,
        )

    assert error.value.status_code == 503
    assert repo.last_run_create_kwargs is None


@pytest.mark.anyio
async def test_schedule_gx_suite_run_rejects_missing_worker_heartbeat(monkeypatch) -> None:
    repo = _Repo()
    request = SimpleNamespace(headers={})
    scheduled_at = datetime(2026, 4, 6, 13, 15, tzinfo=UTC)

    async def _reject_worker(redis_url: str, queue_key: str) -> None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "dispatch_worker_unavailable",
                "queue_key": queue_key,
            },
        )

    _patch_gx_redis_url(monkeypatch, "redis://example")
    _patch_gx_worker_heartbeat(monkeypatch, _reject_worker)

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.schedule_gx_suite_run(
            request=request,
            suite_id="gx_suite_1",
            request_body=SimpleNamespace(scheduledAt=scheduled_at),
            suite_version=None,
            status="active",
            repository=repo,
            execution_run_repository=repo,
        )

    assert error.value.status_code == 503
    assert isinstance(error.value.detail, dict)
    assert error.value.detail["error"] == "dispatch_worker_unavailable"
    assert repo.last_run_create_kwargs is None


@pytest.mark.anyio
async def test_save_gx_suite_persists_envelope() -> None:
    repo = _Repo()
    body = gx_endpoints.GxArtifactEnvelopeView.model_validate(repo.list_payload[0])

    out = await gx_endpoints.save_gx_suite(body=body, status="deprecated", repository=repo)

    assert out.suiteId == "gx_suite_1"
    assert repo.last_save_kwargs is not None
    assert repo.last_save_kwargs["status"] == "deprecated"
    assert repo.last_save_kwargs["envelope"].validationArtifactId == "gx_suite_1"


@pytest.mark.anyio
async def test_save_gx_suite_emits_custom_span(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class _Span:
        def __init__(self, attrs: dict[str, object]) -> None:
            self.attrs = attrs

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: object) -> None:
            self.attrs[key] = value

        def record_exception(self, exc: Exception) -> None:
            return None

        def set_status(self, status) -> None:
            return None

    @contextmanager
    def _fake_traced_span(name: str, **attrs: object):
        calls.append((name, dict(attrs)))
        yield _Span(calls[-1][1])

    monkeypatch.setattr(gx_endpoints, "traced_span", _fake_traced_span)
    repo = _Repo()
    body = gx_endpoints.GxArtifactEnvelopeView.model_validate(repo.list_payload[0])

    out = await gx_endpoints.save_gx_suite(body=body, status="deprecated", repository=repo)

    assert out.suiteId == "gx_suite_1"
    assert calls[0][0] == "gx.suite.save"
    assert calls[0][1]["suite_id"] == "gx_suite_1"
    assert calls[0][1]["suite_status"] == "deprecated"
    assert calls[0][1]["gx_save_result"] == "saved"


@pytest.mark.anyio
async def test_save_gx_suite_passes_expected_hash() -> None:
    repo = _Repo()
    body = gx_endpoints.GxArtifactEnvelopeView.model_validate(repo.list_payload[0])

    await gx_endpoints.save_gx_suite(
        body=body,
        status="active",
        expected_existing_hash="abc123",
        response=Response(),
        repository=repo,
    )

    assert repo.last_save_kwargs is not None
    assert repo.last_save_kwargs["expected_existing_hash"] == "abc123"


@pytest.mark.anyio
async def test_save_gx_suite_returns_409_on_hash_conflict() -> None:
    repo = _Repo()
    body = gx_endpoints.GxArtifactEnvelopeView.model_validate(repo.list_payload[0])

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.save_gx_suite(
            body=body,
            status="active",
            expected_existing_hash="reject",
            response=Response(),
            repository=repo,
        )

    assert error.value.status_code == 409


@pytest.mark.anyio
async def test_patch_gx_suite_status_updates_and_returns_envelope() -> None:
    repo = _Repo()

    out = await gx_endpoints.patch_gx_suite_status(
        suite_id="gx_suite_1",
        status="deprecated",
        suite_version=None,
        repository=repo,
    )

    assert out.suiteId == "gx_suite_1"
    assert repo.last_patch_kwargs is not None
    assert repo.last_patch_kwargs["artifact_id"] == "gx_suite_1"
    assert repo.last_patch_kwargs["new_status"] == "deprecated"
    assert repo.last_patch_kwargs["artifact_version"] is None


@pytest.mark.anyio
async def test_patch_gx_suite_status_with_explicit_version() -> None:
    repo = _Repo()

    await gx_endpoints.patch_gx_suite_status(
        suite_id="gx_suite_1",
        status="disabled",
        suite_version=3,
        repository=repo,
    )

    assert repo.last_patch_kwargs is not None
    assert repo.last_patch_kwargs["artifact_version"] == 3
    assert repo.last_patch_kwargs["new_status"] == "disabled"


@pytest.mark.anyio
async def test_patch_gx_suite_status_returns_404_when_not_found() -> None:
    repo = _Repo()

    with pytest.raises(HTTPException) as error:
        await gx_endpoints.patch_gx_suite_status(
            suite_id="missing-suite",
            status="deprecated",
            suite_version=None,
            repository=repo,
        )

    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_get_gx_suite_status_history_returns_trail() -> None:
    repo = _Repo()

    out = await gx_endpoints.get_gx_suite_status_history(
        suite_id="gx_suite_1",
        suite_version=None,
        repository=repo,
    )

    assert len(out) == 2
    assert out[0].toStatus == "active"
    assert out[0].fromStatus is None
    assert out[1].toStatus == "deprecated"
    assert out[1].fromStatus == "active"
    assert out[1].reason == "superseded by v2"
    assert repo.last_history_kwargs == {"artifact_id": "gx_suite_1", "artifact_version": None}


@pytest.mark.anyio
async def test_get_gx_suite_status_history_filters_by_version() -> None:
    repo = _Repo()

    out = await gx_endpoints.get_gx_suite_status_history(
        suite_id="gx_suite_1",
        suite_version=1,
        repository=repo,
    )

    assert repo.last_history_kwargs == {"artifact_id": "gx_suite_1", "artifact_version": 1}
    assert len(out) == 2


@pytest.mark.anyio
async def test_get_gx_suite_status_history_returns_empty_list_for_unknown_suite() -> None:
    repo = _Repo()

    out = await gx_endpoints.get_gx_suite_status_history(
        suite_id="missing-suite",
        suite_version=None,
        repository=repo,
    )

    assert out == []
