from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.domain.entities.gx_execution_run import build_gx_execution_run_create_entity
from app.application.use_cases.execution_queries import GxExecutionExceptionAnalyticsQuery
from app.application.use_cases.execution_queries import get_gx_execution_exception_analytics
from app.application.use_cases.execution_queries import get_gx_execution_run_statistics
from app.application.use_cases.execution_queries import ListGxExecutionRunsQuery
from app.application.use_cases.execution_queries import GxExecutionRunStatisticsQuery
from app.application.use_cases.execution_queries import list_gx_execution_run_summaries
from app.domain.entities.gx_execution_run import GxExecutionRunListQueryEntity
from app.domain.entities import GxExecutionRunSummaryEntity
from app.domain.entities.gx_execution_violation import build_gx_execution_violation_summary_entity
from app.infrastructure.repositories.in_memory_gx_execution_run_repository import InMemoryGxExecutionRunRepository
from app.infrastructure.repositories.in_memory_gx_run_plan_repository import InMemoryGxRunPlanRepository
from app.infrastructure.repositories.in_memory_gx_suite_repository import InMemoryGxSuiteRepository


class _StubRulesRepository:
    def __init__(self) -> None:
        self._rules = {
            "rule-1": SimpleNamespace(
                id="rule-1",
                name="Customer Order Completeness",
                taxonomy=SimpleNamespace(owner="data-platform", domain="retail-banking", severity="high"),
            ),
            "rule-2": SimpleNamespace(
                id="rule-2",
                name="Transfer Match",
                taxonomy=SimpleNamespace(owner="risk-engineering", domain="corporate-banking", severity="medium"),
            ),
        }

    async def get_rule_by_id(self, rule_id: str):
        return self._rules.get(rule_id)


class _StubDataCatalogRepository:
    def list_data_objects_catalog(self, data_set_id: str | None = None):
        return [
            SimpleNamespace(id="object-orders", name="Orders"),
            SimpleNamespace(id="object-customers", name="Customer Orders"),
        ]

    def list_data_object_versions(self, object_id: str | None = None):
        versions = [
            SimpleNamespace(id="dov-1", data_object_id="object-orders", version=1),
            SimpleNamespace(id="dov-2", data_object_id="object-customers", version=1),
        ]
        if object_id is None:
            return versions
        return [version for version in versions if version.data_object_id == object_id]


class _StubViolationRepository:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    async def summarize_violations(self, **kwargs):
        return await self.summarize_reason_analytics(**kwargs)

    async def summarize_reason_analytics(self, **kwargs):
        self.last_kwargs = kwargs
        second_bucket_start = (
            datetime.fromisoformat(str(kwargs["bucket_origin"])) + timedelta(seconds=int(kwargs["bucket_size_seconds"]))
        ).isoformat()
        requested_reason_codes = {
            str(value).strip()
            for value in (kwargs.get("reason_codes") or [])
            if str(value).strip()
        }
        payload = {
            "total_failed_records": 6,
            "runs_with_failures": 2,
            "trend_totals": [
                {"bucket_start": str(kwargs["bucket_origin"]), "total": 3},
                {"bucket_start": second_bucket_start, "total": 3},
            ],
            "reason_trend_totals": [
                {
                    "bucket_start": str(kwargs["bucket_origin"]),
                    "reason_code": "expect_column_values_to_not_be_null",
                    "reason_text": "customer_id must not be null",
                    "total": 2,
                },
                {
                    "bucket_start": str(kwargs["bucket_origin"]),
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                    "total": 1,
                },
                {
                    "bucket_start": second_bucket_start,
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                    "total": 3,
                },
            ],
            "rule_totals": [{"rule_id": "rule-2", "total": 6}],
            "data_object_totals": [{"data_object_version_id": "dov-1", "total": 6}],
            "reason_totals": [
                {
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                    "total": 4,
                },
                {
                    "reason_code": "expect_column_values_to_not_be_null",
                    "reason_text": "customer_id must not be null",
                    "total": 2,
                },
            ],
        }
        if requested_reason_codes:
            payload["reason_trend_totals"] = [
                row for row in payload["reason_trend_totals"] if str(row["reason_code"]) in requested_reason_codes
            ]
            payload["reason_totals"] = [
                row for row in payload["reason_totals"] if str(row["reason_code"]) in requested_reason_codes
            ]
            payload["total_failed_records"] = sum(int(row["total"]) for row in payload["reason_trend_totals"])
            payload["runs_with_failures"] = 1 if payload["reason_trend_totals"] else 0
            bucket_totals: dict[str, int] = {}
            for row in payload["reason_trend_totals"]:
                bucket_start = str(row["bucket_start"])
                bucket_totals[bucket_start] = bucket_totals.get(bucket_start, 0) + int(row["total"])
            payload["trend_totals"] = [
                {"bucket_start": bucket_start, "total": total}
                for bucket_start, total in sorted(bucket_totals.items())
            ]
        return build_gx_execution_violation_summary_entity(payload)


class _CaptureQueryRepository(InMemoryGxExecutionRunRepository):
    def __init__(self) -> None:
        super().__init__()
        self.last_query: object | None = None

    async def list_runs(self, query):
        self.last_query = query
        return await super().list_runs(query)


@pytest.mark.anyio
async def test_list_gx_execution_run_summaries_filters_by_rule_and_data_object_name() -> None:
    repository = InMemoryGxExecutionRunRepository()
    suite_repository = InMemoryGxSuiteRepository()
    rules_repository = _StubRulesRepository()
    data_catalog_repository = _StubDataCatalogRepository()

    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-123",
                "suite_id": "gx-suite-1",
                "suite_version": 3,
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "correlation_id": "corr-123",
                "requested_by": "user-admin",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "join_pair",
                "status": "running",
                "submitted_at": "2026-04-16T08:00:00+00:00",
                "execution_contract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "join_pair",
                    "traceability": {
                        "ruleId": "rule-1",
                        "ruleVersionId": "rule-version-1",
                        "gxSuiteId": "gx-suite-1",
                        "gxSuiteVersion": 3,
                        "dataObjectVersionId": "dov-1",
                    },
                    "sourceMaterialization": {
                        "leftSource": {"dataObjectId": "object-orders", "dataObjectVersionId": "dov-1"},
                        "rightSource": {"dataObjectId": "object-customers", "dataObjectVersionId": "dov-2"},
                    },
                },
                "handoff_payload": {"queue_key": "dq-gx:execution-dispatch", "engine_type": "gx"},
            }
        )
    )
    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-999",
                "suite_id": "gx-suite-other",
                "suite_version": 1,
                "rule_id": "rule-2",
                "rule_version_id": "rule-version-2",
                "correlation_id": "corr-999",
                "requested_by": "user-other",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "pending",
                "submitted_at": "2026-04-05T08:00:00+00:00",
                "execution_contract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "single_object",
                    "traceability": {
                        "ruleId": "rule-2",
                        "ruleVersionId": "rule-version-2",
                        "gxSuiteId": "gx-suite-other",
                        "gxSuiteVersion": 1,
                        "dataObjectVersionId": "dov-2",
                    },
                },
            }
        )
    )

    result = await list_gx_execution_run_summaries(
        query=ListGxExecutionRunsQuery(
            lookback_amount=7,
            lookback_unit="days",
            rule_name="Customer Order",
            data_object_name="Orders",
            search="corr-123",
            limit=25,
        ),
        repository=repository,
        run_plan_repository=InMemoryGxRunPlanRepository(),
        suite_repository=suite_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        now=datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
    )

    assert len(result) == 1
    assert isinstance(result[0], GxExecutionRunSummaryEntity)
    assert result[0].id == "run-123"
    assert result[0].ruleName == "Customer Order Completeness"
    assert result[0].owner == "data-platform"
    assert result[0].domain == "retail-banking"
    assert result[0].severity == "high"
    assert result[0].dataObjectNames == ["Orders", "Customer Orders"]
    assert result[0].status == "running"


@pytest.mark.anyio
async def test_list_gx_execution_run_summaries_filters_by_rule_taxonomy() -> None:
    repository = InMemoryGxExecutionRunRepository()
    suite_repository = InMemoryGxSuiteRepository()
    rules_repository = _StubRulesRepository()
    data_catalog_repository = _StubDataCatalogRepository()

    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-taxonomy-1",
                "suite_id": "gx-suite-1",
                "suite_version": 3,
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "correlation_id": "corr-taxonomy-1",
                "requested_by": "user-admin",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "join_pair",
                "status": "running",
                "submitted_at": "2026-04-16T08:00:00+00:00",
                "execution_contract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "join_pair",
                    "traceability": {
                        "ruleId": "rule-1",
                        "ruleVersionId": "rule-version-1",
                        "gxSuiteId": "gx-suite-1",
                        "gxSuiteVersion": 3,
                        "dataObjectVersionId": "dov-1",
                    },
                },
            }
        )
    )
    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-taxonomy-2",
                "suite_id": "gx-suite-2",
                "suite_version": 1,
                "rule_id": "rule-2",
                "rule_version_id": "rule-version-2",
                "correlation_id": "corr-taxonomy-2",
                "requested_by": "user-admin",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "pending",
                "submitted_at": "2026-04-16T08:05:00+00:00",
                "execution_contract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "single_object",
                    "traceability": {
                        "ruleId": "rule-2",
                        "ruleVersionId": "rule-version-2",
                        "gxSuiteId": "gx-suite-2",
                        "gxSuiteVersion": 1,
                        "dataObjectVersionId": "dov-2",
                    },
                },
            }
        )
    )

    result = await list_gx_execution_run_summaries(
        query=ListGxExecutionRunsQuery(
            lookback_amount=7,
            lookback_unit="days",
            owner="data-platform",
            domain="retail-banking",
            severity="high",
            limit=25,
        ),
        repository=repository,
        run_plan_repository=InMemoryGxRunPlanRepository(),
        suite_repository=suite_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        now=datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
    )

    assert len(result) == 1
    assert result[0].id == "run-taxonomy-1"
    assert result[0].owner == "data-platform"
    assert result[0].domain == "retail-banking"
    assert result[0].severity == "high"


@pytest.mark.anyio
async def test_list_gx_execution_run_summaries_passes_raw_mapping_to_repository() -> None:
    repository = _CaptureQueryRepository()
    suite_repository = InMemoryGxSuiteRepository()
    rules_repository = _StubRulesRepository()
    data_catalog_repository = _StubDataCatalogRepository()

    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-capture-1",
                "suite_id": "gx-suite-capture",
                "suite_version": 1,
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "correlation_id": "corr-capture-1",
                "requested_by": "user-admin",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "running",
                "submitted_at": "2026-04-16T08:00:00+00:00",
                "execution_contract": {
                    "engineType": "gx",
                    "engineTarget": "pyspark",
                    "executionShape": "single_object",
                    "traceability": {
                        "ruleId": "rule-1",
                        "ruleVersionId": "rule-version-1",
                        "gxSuiteId": "gx-suite-capture",
                        "gxSuiteVersion": 1,
                        "dataObjectVersionId": "dov-1",
                    },
                },
            }
        )
    )

    result = await list_gx_execution_run_summaries(
        query=ListGxExecutionRunsQuery(
            lookback_amount=7,
            lookback_unit="days",
            limit=25,
        ),
        repository=repository,
        run_plan_repository=InMemoryGxRunPlanRepository(),
        suite_repository=suite_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        now=datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
    )

    assert len(result) == 1
    assert isinstance(repository.last_query, dict)
    assert not isinstance(repository.last_query, GxExecutionRunListQueryEntity)
    assert repository.last_query["status"] is None
    assert repository.last_query["submitted_after"] == datetime(2026, 4, 9, 10, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_list_gx_execution_run_summaries_searches_by_engine_type() -> None:
    repository = InMemoryGxExecutionRunRepository()
    suite_repository = InMemoryGxSuiteRepository()
    rules_repository = _StubRulesRepository()
    data_catalog_repository = _StubDataCatalogRepository()

    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-engine-1",
                "suite_id": "suite-one",
                "suite_version": 1,
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "correlation_id": "corr-engine-1",
                "requested_by": "user-admin",
                "engine_type": "neutral-runtime",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "running",
                "submitted_at": "2026-04-16T08:00:00+00:00",
                "execution_contract": {
                    "engine_type": "neutral-runtime",
                    "engine_target": "pyspark",
                    "execution_shape": "single_object",
                    "traceability": {
                        "ruleId": "rule-1",
                        "ruleVersionId": "rule-version-1",
                        "gxSuiteId": "suite-one",
                        "gxSuiteVersion": 1,
                        "dataObjectVersionId": "dov-1",
                    },
                },
            }
        )
    )

    result = await list_gx_execution_run_summaries(
        query=ListGxExecutionRunsQuery(
            lookback_amount=7,
            lookback_unit="days",
            search="neutral-runtime",
            limit=25,
        ),
        repository=repository,
        run_plan_repository=InMemoryGxRunPlanRepository(),
        suite_repository=suite_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        now=datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
    )

    assert len(result) == 1
    assert result[0].id == "run-engine-1"
    assert result[0].engineType == "neutral-runtime"


@pytest.mark.anyio
async def test_get_gx_execution_run_statistics_aggregates_counts_and_recent_runs() -> None:
    repository = InMemoryGxExecutionRunRepository()
    suite_repository = InMemoryGxSuiteRepository()
    rules_repository = _StubRulesRepository()
    data_catalog_repository = _StubDataCatalogRepository()

    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-stat-1",
                "suite_id": "gx-suite-1",
                "suite_version": 1,
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "correlation_id": "corr-stat-1",
                "requested_by": "user-admin",
                "engine_type": "neutral-runtime",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "running",
                "submitted_at": "2026-04-16T09:45:00+00:00",
                "execution_contract": {
                    "engineType": "neutral-runtime",
                    "engineTarget": "pyspark",
                    "executionShape": "single_object",
                    "resolvedDataDeliveryId": "delivery-stat-1",
                    "traceability": {
                        "ruleId": "rule-1",
                        "ruleVersionId": "rule-version-1",
                        "gxSuiteId": "gx-suite-1",
                        "gxSuiteVersion": 1,
                        "dataObjectVersionId": "dov-1",
                    },
                },
                "handoff_payload": {
                    "engine_type": "neutral-runtime",
                    "runPlanId": "run-plan-stat-1",
                },
            }
        )
    )
    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-stat-2",
                "suite_id": "gx-suite-2",
                "suite_version": 1,
                "rule_id": "rule-2",
                "rule_version_id": "rule-version-2",
                "correlation_id": "corr-stat-2",
                "requested_by": "user-admin",
                "engine_type": "batch-runtime",
                "engine_target": "spark",
                "execution_shape": "grouped_scope",
                "status": "succeeded",
                "submitted_at": "2026-04-16T09:30:00+00:00",
                "execution_contract": {
                    "engineType": "batch-runtime",
                    "engineTarget": "spark",
                    "executionShape": "grouped_scope",
                    "traceability": {
                        "ruleId": "rule-2",
                        "ruleVersionId": "rule-version-2",
                        "gxSuiteId": "gx-suite-2",
                        "gxSuiteVersion": 1,
                        "dataObjectVersionId": "dov-2",
                    },
                },
            }
        )
    )

    result = await get_gx_execution_run_statistics(
        query=GxExecutionRunStatisticsQuery(
            lookback_amount=24,
            lookback_unit="hours",
            recent_limit=1,
        ),
        repository=repository,
        run_plan_repository=InMemoryGxRunPlanRepository(),
        suite_repository=suite_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        now=datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
    )

    assert result.totalRuns == 2
    assert result.pendingRuns == 0
    assert result.runningRuns == 1
    assert result.succeededRuns == 1
    assert result.failedRuns == 0
    assert result.cancelledRuns == 0
    assert [row.name for row in result.statusBreakdown] == ["running", "succeeded"]
    assert [row.name for row in result.engineTargetBreakdown] == ["pyspark", "spark"]
    assert [row.name for row in result.executionShapeBreakdown] == ["grouped_scope", "single_object"]
    assert len(result.recentRuns) == 1
    assert result.recentRuns[0].id == "run-stat-1"
    assert result.recentRuns[0].runPlanId == "run-plan-stat-1"
    assert result.recentRuns[0].resolvedDataDeliveryId == "delivery-stat-1"


@pytest.mark.anyio
async def test_get_gx_execution_run_statistics_filters_by_workspace_run_plans() -> None:
    repository = InMemoryGxExecutionRunRepository()
    run_plan_repository = InMemoryGxRunPlanRepository()
    suite_repository = InMemoryGxSuiteRepository()
    rules_repository = _StubRulesRepository()
    data_catalog_repository = _StubDataCatalogRepository()

    await run_plan_repository.create_plan(
        run_plan_id="run-plan-retail",
        run_plan_version_id="run-plan-retail-v1",
        workspace_id="retail-banking",
        scope_selector={"workspaceId": "retail-banking"},
        planning_mode="scheduled",
        status="active",
        created_by="user-admin",
        gx_suite_selection={},
        suite_id="gx-suite-1",
        suite_version=1,
        suite_snapshot=None,
        execution_contract_snapshot=None,
        schedule_definition={},
    )
    await run_plan_repository.create_plan(
        run_plan_id="run-plan-corp",
        run_plan_version_id="run-plan-corp-v1",
        workspace_id="corporate-banking",
        scope_selector={"workspaceId": "corporate-banking"},
        planning_mode="scheduled",
        status="active",
        created_by="user-admin",
        gx_suite_selection={},
        suite_id="gx-suite-2",
        suite_version=1,
        suite_snapshot=None,
        execution_contract_snapshot=None,
        schedule_definition={},
    )

    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-retail-1",
                "suite_id": "gx-suite-1",
                "suite_version": 1,
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "correlation_id": "corr-retail-1",
                "requested_by": "user-admin",
                "engine_type": "neutral-runtime",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "running",
                "submitted_at": "2026-04-16T09:45:00+00:00",
                "execution_contract": {
                    "engineType": "neutral-runtime",
                    "engineTarget": "pyspark",
                    "executionShape": "single_object",
                    "traceability": {
                        "ruleId": "rule-1",
                        "ruleVersionId": "rule-version-1",
                        "gxSuiteId": "gx-suite-1",
                        "gxSuiteVersion": 1,
                        "dataObjectVersionId": "dov-1",
                    },
                },
                "handoff_payload": {
                    "engine_type": "neutral-runtime",
                    "runPlanId": "run-plan-retail",
                },
            }
        )
    )
    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-corp-1",
                "suite_id": "gx-suite-2",
                "suite_version": 1,
                "rule_id": "rule-2",
                "rule_version_id": "rule-version-2",
                "correlation_id": "corr-corp-1",
                "requested_by": "user-admin",
                "engine_type": "batch-runtime",
                "engine_target": "spark",
                "execution_shape": "grouped_scope",
                "status": "succeeded",
                "submitted_at": "2026-04-16T09:30:00+00:00",
                "execution_contract": {
                    "engineType": "batch-runtime",
                    "engineTarget": "spark",
                    "executionShape": "grouped_scope",
                    "traceability": {
                        "ruleId": "rule-2",
                        "ruleVersionId": "rule-version-2",
                        "gxSuiteId": "gx-suite-2",
                        "gxSuiteVersion": 1,
                        "dataObjectVersionId": "dov-2",
                    },
                },
                "handoff_payload": {
                    "engine_type": "batch-runtime",
                    "runPlanId": "run-plan-corp",
                },
            }
        )
    )

    result = await get_gx_execution_run_statistics(
        query=GxExecutionRunStatisticsQuery(
            lookback_amount=24,
            lookback_unit="hours",
            recent_limit=10,
            workspace_id="retail-banking",
        ),
        repository=repository,
        run_plan_repository=run_plan_repository,
        suite_repository=suite_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        now=datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
    )

    assert result.totalRuns == 1
    assert result.runningRuns == 1
    assert result.succeededRuns == 0
    assert len(result.recentRuns) == 1
    assert result.recentRuns[0].id == "run-retail-1"
    assert result.recentRuns[0].runPlanId == "run-plan-retail"


@pytest.mark.anyio
async def test_get_gx_execution_run_statistics_filters_by_run_plan_id() -> None:
    repository = InMemoryGxExecutionRunRepository()
    suite_repository = InMemoryGxSuiteRepository()
    rules_repository = _StubRulesRepository()
    data_catalog_repository = _StubDataCatalogRepository()

    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-plan-filter-1",
                "suite_id": "gx-suite-1",
                "suite_version": 1,
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "correlation_id": "corr-plan-filter-1",
                "requested_by": "user-admin",
                "engine_type": "neutral-runtime",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "running",
                "submitted_at": "2026-04-16T09:45:00+00:00",
                "execution_contract": {
                    "engineType": "neutral-runtime",
                    "engineTarget": "pyspark",
                    "executionShape": "single_object",
                    "traceability": {
                        "ruleId": "rule-1",
                        "ruleVersionId": "rule-version-1",
                        "gxSuiteId": "gx-suite-1",
                        "gxSuiteVersion": 1,
                        "dataObjectVersionId": "dov-1",
                    },
                },
                "handoff_payload": {
                    "engine_type": "neutral-runtime",
                    "runPlanId": "run-plan-retail",
                },
            }
        )
    )
    await repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-plan-filter-2",
                "suite_id": "gx-suite-2",
                "suite_version": 1,
                "rule_id": "rule-2",
                "rule_version_id": "rule-version-2",
                "correlation_id": "corr-plan-filter-2",
                "requested_by": "user-admin",
                "engine_type": "batch-runtime",
                "engine_target": "spark",
                "execution_shape": "grouped_scope",
                "status": "succeeded",
                "submitted_at": "2026-04-16T09:30:00+00:00",
                "execution_contract": {
                    "engineType": "batch-runtime",
                    "engineTarget": "spark",
                    "executionShape": "grouped_scope",
                    "traceability": {
                        "ruleId": "rule-2",
                        "ruleVersionId": "rule-version-2",
                        "gxSuiteId": "gx-suite-2",
                        "gxSuiteVersion": 1,
                        "dataObjectVersionId": "dov-2",
                    },
                },
                "handoff_payload": {
                    "engine_type": "batch-runtime",
                    "runPlanId": "run-plan-corp",
                },
            }
        )
    )

    result = await get_gx_execution_run_statistics(
        query=GxExecutionRunStatisticsQuery(
            lookback_amount=24,
            lookback_unit="hours",
            recent_limit=10,
            run_plan_id="run-plan-retail",
        ),
        repository=repository,
        run_plan_repository=InMemoryGxRunPlanRepository(),
        suite_repository=suite_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        now=datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
    )

    assert result.totalRuns == 1
    assert result.runningRuns == 1
    assert result.succeededRuns == 0
    assert len(result.recentRuns) == 1
    assert result.recentRuns[0].id == "run-plan-filter-1"
    assert result.recentRuns[0].runPlanId == "run-plan-retail"


@pytest.mark.anyio
async def test_get_gx_execution_exception_analytics_aggregates_filtered_runs() -> None:
    repository = InMemoryGxExecutionRunRepository()
    suite_repository = InMemoryGxSuiteRepository()
    violation_repository = _StubViolationRepository()
    rules_repository = _StubRulesRepository()
    data_catalog_repository = _StubDataCatalogRepository()

    for run_id, correlation_id in (("run-123", "corr-123"), ("run-456", "corr-456")):
        await repository.create_run(
            build_gx_execution_run_create_entity(
                {
                    "run_id": run_id,
                    "suite_id": "gx-suite-1",
                    "suite_version": 1,
                    "rule_id": "rule-2",
                    "rule_version_id": "rule-version-2",
                    "correlation_id": correlation_id,
                    "requested_by": "user-admin",
                    "engine_type": "gx",
                    "engine_target": "pyspark",
                    "execution_shape": "single_object",
                    "status": "failed",
                    "submitted_at": "2026-04-16T08:00:00+00:00",
                    "execution_contract": {
                        "engineType": "gx",
                        "engineTarget": "pyspark",
                        "executionShape": "single_object",
                        "traceability": {
                            "ruleId": "rule-2",
                            "ruleVersionId": "rule-version-2",
                            "gxSuiteId": "gx-suite-1",
                            "gxSuiteVersion": 1,
                            "dataObjectVersionId": "dov-1",
                        },
                    },
                }
            )
        )

    result = await get_gx_execution_exception_analytics(
        query=GxExecutionExceptionAnalyticsQuery(
            lookback_amount=24,
            lookback_unit="hours",
        ),
        repository=repository,
        run_plan_repository=InMemoryGxRunPlanRepository(),
        suite_repository=suite_repository,
        projection_repository=violation_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        now=datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
    )

    assert violation_repository.last_kwargs is not None
    assert violation_repository.last_kwargs["data_object_version_ids"] == ["dov-1"]
    assert violation_repository.last_kwargs["execution_run_ids"] == ["run-123", "run-456"]
    assert result.totalFailedRecords == 6
    assert result.runsWithFailures == 2
    assert len(result.topRules) == 1
    assert result.topRules[0].ruleId == "rule-2"
    assert result.topRules[0].ruleName == "Transfer Match"
    assert result.topRules[0].total == 6
    assert len(result.topDataObjects) == 1
    assert result.topDataObjects[0].dataObjectVersionId == "dov-1"
    assert result.topDataObjects[0].dataObjectName == "Orders"
    assert result.topDataObjects[0].total == 6
    assert len(result.topReasons) == 2
    assert result.topReasons[0].reasonCode == "value_mismatch"
    assert result.topReasons[0].reasonText == "customer_id differs from golden source"
    assert result.topReasons[0].total == 4
    assert len(result.reasonTrendBuckets) == 3
    assert result.reasonTrendBuckets[0].reasonCode == "expect_column_values_to_not_be_null"
    assert result.reasonTrendBuckets[0].reasonText == "customer_id must not be null"
    assert result.reasonTrendBuckets[0].total == 2
    assert len(result.reasonFluctuations) == 2
    assert result.reasonFluctuations[0].reasonCode == "value_mismatch"
    assert result.reasonFluctuations[0].direction == "up"
    assert result.reasonFluctuations[0].netChange == 2
    assert result.reasonFluctuations[0].latestTotal == 3
    assert result.trendBuckets[0].total == 3
    assert result.trendBuckets[1].total == 3


@pytest.mark.anyio
async def test_get_gx_execution_exception_analytics_filters_one_reason_trend() -> None:
    repository = InMemoryGxExecutionRunRepository()
    suite_repository = InMemoryGxSuiteRepository()
    violation_repository = _StubViolationRepository()
    rules_repository = _StubRulesRepository()
    data_catalog_repository = _StubDataCatalogRepository()

    for run_id, correlation_id in (("run-123", "corr-123"), ("run-456", "corr-456")):
        await repository.create_run(
            build_gx_execution_run_create_entity(
                {
                    "run_id": run_id,
                    "suite_id": "gx-suite-1",
                    "suite_version": 1,
                    "rule_id": "rule-2",
                    "rule_version_id": "rule-version-2",
                    "correlation_id": correlation_id,
                    "requested_by": "user-admin",
                    "engine_type": "gx",
                    "engine_target": "pyspark",
                    "execution_shape": "single_object",
                    "status": "failed",
                    "submitted_at": "2026-04-16T08:00:00+00:00",
                    "execution_contract": {
                        "engineType": "gx",
                        "engineTarget": "pyspark",
                        "executionShape": "single_object",
                        "traceability": {
                            "ruleId": "rule-2",
                            "ruleVersionId": "rule-version-2",
                            "gxSuiteId": "gx-suite-1",
                            "gxSuiteVersion": 1,
                            "dataObjectVersionId": "dov-1",
                        },
                    },
                }
            )
        )

    result = await get_gx_execution_exception_analytics(
        query=GxExecutionExceptionAnalyticsQuery(
            lookback_amount=24,
            lookback_unit="hours",
            reason_code="value_mismatch",
        ),
        repository=repository,
        run_plan_repository=InMemoryGxRunPlanRepository(),
        suite_repository=suite_repository,
        projection_repository=violation_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        now=datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
    )

    assert violation_repository.last_kwargs is not None
    assert violation_repository.last_kwargs["reason_codes"] == ["value_mismatch"]
    assert result.totalFailedRecords == 4
    assert [item.reasonCode for item in result.topReasons] == ["value_mismatch"]
    assert all(item.reasonCode == "value_mismatch" for item in result.reasonTrendBuckets)
    assert len(result.reasonFluctuations) == 1
    assert result.reasonFluctuations[0].reasonCode == "value_mismatch"
    assert result.reasonFluctuations[0].direction == "up"
    assert result.reasonFluctuations[0].bucketCount == 2