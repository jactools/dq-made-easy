import re
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import and_
from sqlalchemy import select

from app.application.services import evaluate_expression_on_context_with_details
from app.domain.entities.testing import (
    BatchTestRequestEntity,
    BatchTestRunResultEntity,
    StoreTestProofResultEntity,
    TestDataPayloadEntity,
    TestProofEntity,
    TestRowResultEntity,
    TestRunResultEntity,
)
from app.domain.interfaces.v1.testing_repository import TestingRepository
from app.infrastructure.orm.models import AttributeCatalogRow
from app.infrastructure.orm.models import BatchTestRequestRow
from app.infrastructure.orm.models import DataObjectVersionRow
from app.infrastructure.orm.models import RuleCurrentVersionRow
from app.infrastructure.orm.models import RuleRow
from app.infrastructure.orm.models import RuleVersionRow
from app.infrastructure.orm.models import TestProofRow
from app.infrastructure.orm.session import session_scope


class PostgresTestingRepository(TestingRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @staticmethod
    def _normalize_test_proof_status(status: Any, passed: Any = None) -> str:
        normalized = str(status or "").strip().lower()
        if normalized in {"pending", "running", "passed", "failed"}:
            return normalized
        if passed is True:
            return "passed"
        if passed is False:
            return "failed"
        return "pending"

    @classmethod
    def _coerce_test_proof_passed(cls, status: str, passed: Any) -> bool | None:
        if status == "passed":
            return True
        if status == "failed":
            return False
        if isinstance(passed, bool):
            return passed
        return None

    @classmethod
    def _resolve_row_test_proof_status(cls, row: TestProofRow) -> str:
        proof_data = dict(getattr(row, "test_data", {}) or {})
        execution_trace = dict(proof_data.get("executionTrace") or {})
        return cls._normalize_test_proof_status(
            execution_trace.get("resultStatus") or proof_data.get("requestStatus"),
            row.passed,
        )

    @classmethod
    def _build_execution_trace(
        cls,
        *,
        test_date: str,
        proof_data: dict[str, Any],
        test_data: dict[str, Any],
        status: str,
        existing_execution_trace: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        execution_trace = dict(existing_execution_trace or {})
        execution_trace.update(dict(test_data.get("executionTrace") or {}))
        execution_trace.setdefault("executionId", f"exec-{uuid4().hex[:12]}")
        execution_trace.setdefault("correlationId", f"corr-{uuid4().hex[:12]}")
        if status in {"passed", "failed"}:
            execution_trace["executedAt"] = str(execution_trace.get("executedAt") or test_date)
        else:
            execution_trace.setdefault("executedAt", None)
        execution_trace["resultStatus"] = status
        proof_data["executionTrace"] = execution_trace
        proof_data["requestStatus"] = status
        return execution_trace

    @classmethod
    def _build_test_proof_entity(cls, row: TestProofRow) -> TestProofEntity:
        proof_data = dict(getattr(row, "test_data", {}) or {})
        execution_trace = dict(proof_data.get("executionTrace") or {})
        status = cls._resolve_row_test_proof_status(row)
        execution_trace.setdefault("executionId", f"exec-{str(row.id or '')}" if row.id else "")
        execution_trace.setdefault("correlationId", f"corr-{str(row.id or '')}" if row.id else None)
        execution_trace.setdefault("executedAt", cls._to_optional_text(row.test_date))
        execution_trace.setdefault("resultStatus", status)

        return TestProofEntity(
            id=str(row.id or ""),
            ruleId=str(row.rule_id or ""),
            testDate=cls._to_text(row.test_date),
            coverage=float(row.coverage or 0.0),
            status=status,
            recordsTestedCount=int(row.records_tested_count or 0),
            failuresFound=int(row.failures_found or 0),
            proofData=proof_data,
            executionTrace=execution_trace,
            metrics=dict(getattr(row, "metrics", {}) or {}) or None,
            diagnostics=list(getattr(row, "diagnostics", []) or []) or None,
        )

    def generate_test_data_for_version(self, version_id: str, sample_count: int = 10) -> TestDataPayloadEntity:
        generated_at = self._current_timestamp()
        with session_scope(self.database_url) as session:
            version = session.get(DataObjectVersionRow, version_id)
        if version is None:
            return TestDataPayloadEntity(
                versionId=version_id,
                versionName=None,
                dataObjectId=None,
                attributeCount=0,
                sampleCount=sample_count,
                samples=[],
                attributes=[],
                generatedAt=generated_at,
            )
        with session_scope(self.database_url) as session:
            attribute_rows = session.execute(
                select(AttributeCatalogRow)
                .where(AttributeCatalogRow.version_id == version_id)
                .order_by(AttributeCatalogRow.id)
            ).scalars().all()
        attributes = [{"id": row.id, "name": row.name, "type": row.type} for row in attribute_rows]

        samples = [
            {
                str(attr.get("name") or attr.get("id")): self._sample_value_for_attribute(attr, index)
                for attr in attributes
            }
            for index in range(sample_count)
        ]
        return TestDataPayloadEntity(
            versionId=version_id,
            versionName=version.version,
            dataObjectId=version.data_object_id,
            attributeCount=len(attributes),
            sampleCount=sample_count,
            samples=samples,
            attributes=attributes,
            generatedAt=generated_at,
        )

    def run_rule_with_generated_data(
        self,
        rule_id: str,
        version_id: str,
        sample_count: int = 10,
        compiled_expression: str | None = None,
        semantic_config: dict[str, Any] | None = None,
    ) -> TestRunResultEntity:
        generated = self.generate_test_data_for_version(version_id, sample_count)
        return self.run_rule_against_test_data(
            rule_id,
            generated.samples,
            version_id,
            compiled_expression=compiled_expression,
            semantic_config=semantic_config,
        )

    def store_test_proof(self, rule_id: str, test_data: dict) -> StoreTestProofResultEntity:
        records_tested = int(test_data.get("recordsTestedCount") or 0)
        failures_found = int(test_data.get("failuresFound") or 0)
        success_rate = ((records_tested - failures_found) / records_tested * 100) if records_tested > 0 else 0
        test_date = self._current_timestamp()
        proof_data = dict(test_data.get("proofData") or {})
        metrics = dict(test_data.get("metrics") or {}) or None
        diagnostics = list(test_data.get("diagnostics") or []) or None
        status = self._normalize_test_proof_status(test_data.get("status"), test_data.get("passed"))
        execution_trace = self._build_execution_trace(
            test_date=test_date,
            proof_data=proof_data,
            test_data=test_data,
            status=status,
        )

        proof_id = f"proof-{uuid4().hex[:12]}"
        now = datetime.now(UTC)
        with session_scope(self.database_url) as session:
            row = TestProofRow(
                id=proof_id,
                rule_id=rule_id,
                test_date=now,
                coverage=float(test_data.get("coverage") or 0),
                passed=self._coerce_test_proof_passed(status, test_data.get("passed")),
                records_tested_count=records_tested,
                failures_found=failures_found,
                success_rate=success_rate,
                test_data=proof_data,
                workspace="default",
                tested_by="system",
                created_at=now,
                metrics=metrics,
                diagnostics=diagnostics,
            )
            session.add(row)
            session.commit()

        return StoreTestProofResultEntity(
            proofId=proof_id,
            ruleId=rule_id,
            testDate=test_date,
            coverage=float(test_data.get("coverage") or 0),
            passed=status == "passed",
            recordsTestedCount=records_tested,
            failuresFound=failures_found,
            successRate=success_rate,
            proofData=proof_data,
            executionTrace=execution_trace,
            metrics=metrics,
            diagnostics=diagnostics,
        )

    def create_test_proof(self, rule_id: str, test_data: dict, status: str = "pending") -> TestProofEntity:
        normalized_status = self._normalize_test_proof_status(status, test_data.get("passed"))
        test_date = self._current_timestamp()
        proof_data = dict(test_data.get("proofData") or {})
        metrics = dict(test_data.get("metrics") or {}) or None
        diagnostics = list(test_data.get("diagnostics") or []) or None
        execution_trace = self._build_execution_trace(
            test_date=test_date,
            proof_data=proof_data,
            test_data=test_data,
            status=normalized_status,
        )
        proof_id = f"proof-{uuid4().hex[:12]}"
        records_tested = int(test_data.get("recordsTestedCount") or 0)
        failures_found = int(test_data.get("failuresFound") or 0)
        success_rate = ((records_tested - failures_found) / records_tested * 100) if records_tested > 0 else 0
        now = datetime.now(UTC)

        with session_scope(self.database_url) as session:
            row = TestProofRow(
                id=proof_id,
                rule_id=rule_id,
                test_date=now,
                coverage=float(test_data.get("coverage") or 0),
                passed=self._coerce_test_proof_passed(normalized_status, test_data.get("passed")),
                records_tested_count=records_tested,
                failures_found=failures_found,
                success_rate=success_rate,
                test_data=proof_data,
                workspace="default",
                tested_by="system",
                created_at=now,
                metrics=metrics,
                diagnostics=diagnostics,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._build_test_proof_entity(row)

    def update_test_proof(self, proof_id: str, test_data: dict, status: str | None = None) -> TestProofEntity:
        with session_scope(self.database_url) as session:
            row = session.get(TestProofRow, proof_id)
            if row is None:
                raise KeyError(f"test_proof {proof_id} not found")

            normalized_status = self._normalize_test_proof_status(status, test_data.get("passed"))
            test_date = self._to_text(row.test_date) or self._current_timestamp()
            existing_proof_data = dict(getattr(row, "test_data", {}) or {})
            incoming_proof_data = dict(test_data.get("proofData") or {})
            proof_data = {
                **existing_proof_data,
                **incoming_proof_data,
            }
            existing_execution_trace = dict(existing_proof_data.get("executionTrace") or {})
            execution_trace = self._build_execution_trace(
                test_date=test_date,
                proof_data=proof_data,
                test_data=test_data,
                status=normalized_status,
                existing_execution_trace=existing_execution_trace,
            )

            row.coverage = float(test_data.get("coverage") if test_data.get("coverage") is not None else row.coverage or 0)
            row.records_tested_count = int(
                test_data.get("recordsTestedCount")
                if test_data.get("recordsTestedCount") is not None
                else row.records_tested_count or 0
            )
            row.failures_found = int(
                test_data.get("failuresFound")
                if test_data.get("failuresFound") is not None
                else row.failures_found or 0
            )
            row.success_rate = (
                ((int(row.records_tested_count or 0) - int(row.failures_found or 0)) / int(row.records_tested_count or 0) * 100)
                if int(row.records_tested_count or 0) > 0
                else 0
            )
            row.passed = self._coerce_test_proof_passed(normalized_status, test_data.get("passed"))
            row.test_data = proof_data
            row.metrics = (
                dict(test_data.get("metrics") or {})
                if test_data.get("metrics") is not None
                else dict(getattr(row, "metrics", {}) or {}) or None
            )
            row.diagnostics = (
                list(test_data.get("diagnostics") or [])
                if test_data.get("diagnostics") is not None
                else list(getattr(row, "diagnostics", []) or []) or None
            )
            if normalized_status in {"passed", "failed"} and execution_trace.get("executedAt"):
                row.test_date = datetime.fromisoformat(str(execution_trace["executedAt"]).replace("Z", "+00:00"))
            session.commit()
            session.refresh(row)
            return self._build_test_proof_entity(row)

    def run_rule_against_test_data(
        self,
        rule_id: str,
        test_data: list[dict],
        version_id_source: str | None = None,
        compiled_expression: str | None = None,
        semantic_config: dict[str, Any] | None = None,
    ) -> TestRunResultEntity:
        timestamp = self._current_timestamp()
        with session_scope(self.database_url) as session:
            rule_row = session.get(RuleRow, rule_id)
        rule = {
            "id": rule_row.id,
            "name": rule_row.name,
            "dimension": rule_row.dimension,
            "description": rule_row.description,
            "expression": rule_row.expression,
            "check_type": getattr(rule_row, "check_type", None),
            "check_type_params": getattr(rule_row, "check_type_params", None),
        } if rule_row is not None else {}

        version_check_type = None
        version_check_type_params = None
        if rule_row is not None:
            with session_scope(self.database_url) as session:
                current_pointer = session.get(RuleCurrentVersionRow, str(rule_row.id))
                pointer_version_id = str(getattr(current_pointer, "version_id", "") or "").strip()
                if pointer_version_id:
                    version_row = session.get(RuleVersionRow, pointer_version_id)
                    if version_row is not None:
                        version_check_type = getattr(version_row, "check_type", None)
                        version_check_type_params = getattr(version_row, "check_type_params", None)

        expression_to_execute = str(compiled_expression or rule.get("expression") or "")
        semantic_stats = self._create_semantic_stats(semantic_config)
        matcher = self._build_rule_matcher(
            expression_to_execute,
            semantic_config=semantic_config,
            semantic_stats=semantic_stats,
        )
        results: list[TestRowResultEntity] = []
        evaluation_warning: str | None = None
        for index, row in enumerate(test_data):
            try:
                passed = matcher(row)
            except ValueError as exc:
                evaluation_warning = str(exc)
                passed = False
            results.append(
                TestRowResultEntity(
                    rowIndex=index,
                    data=row,
                    passed=passed,
                    joinEvaluated=False,
                    joinMatchedContexts=0,
                )
            )

        passed_count = len([entry for entry in results if entry.passed])
        failed_count = len(results) - passed_count
        total = len(results)
        success_rate = (passed_count / total * 100) if total else 0
        check_type = str(version_check_type or rule.get("check_type") or "").strip().upper() or None
        raw_params = version_check_type_params if version_check_type_params is not None else rule.get("check_type_params")
        if isinstance(raw_params, str):
            try:
                check_type_params = json.loads(raw_params)
            except json.JSONDecodeError:
                check_type_params = {}
        else:
            check_type_params = dict(raw_params or {})
        rule_passed, required_success_rate = self._evaluate_rule_pass(
            check_type,
            check_type_params,
            success_rate,
            failed_count,
        )
        semantic_context = {
            "enabled": bool(semantic_stats.get("enabled")),
            "configured": bool(semantic_stats.get("configured")),
            "fieldAliasHits": int(semantic_stats.get("field_alias_hits", 0)),
            "valueCoercionMatches": int(semantic_stats.get("value_coercion_matches", 0)),
            "semanticCoercionUsed": bool(
                int(semantic_stats.get("field_alias_hits", 0)) > 0
                or int(semantic_stats.get("value_coercion_matches", 0)) > 0
            ),
        }

        return TestRunResultEntity(
            ruleId=rule_id,
            expression=expression_to_execute,
            testDataSource=version_id_source or "manual",
            totalTests=total,
            passedCount=passed_count,
            failedCount=failed_count,
            successRate=round(success_rate, 2),
            rulePassed=rule_passed,
            requiredSuccessRate=required_success_rate,
            timestamp=timestamp,
            results=results,
            ruleDetails={
                "name": rule.get("name", "Unknown"),
                "dimension": rule.get("dimension", "unknown"),
                "description": rule.get("description", ""),
                **({"evaluationWarning": evaluation_warning} if evaluation_warning else {}),
            },
            executionContext=(
                {
                    **({"reason": "expression-not-executable", "message": evaluation_warning} if evaluation_warning else {}),
                    "semanticMatching": semantic_context,
                }
            ),
        )

    def create_batch_test_requests(
        self,
        rule_ids: list[str],
        test_data_config: dict | None = None,
        requested_by: str | None = None,
        workspace: str | None = None,
    ) -> list[BatchTestRequestEntity]:
        config = test_data_config or {}
        actor = requested_by or "system"
        target_workspace = workspace or "default"
        requested_at = datetime.now(UTC)
        created_rows: list[BatchTestRequestEntity] = []
        with session_scope(self.database_url) as session:
            for rule_id in rule_ids:
                request_id = f"batch-{uuid4().hex[:12]}"
                row = BatchTestRequestRow(
                    id=request_id,
                    rule_id=str(rule_id),
                    requested_by=actor,
                    requested_at=requested_at,
                    test_data_config=dict(config),
                    status="pending",
                    workspace=target_workspace,
                    completed_at=None,
                    proof_id=None,
                )
                session.add(row)
                created_rows.append(
                    BatchTestRequestEntity(
                        id=request_id,
                        ruleId=str(rule_id),
                        requestedBy=actor,
                        requestedAt=self._to_text(requested_at),
                        testDataConfig=dict(config),
                        executionCorrelationId=None,
                        status="pending",
                        workspace=target_workspace,
                        completedAt=None,
                        proofId=None,
                    )
                )
            session.commit()
        return created_rows

    def list_batch_test_requests(
        self,
        workspace: str | None = None,
        status: str | None = None,
    ) -> list[BatchTestRequestEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(BatchTestRequestRow)
            filters = []
            if workspace:
                filters.append(BatchTestRequestRow.workspace == workspace)
            if status:
                filters.append(BatchTestRequestRow.status == status)
            if filters:
                stmt = stmt.where(and_(*filters))
            stmt = stmt.order_by(BatchTestRequestRow.requested_at.desc())
            rows = session.execute(stmt).scalars().all()
        return [
            BatchTestRequestEntity(
                id=str(row.id or ""),
                ruleId=str(row.rule_id or ""),
                requestedBy=str(row.requested_by or ""),
                requestedAt=self._to_text(row.requested_at),
                testDataConfig={
                    key: value
                    for key, value in dict(row.test_data_config or {}).items()
                    if key != "executionCorrelationId"
                },
                executionCorrelationId=(
                    str(dict(row.test_data_config or {}).get("executionCorrelationId") or "").strip() or None
                ),
                status=str(row.status or "pending"),
                workspace=str(row.workspace or "default"),
                completedAt=self._to_optional_text(row.completed_at),
                proofId=str(row.proof_id) if row.proof_id is not None else None,
            )
            for row in rows
        ]

    def get_batch_test_request(self, request_id: str) -> BatchTestRequestEntity | None:
        with session_scope(self.database_url) as session:
            row = session.get(BatchTestRequestRow, request_id)
        if row is None:
            return None
        return BatchTestRequestEntity(
            id=str(row.id or ""),
            ruleId=str(row.rule_id or ""),
            requestedBy=str(row.requested_by or ""),
            requestedAt=self._to_text(row.requested_at),
            testDataConfig={
                key: value
                for key, value in dict(row.test_data_config or {}).items()
                if key != "executionCorrelationId"
            },
            executionCorrelationId=(
                str(dict(row.test_data_config or {}).get("executionCorrelationId") or "").strip() or None
            ),
            status=str(row.status or "pending"),
            workspace=str(row.workspace or "default"),
            completedAt=self._to_optional_text(row.completed_at),
            proofId=str(row.proof_id) if row.proof_id is not None else None,
        )

    def run_batch_test_request(self, request_id: str) -> BatchTestRunResultEntity:
        final_status = "running"
        with session_scope(self.database_url) as session:
            row = session.get(BatchTestRequestRow, request_id)
            if row is not None and str(row.status or "") == "pending":
                row.status = "running"
                session.commit()
                config_payload = dict(getattr(row, "test_data_config", {}) or {})
                correlation_id = str(config_payload.get("executionCorrelationId") or f"corr-{uuid4().hex[:12]}")
                config_payload["executionCorrelationId"] = correlation_id
                try:
                    sample_count = int(config_payload.get("sampleCount") or 10)
                    version_id = str(config_payload.get("versionId") or "")
                    run_result = self.run_rule_with_generated_data(
                        str(row.rule_id or ""),
                        version_id,
                        sample_count=sample_count,
                    )
                    proof = self.store_test_proof(
                        str(row.rule_id or ""),
                        {
                            "coverage": float(run_result.successRate) / 100,
                            "passed": bool(run_result.failedCount == 0),
                            "recordsTestedCount": int(run_result.totalTests),
                            "failuresFound": int(run_result.failedCount),
                            "proofData": {
                                "source": "batch-test-request",
                                "requestId": request_id,
                                "testDataSource": run_result.testDataSource,
                            },
                            "executionTrace": {
                                "correlationId": correlation_id,
                            },
                        },
                    )
                    row.test_data_config = config_payload
                    row.proof_id = proof.proofId
                    row.completed_at = datetime.now(UTC)
                    row.status = "completed"
                    session.commit()
                    final_status = "completed"
                except Exception as exc:
                    error_code = str(getattr(exc, "error_code", "") or "EXECUTOR_RUNTIME_ERROR")
                    runtime_correlation_id = str(getattr(exc, "correlation_id", "") or correlation_id)
                    row.test_data_config = {
                        **config_payload,
                        "executionFailure": {
                            "reason": "executor-runtime-error",
                            "errorType": exc.__class__.__name__,
                            "errorCode": error_code,
                            "correlationId": runtime_correlation_id,
                            "message": str(exc),
                        },
                        "executionCorrelationId": runtime_correlation_id,
                    }
                    row.completed_at = datetime.now(UTC)
                    row.proof_id = None
                    row.status = "failed"
                    session.commit()
                    final_status = "failed"
            elif row is not None:
                final_status = str(row.status or "running")

        return BatchTestRunResultEntity(id=request_id, status=final_status)

    def list_test_proofs(self, rule_id: str) -> list[TestProofEntity]:
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(TestProofRow)
                .where(TestProofRow.rule_id == rule_id)
                .order_by(TestProofRow.test_date.desc())
            ).scalars().all()
            return [self._build_test_proof_entity(row) for row in rows]

    @staticmethod
    def _evaluate_rule_pass(
        check_type: str | None,
        check_type_params: dict,
        success_rate: float,
        failed_count: int,
    ) -> tuple[bool, float | None]:
        if str(check_type or "").upper() != "THRESHOLD":
            return failed_count == 0, None

        threshold_raw = check_type_params.get("threshold")
        if threshold_raw is None:
            return failed_count == 0, None

        try:
            required_success_rate = float(threshold_raw)
        except (TypeError, ValueError):
            return failed_count == 0, None

        required_success_rate = max(0.0, min(100.0, required_success_rate))
        operator = str(check_type_params.get("operator") or "gte").lower()

        if operator == "gt":
            return success_rate > required_success_rate, required_success_rate
        if operator == "lt":
            return success_rate < required_success_rate, required_success_rate
        if operator == "lte":
            return success_rate <= required_success_rate, required_success_rate
        return success_rate >= required_success_rate, required_success_rate

    @staticmethod
    def _to_text(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        if value is None:
            return ""
        return str(value)

    @classmethod
    def _to_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        return cls._to_text(value)

    @staticmethod
    def _create_semantic_stats(semantic_config: dict[str, Any] | None) -> dict[str, Any]:
        config = dict(semantic_config or {})
        field_alias_mappings = config.get("fieldAliasMappings")
        alias_map = (
            {
                str(key).strip(): str(value).strip()
                for key, value in dict(field_alias_mappings or {}).items()
                if str(key).strip() and str(value).strip()
            }
            if isinstance(field_alias_mappings, dict)
            else {}
        )
        return {
            "enabled": bool(config.get("enabled")),
            "configured": bool(alias_map) or bool(config.get("enabled")),
            "field_alias_mappings": alias_map,
            "field_alias_hits": 0,
            "value_coercion_matches": 0,
        }

    @staticmethod
    def _canonical_semantic_token(value: Any, semantic_config: dict[str, Any] | None) -> str | None:
        if isinstance(value, bool):
            return "active" if value else "inactive"

        normalized = str(value or "").strip().lower()
        if not normalized:
            return None

        config = dict(semantic_config or {})
        active_synonyms = config.get("activeSynonyms")
        inactive_synonyms = config.get("inactiveSynonyms")
        active_set = {
            str(item).strip().lower()
            for item in (active_synonyms if isinstance(active_synonyms, list) else ["active", "enabled", "true", "1", "yes", "on"])
            if str(item).strip()
        }
        inactive_set = {
            str(item).strip().lower()
            for item in (inactive_synonyms if isinstance(inactive_synonyms, list) else ["inactive", "disabled", "false", "0", "no", "off"])
            if str(item).strip()
        }

        if normalized in active_set:
            return "active"
        if normalized in inactive_set:
            return "inactive"
        return None

    @staticmethod
    def _build_rule_matcher(
        expression: str,
        semantic_config: dict[str, Any] | None = None,
        semantic_stats: dict[str, Any] | None = None,
    ):
        contains_match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+contains\s+'([^']*)'\s*", expression)
        if contains_match:
            field_name, expected = contains_match.groups()

            def contains_matcher(row: dict) -> bool:
                value = row.get(field_name)
                return isinstance(value, str) and expected in value

            return contains_matcher

        regex_match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*~\s*'([^']*)'\s*", expression)
        if regex_match:
            field_name, pattern = regex_match.groups()
            compiled = re.compile(pattern)

            def regex_matcher(row: dict) -> bool:
                value = row.get(field_name)
                return isinstance(value, str) and compiled.search(value) is not None

            return regex_matcher

        regex_matches_match = re.fullmatch(
            r"\s*REGEXP_MATCHES\(([A-Za-z_][A-Za-z0-9_]*),\s*'([^']*)'(?:,\s*'([a-zA-Z]*)')?\)\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if regex_matches_match:
            field_name, pattern, flags = regex_matches_match.groups()
            regex_flags = 0
            for flag in flags or "":
                if flag == "i":
                    regex_flags |= re.IGNORECASE
                elif flag == "m":
                    regex_flags |= re.MULTILINE
                elif flag == "s":
                    regex_flags |= re.DOTALL
            compiled = re.compile(pattern, regex_flags)

            def regex_matches_matcher(row: dict) -> bool:
                value = row.get(field_name)
                return isinstance(value, str) and compiled.search(value) is not None

            return regex_matches_matcher

        equality_match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'([^']*)'\s*", expression)
        if equality_match:
            field_name, expected = equality_match.groups()

            def equality_matcher(row: dict) -> bool:
                stats = semantic_stats or {}
                alias_map = dict(stats.get("field_alias_mappings") or {})
                resolved_field_name = field_name
                if resolved_field_name not in row and field_name in alias_map and alias_map[field_name] in row:
                    resolved_field_name = alias_map[field_name]
                    stats["field_alias_hits"] = int(stats.get("field_alias_hits", 0)) + 1

                value = row.get(resolved_field_name)
                if value == expected:
                    return True

                if not bool((semantic_config or {}).get("enabled")):
                    return False

                actual_token = PostgresTestingRepository._canonical_semantic_token(value, semantic_config)
                expected_token = PostgresTestingRepository._canonical_semantic_token(expected, semantic_config)
                if actual_token and expected_token and actual_token == expected_token:
                    stats["value_coercion_matches"] = int(stats.get("value_coercion_matches", 0)) + 1
                    return True
                return False

            return equality_matcher

        def expression_matcher(row: dict) -> bool:
            passed, eval_error = evaluate_expression_on_context_with_details(expression, row)
            if eval_error:
                raise ValueError(
                    f"Expression is not executable by test evaluator: {eval_error}"
                )
            return passed

        return expression_matcher

    @staticmethod
    def _sample_value_for_attribute(attribute: dict, index: int) -> object:
        field_name = str(attribute.get("name") or attribute.get("id") or "").lower()
        field_type = str(attribute.get("type") or "").lower()

        if "email" in field_name:
            return f"user{index + 1}@example.com"
        if "status" in field_name:
            return "active" if index % 2 == 0 else "inactive"
        if field_type == "boolean":
            return index % 2 == 0
        if field_type in {"integer", "int", "number", "float", "double"}:
            return index + 1
        return f"val_{index + 1}"

    @staticmethod
    def _current_timestamp() -> str:
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
