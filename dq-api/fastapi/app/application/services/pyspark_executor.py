from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from time import perf_counter
from uuid import uuid4

from pydantic import Field

from dq_domain_validation import GxArtifactEngineTarget
from dq_domain_validation import GxArtifactExecutionShape
from dq_domain_validation import GxExecutionStatus
from app.application.services.grouped_execution_planner import GroupedExecutionPlanner
from app.application.services.gx_execution_source_adapter import GxExecutionSourceAdapter
from app.application.services.gx_execution_source_adapter import GxExecutionSourceAdapterError
from app.core.otel_metrics import increment_gx_failure
from app.core.otel_metrics import record_execution_data_scanned
from app.core.otel_metrics import record_execution_runtime_cost
from app.core.otel_metrics import record_gx_operation_metric
from app.domain.entities import GxArtifactEnvelopeEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import build_gx_artifact_envelope_from_validation_artifact
from app.schemas.pydantic_base import SnakeModel
from dq_utils.spark_runtime import build_spark_session_builder


class PysparkExecutionError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400, error_code: str = "PYSPARK_EXECUTION_ERROR") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class PysparkExecutionDependencyError(PysparkExecutionError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503, error_code="PYSPARK_EXECUTION_DEPENDENCY_ERROR")


class PysparkExecutionPlanError(PysparkExecutionError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400, error_code="PYSPARK_EXECUTION_PLAN_ERROR")


class PysparkExecutionSuiteResultView(SnakeModel):
    suiteId: str
    suiteVersion: int
    dataObjectVersionId: str
    executionShape: GxArtifactExecutionShape
    status: GxExecutionStatus
    startedAt: str
    completedAt: str
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    executionFailure: dict[str, Any] | None = None


class PysparkExecutionPerformanceSummaryView(SnakeModel):
    executionPath: str
    plannerChoice: str
    runtimeMs: float
    suiteCount: int
    batchCount: int
    selectedTargetCount: int
    dataScannedRows: int | None = None
    dataScannedBytes: int | None = None


class PysparkExecutionBatchResultView(SnakeModel):
    dataObjectVersionId: str
    incrementalSelection: dict[str, Any] | None = None
    suiteCount: int
    status: GxExecutionStatus
    startedAt: str
    completedAt: str
    suiteResults: list[PysparkExecutionSuiteResultView] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    performanceSummary: PysparkExecutionPerformanceSummaryView | None = None


class PysparkExecutionRunResultView(SnakeModel):
    runId: str
    correlationId: str
    engineTarget: GxArtifactEngineTarget = "pyspark"
    suiteCount: int
    batchCount: int
    status: GxExecutionStatus
    startedAt: str
    completedAt: str
    batchResults: list[PysparkExecutionBatchResultView] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    performanceSummary: PysparkExecutionPerformanceSummaryView | None = None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _default_spark_session_factory() -> Any:
    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:  # pragma: no cover - environment dependent
        increment_gx_failure(surface="pyspark_executor", operation="create_spark_session", reason="pyspark_not_installed")
        raise PysparkExecutionDependencyError(
            "pyspark is not installed; cannot create a Spark session for real execution"
        ) from exc

    return build_spark_session_builder(
        SparkSession=SparkSession,
        app_name="dq-made-easy",
    ).getOrCreate()


class PysparkExecutionExecutor:
    def __init__(
        self,
        *,
        source_loader: Callable[[Any, str], Any] | None = None,
        materialized_source_loader: Callable[[Any, str], Any] | None = None,
        source_adapter: GxExecutionSourceAdapter | None = None,
        validation_runner: Callable[[Any, Any, GxArtifactEnvelopeEntity, str], dict[str, Any]] | None = None,
        spark_session_factory: Callable[[], Any] | None = None,
        manage_spark_session: bool = True,
        planner: GroupedExecutionPlanner | None = None,
    ) -> None:
        self._source_loader = source_loader
        self._materialized_source_loader = materialized_source_loader
        self._source_adapter = source_adapter
        self._validation_runner = validation_runner or self._default_validation_runner
        self._has_validation_runner = validation_runner is not None
        self._spark_session_factory = spark_session_factory or _default_spark_session_factory
        self._manage_spark_session = manage_spark_session
        self._planner = planner or GroupedExecutionPlanner()

    def _execution_error(self, message: str, *, reason: str, status_code: int = 400) -> PysparkExecutionError:
        increment_gx_failure(surface="pyspark_executor", operation="execute_plan", reason=reason)
        if status_code == 503:
            return PysparkExecutionDependencyError(message)
        if status_code == 400:
            return PysparkExecutionPlanError(message)
        return PysparkExecutionError(message, status_code=status_code)

    async def execute_suites(
        self,
        suites: Sequence[GxArtifactEnvelopeEntity | Mapping[str, Any] | object],
        *,
        correlation_id: str | None = None,
    ) -> PysparkExecutionRunResultView:
        plan = await self._planner.build_plan(suites)
        return await self.execute_plan(plan, correlation_id=correlation_id)

    async def execute_plan(
        self,
        plan: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> PysparkExecutionRunResultView:
        started_at = perf_counter()
        try:
            result = await asyncio.to_thread(self._execute_plan_sync, dict(plan), correlation_id)
        except PysparkExecutionError as exc:
            record_gx_operation_metric(
                surface="pyspark_executor",
                operation="execute_plan",
                result="failed",
                status_code=exc.status_code,
                duration_ms=(perf_counter() - started_at) * 1000.0,
                engine_target="pyspark",
            )
            raise
        except Exception:
            record_gx_operation_metric(
                surface="pyspark_executor",
                operation="execute_plan",
                result="failed",
                status_code=503,
                duration_ms=(perf_counter() - started_at) * 1000.0,
                engine_target="pyspark",
            )
            raise

        record_gx_operation_metric(
            surface="pyspark_executor",
            operation="execute_plan",
            result=result.status,
            status_code=200,
            duration_ms=(perf_counter() - started_at) * 1000.0,
            engine_target=result.engineTarget,
        )
        return result

    def _execute_plan_sync(
        self,
        plan: Mapping[str, Any],
        correlation_id: str | None,
    ) -> PysparkExecutionRunResultView:
        run_started_perf = perf_counter()
        batches = self._coerce_batches(plan)
        run_id = f"run-{uuid4().hex[:12]}"
        run_correlation_id = str(correlation_id or f"corr-{uuid4().hex[:12]}")
        started_at = _utc_now_iso()
        self._preflight_dependencies(batches)
        batch_results: list[PysparkExecutionBatchResultView] = []
        diagnostics: list[dict[str, Any]] = []

        for batch_payload in batches:
            spark_session = self._create_spark_session()
            try:
                batch_results.append(self._execute_batch(spark_session, batch_payload, run_correlation_id))
            finally:
                if self._manage_spark_session and hasattr(spark_session, "stop"):
                    spark_session.stop()

        completed_at = _utc_now_iso()
        status = "succeeded" if all(batch.status == "succeeded" for batch in batch_results) else "failed"
        diagnostics.extend(self._collect_batch_diagnostics(batch_results))
        performance_summary = self._build_run_performance_summary(
            batch_results=batch_results,
            runtime_ms=(perf_counter() - run_started_perf) * 1000.0,
        )
        record_execution_runtime_cost(
            executor="pyspark_executor",
            execution_path=performance_summary.executionPath,
            planner_choice=performance_summary.plannerChoice,
            runtime_ms=performance_summary.runtimeMs,
            batch_count=performance_summary.batchCount,
            suite_count=performance_summary.suiteCount,
            engine_target=str("pyspark"),
            execution_shape="grouped_scope",
        )
        record_execution_data_scanned(
            executor="pyspark_executor",
            execution_path=performance_summary.executionPath,
            planner_choice=performance_summary.plannerChoice,
            batch_count=performance_summary.batchCount,
            suite_count=performance_summary.suiteCount,
            data_scanned_rows=performance_summary.dataScannedRows,
            data_scanned_bytes=performance_summary.dataScannedBytes,
            engine_target=str("pyspark"),
            execution_shape="grouped_scope",
        )
        return PysparkExecutionRunResultView(
            runId=run_id,
            correlationId=run_correlation_id,
            suiteCount=sum(batch.suiteCount for batch in batch_results),
            batchCount=len(batch_results),
            status=status,
            startedAt=started_at,
            completedAt=completed_at,
            batchResults=batch_results,
            diagnostics=diagnostics,
            performanceSummary=performance_summary,
        )

    def _create_spark_session(self) -> Any:
        try:
            spark_session = self._spark_session_factory()
        except PysparkExecutionError:
            raise
        except Exception as exc:
            raise self._execution_error(f"Unable to create Spark session: {exc}", reason="spark_session_factory_failed", status_code=503) from exc

        if spark_session is None:
            raise self._execution_error(
                "Spark session factory returned no session",
                reason="spark_session_factory_returned_none",
                status_code=503,
            )
        return spark_session

    def _coerce_batches(self, plan: Mapping[str, Any]) -> list[dict[str, Any]]:
        batches = plan.get("batches") if isinstance(plan, Mapping) else None
        if not isinstance(batches, list):
            raise self._execution_error("Grouped execution plan is missing batches", reason="missing_batches")
        return [self._coerce_batch(batch) for batch in batches]

    def _coerce_batch(self, batch: Any) -> dict[str, Any]:
        if not isinstance(batch, Mapping):
            raise self._execution_error("Grouped execution batch is invalid", reason="invalid_batch")
        data_object_version_id = str(batch.get("dataObjectVersionId") or "").strip()
        if not data_object_version_id:
            raise self._execution_error(
                "Grouped execution batch is missing dataObjectVersionId",
                reason="missing_data_object_version_id",
            )
        suites = batch.get("suites") or []
        if not isinstance(suites, list) or not suites:
            raise self._execution_error(
                f"Grouped execution batch '{data_object_version_id}' does not include any suite envelopes",
                reason="missing_suite_envelopes",
            )
        incremental_selection = batch.get("incrementalSelection")
        if incremental_selection is not None and not isinstance(incremental_selection, Mapping):
            raise self._execution_error(
                f"Grouped execution batch '{data_object_version_id}' declares an invalid incrementalSelection",
                reason="invalid_incremental_selection",
            )
        return {
            "dataObjectVersionId": data_object_version_id,
            "incrementalSelection": dict(incremental_selection) if isinstance(incremental_selection, Mapping) else None,
            "suites": suites,
        }

    def _execute_batch(
        self,
        spark_session: Any,
        batch: Mapping[str, Any],
        correlation_id: str,
    ) -> PysparkExecutionBatchResultView:
        batch_started_perf = perf_counter()
        batch_started_at = _utc_now_iso()
        data_object_version_id = str(batch["dataObjectVersionId"])
        incremental_selection = batch.get("incrementalSelection")
        planner_choice = self._planner_choice_for_batch(batch)
        execution_path = self._execution_path_for_batch(batch)
        suite_results: list[PysparkExecutionSuiteResultView] = []
        batch_diagnostics: list[dict[str, Any]] = []

        try:
            source_handle = self._load_batch_source(spark_session, batch, correlation_id)
        except Exception as exc:
            increment_gx_failure(surface="pyspark_executor", operation="load_batch_source", reason="batch_source_load_failed")
            failure_diagnostic = self._build_failure_diagnostic(exc, correlation_id, data_object_version_id)
            performance_summary = self._build_batch_performance_summary(
                execution_path=execution_path,
                planner_choice=planner_choice,
                runtime_ms=(perf_counter() - batch_started_perf) * 1000.0,
                suite_count=len(batch["suites"]),
                batch_count=1,
                data_scanned_rows=None,
                data_scanned_bytes=None,
                selected_target_count=1,
            )
            record_execution_runtime_cost(
                executor="pyspark_executor",
                execution_path=execution_path,
                planner_choice=planner_choice,
                runtime_ms=performance_summary.runtimeMs,
                batch_count=1,
                suite_count=performance_summary.suiteCount,
                engine_target=str("pyspark"),
                execution_shape="grouped_scope",
            )
            for suite_payload in batch["suites"]:
                suite = self._coerce_suite(suite_payload)
                suite_results.append(
                    PysparkExecutionSuiteResultView(
                        suiteId=str(suite.suiteId or "").strip(),
                        suiteVersion=int(suite.suiteVersion),
                        dataObjectVersionId=data_object_version_id,
                        executionShape=str(suite.executionContract.executionShape) if suite.executionContract else "single_object",
                        status="failed",
                        startedAt=batch_started_at,
                        completedAt=_utc_now_iso(),
                        diagnostics=[failure_diagnostic],
                        result={},
                        executionFailure=failure_diagnostic,
                    )
                )
            return PysparkExecutionBatchResultView(
                dataObjectVersionId=data_object_version_id,
                incrementalSelection=incremental_selection,
                suiteCount=len(suite_results),
                status="failed",
                startedAt=batch_started_at,
                completedAt=_utc_now_iso(),
                suiteResults=suite_results,
                diagnostics=[failure_diagnostic],
                performanceSummary=performance_summary,
            )

        scan_metrics = self._extract_scan_metrics(source_handle)

        for suite_payload in batch["suites"]:
            suite = self._coerce_suite(suite_payload)
            suite_started_at = _utc_now_iso()
            try:
                validation_payload = self._validation_runner(spark_session, source_handle, suite, correlation_id)
                suite_result = self._coerce_validation_payload(validation_payload)
                suite_status = suite_result["status"]
                diagnostics = suite_result["diagnostics"]
                execution_failure = suite_result["executionFailure"]
                result_payload = suite_result["result"]
            except PysparkExecutionError as exc:
                increment_gx_failure(surface="pyspark_executor", operation="validate_suite", reason=exc.error_code.lower())
                suite_status = "failed"
                diagnostics = [self._build_failure_diagnostic(exc, correlation_id, data_object_version_id)]
                execution_failure = diagnostics[0]
                result_payload = {}
            except Exception as exc:
                increment_gx_failure(surface="pyspark_executor", operation="validate_suite", reason="suite_validation_failed")
                suite_status = "failed"
                diagnostics = [self._build_failure_diagnostic(exc, correlation_id, data_object_version_id)]
                execution_failure = diagnostics[0]
                result_payload = {}

            suite_results.append(
                PysparkExecutionSuiteResultView(
                    suiteId=str(suite.suiteId or "").strip(),
                    suiteVersion=int(suite.suiteVersion),
                    dataObjectVersionId=data_object_version_id,
                    executionShape=str(suite.executionContract.executionShape),
                    status=suite_status,
                    startedAt=suite_started_at,
                    completedAt=_utc_now_iso(),
                    diagnostics=diagnostics,
                    result=result_payload,
                    executionFailure=execution_failure if suite_status == "failed" else None,
                )
            )
            if suite_status == "failed":
                batch_diagnostics.extend(diagnostics)

        batch_status = "succeeded" if all(result.status == "succeeded" for result in suite_results) else "failed"
        performance_summary = self._build_batch_performance_summary(
            execution_path=execution_path,
            planner_choice=planner_choice,
            runtime_ms=(perf_counter() - batch_started_perf) * 1000.0,
            suite_count=len(suite_results),
            batch_count=1,
            data_scanned_rows=scan_metrics.get("rows_scanned"),
            data_scanned_bytes=scan_metrics.get("bytes_scanned"),
            selected_target_count=1,
        )
        record_execution_runtime_cost(
            executor="pyspark_executor",
            execution_path=execution_path,
            planner_choice=planner_choice,
            runtime_ms=performance_summary.runtimeMs,
            batch_count=1,
            suite_count=performance_summary.suiteCount,
            engine_target=str("pyspark"),
            execution_shape="grouped_scope",
        )
        record_execution_data_scanned(
            executor="pyspark_executor",
            execution_path=execution_path,
            planner_choice=planner_choice,
            batch_count=1,
            suite_count=performance_summary.suiteCount,
            data_scanned_rows=performance_summary.dataScannedRows,
            data_scanned_bytes=performance_summary.dataScannedBytes,
            engine_target=str("pyspark"),
            execution_shape="grouped_scope",
        )
        return PysparkExecutionBatchResultView(
            dataObjectVersionId=data_object_version_id,
            incrementalSelection=incremental_selection,
            suiteCount=len(suite_results),
            status=batch_status,
            startedAt=batch_started_at,
            completedAt=_utc_now_iso(),
            suiteResults=suite_results,
            diagnostics=batch_diagnostics,
            performanceSummary=performance_summary,
        )

    def _preflight_dependencies(self, batches: Sequence[Mapping[str, Any]]) -> None:
        if not self._has_validation_runner:
            raise self._execution_error(
                "No validation_runner was configured for pyspark execution",
                reason="missing_validation_runner",
                status_code=503,
            )

        for batch in batches:
            suites = list(batch.get("suites") or [])
            if not suites:
                continue
            suite = self._coerce_suite(suites[0])
            execution_contract = suite.executionContract
            if execution_contract is None:
                raise self._execution_error(
                    f"GX suite '{suite.suiteId}' is missing an executionContract",
                    reason="missing_execution_contract",
                )
            execution_shape = str(execution_contract.executionShape or "").strip()
            if self._source_adapter is not None:
                if not self._source_adapter.supports_execution_shape(execution_shape):
                    raise self._execution_error(
                        f"Configured source_adapter does not support '{execution_shape}' execution",
                        reason="unsupported_execution_shape",
                    )
                continue
            if execution_shape == "join_pair" and self._materialized_source_loader is None:
                raise self._execution_error(
                    "No materialized_source_loader was configured for join_pair execution",
                    reason="missing_materialized_source_loader",
                    status_code=503,
                )
            if execution_shape != "join_pair" and self._source_loader is None:
                raise self._execution_error(
                    "No source_loader was configured for single_object/streaming/micro_batch execution",
                    reason="missing_source_loader",
                    status_code=503,
                )

    def _load_batch_source(self, spark_session: Any, batch: Mapping[str, Any], correlation_id: str) -> Any:
        suite = self._coerce_suite(batch["suites"][0])
        incremental_selection = batch.get("incrementalSelection")
        execution_contract = suite.executionContract
        if execution_contract is None:
            raise self._execution_error(
                f"GX suite '{suite.suiteId}' is missing an executionContract",
                reason="missing_execution_contract",
            )

        if self._source_adapter is not None:
            try:
                asset_ref = self._source_adapter.resolve_asset(
                    spark_session=spark_session,
                    suite=suite,
                    data_object_version_id=str(batch["dataObjectVersionId"]),
                    correlation_id=correlation_id,
                )
                source_handle = self._source_adapter.load_dataframe(
                    spark_session=spark_session,
                    asset_ref=asset_ref,
                )
                primary_key_fields = []
                if suite.executionHints is not None:
                    primary_key_fields = list(suite.executionHints.primaryKeyFields or [])
                source_handle = self._source_adapter.materialize_primary_key(source_handle, primary_key_fields)
                source_handle = self._source_adapter.emit_validation_target(
                    source_handle,
                    {
                        "suite_id": str(suite.suiteId or "").strip(),
                        "suite_version": int(suite.suiteVersion),
                        "data_object_version_id": str(batch["dataObjectVersionId"]),
                        "correlation_id": correlation_id,
                        "incremental_selection": incremental_selection,
                    },
                )
                return source_handle
            except GxExecutionSourceAdapterError as exc:
                raise self._execution_error(str(exc), reason="source_adapter_failed", status_code=exc.status_code) from exc

        if execution_contract.executionShape != "join_pair":
            if self._source_loader is None:
                raise self._execution_error(
                    "No source_loader was configured for single_object/streaming/micro_batch execution",
                    reason="missing_source_loader",
                    status_code=503,
                )
            return self._source_loader(spark_session, batch["dataObjectVersionId"])

        source_materialization = execution_contract.sourceMaterialization
        if source_materialization is None:
            raise self._execution_error(
                f"GX suite '{suite.suiteId}' declares join_pair execution without sourceMaterialization",
                reason="missing_source_materialization",
            )
        if self._materialized_source_loader is None:
            raise self._execution_error(
                "No materialized_source_loader was configured for join_pair execution",
                reason="missing_materialized_source_loader",
                status_code=503,
            )
        return self._materialized_source_loader(spark_session, source_materialization.outputLocation)

    @staticmethod
    def _planner_choice_for_batch(batch: Mapping[str, Any]) -> str:
        if isinstance(batch, Mapping) and str(batch.get("plannerChoice") or "").strip():
            return str(batch["plannerChoice"]).strip()
        incremental_selection = batch.get("incrementalSelection")
        return "incremental_scope" if incremental_selection is not None else "full_scope"

    @classmethod
    def _execution_path_for_batch(cls, batch: Mapping[str, Any]) -> str:
        if isinstance(batch, Mapping) and str(batch.get("executionPath") or "").strip():
            return str(batch["executionPath"]).strip()
        return "incremental_grouped_execution" if cls._planner_choice_for_batch(batch) == "incremental_scope" else "grouped_execution"

    @staticmethod
    def _extract_scan_metrics(source_handle: Any) -> dict[str, int | None]:
        if not isinstance(source_handle, Mapping):
            return {"rows_scanned": None, "bytes_scanned": None}

        scan_metrics: Mapping[str, Any] | None = None
        for key in ("scan_metrics", "scanMetrics"):
            candidate = source_handle.get(key)
            if isinstance(candidate, Mapping):
                scan_metrics = candidate
                break

        if scan_metrics is None:
            return {"rows_scanned": None, "bytes_scanned": None}

        rows_scanned = None
        for key in ("rows_scanned", "rowsScanned", "row_count", "rowCount", "records_scanned", "recordsScanned"):
            value = scan_metrics.get(key)
            if value is not None:
                rows_scanned = int(value)
                break

        bytes_scanned = None
        for key in ("bytes_scanned", "bytesScanned"):
            value = scan_metrics.get(key)
            if value is not None:
                bytes_scanned = int(value)
                break

        return {
            "rows_scanned": rows_scanned,
            "bytes_scanned": bytes_scanned,
        }

    @staticmethod
    def _build_batch_performance_summary(
        *,
        execution_path: str,
        planner_choice: str,
        runtime_ms: float,
        suite_count: int,
        batch_count: int,
        data_scanned_rows: int | None,
        data_scanned_bytes: int | None,
        selected_target_count: int,
    ) -> PysparkExecutionPerformanceSummaryView:
        return PysparkExecutionPerformanceSummaryView(
            executionPath=execution_path,
            plannerChoice=planner_choice,
            runtimeMs=runtime_ms,
            suiteCount=suite_count,
            batchCount=batch_count,
            selectedTargetCount=selected_target_count,
            dataScannedRows=data_scanned_rows,
            dataScannedBytes=data_scanned_bytes,
        )

    @classmethod
    def _build_run_performance_summary(
        cls,
        *,
        batch_results: Sequence[PysparkExecutionBatchResultView],
        runtime_ms: float,
    ) -> PysparkExecutionPerformanceSummaryView:
        if not batch_results:
            return PysparkExecutionPerformanceSummaryView(
                executionPath="empty_plan",
                plannerChoice="empty",
                runtimeMs=runtime_ms,
                suiteCount=0,
                batchCount=0,
                selectedTargetCount=0,
                dataScannedRows=None,
                dataScannedBytes=None,
            )

        execution_paths = {
            str(batch.performanceSummary.executionPath).strip().lower()
            for batch in batch_results
            if batch.performanceSummary is not None and str(batch.performanceSummary.executionPath or "").strip()
        }
        planner_choices = {
            str(batch.performanceSummary.plannerChoice).strip().lower()
            for batch in batch_results
            if batch.performanceSummary is not None and str(batch.performanceSummary.plannerChoice or "").strip()
        }
        execution_path = "mixed_grouped_execution" if len(execution_paths) > 1 else next(iter(execution_paths), "grouped_execution")
        planner_choice = "mixed_scope" if len(planner_choices) > 1 else next(iter(planner_choices), "full_scope")

        data_scanned_rows = cls._sum_optional_batch_metric(batch_results, "dataScannedRows")
        data_scanned_bytes = cls._sum_optional_batch_metric(batch_results, "dataScannedBytes")

        return PysparkExecutionPerformanceSummaryView(
            executionPath=execution_path,
            plannerChoice=planner_choice,
            runtimeMs=runtime_ms,
            suiteCount=sum(batch.suiteCount for batch in batch_results),
            batchCount=len(batch_results),
            selectedTargetCount=sum(batch.performanceSummary.selectedTargetCount for batch in batch_results if batch.performanceSummary is not None),
            dataScannedRows=data_scanned_rows,
            dataScannedBytes=data_scanned_bytes,
        )

    @staticmethod
    def _sum_optional_batch_metric(batch_results: Sequence[PysparkExecutionBatchResultView], field_name: str) -> int | None:
        total = 0
        found = False
        for batch in batch_results:
            performance_summary = batch.performanceSummary
            if performance_summary is None:
                continue
            value = getattr(performance_summary, field_name, None)
            if value is None:
                continue
            total += int(value)
            found = True
        return total if found else None

    def _coerce_suite(
        self,
        suite: ValidationArtifactEnvelopeEntity | GxArtifactEnvelopeEntity | Mapping[str, Any] | object,
    ) -> GxArtifactEnvelopeEntity:
        if isinstance(suite, GxArtifactEnvelopeEntity):
            return suite
        if isinstance(suite, ValidationArtifactEnvelopeEntity):
            try:
                return build_gx_artifact_envelope_from_validation_artifact(suite)
            except ValueError as exc:
                raise self._execution_error("GX suite envelope is invalid", reason="invalid_suite_envelope") from exc
        if hasattr(suite, "model_dump"):
            suite = getattr(suite, "model_dump")(by_alias=False, exclude_none=False)
        if isinstance(suite, Mapping) and (
            suite.get("validationArtifactId") is not None or suite.get("validation_artifact_id") is not None
        ):
            try:
                return build_gx_artifact_envelope_from_validation_artifact(suite)
            except ValueError as exc:
                raise self._execution_error("GX suite envelope is invalid", reason="invalid_suite_envelope") from exc
        try:
            return GxArtifactEnvelopeEntity.model_validate(dict(suite))
        except Exception as exc:
            raise self._execution_error("GX suite envelope is invalid", reason="invalid_suite_envelope") from exc

    def _coerce_validation_payload(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise self._execution_error("Validation runner must return a mapping", reason="invalid_validation_payload")

        status = str(payload.get("status") or "").strip().lower()
        passed = payload.get("passed")
        if not status:
            status = "succeeded" if bool(passed) else "failed"
        if status not in {"succeeded", "failed"}:
            raise self._execution_error(
                f"Validation runner returned unsupported status '{status}'",
                reason="unsupported_validation_status",
            )

        diagnostics = payload.get("diagnostics") or []
        if not isinstance(diagnostics, list):
            raise self._execution_error("Validation runner diagnostics must be a list", reason="invalid_diagnostics")

        result = payload.get("result") or {}
        if not isinstance(result, dict):
            raise self._execution_error("Validation runner result must be a mapping", reason="invalid_result_payload")

        execution_failure = payload.get("executionFailure")
        if execution_failure is not None and not isinstance(execution_failure, dict):
            raise self._execution_error(
                "Validation runner executionFailure must be a mapping when provided",
                reason="invalid_execution_failure_payload",
            )

        return {
            "status": status,
            "diagnostics": diagnostics,
            "result": result,
            "executionFailure": execution_failure,
        }

    def _build_failure_diagnostic(
        self,
        exc: Exception,
        correlation_id: str,
        data_object_version_id: str,
    ) -> dict[str, Any]:
        error_code = str(getattr(exc, "error_code", "") or "EXECUTOR_RUNTIME_ERROR")
        return {
            "reason": "executor-runtime-error",
            "errorCode": error_code,
            "errorType": exc.__class__.__name__,
            "correlationId": correlation_id,
            "dataObjectVersionId": data_object_version_id,
            "message": str(exc),
        }

    @staticmethod
    def _collect_batch_diagnostics(batch_results: Sequence[PysparkExecutionBatchResultView]) -> list[dict[str, Any]]:
        diagnostics: list[dict[str, Any]] = []
        for batch in batch_results:
            diagnostics.extend(batch.diagnostics)
        return diagnostics

    @staticmethod
    def _default_validation_runner(
        spark_session: Any,
        source_handle: Any,
        suite: GxArtifactEnvelopeEntity,
        correlation_id: str,
    ) -> dict[str, Any]:
        del spark_session, source_handle, suite, correlation_id
        raise PysparkExecutionDependencyError("No validation_runner was configured for pyspark execution")