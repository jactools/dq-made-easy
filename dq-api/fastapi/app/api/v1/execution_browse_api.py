from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.api.v1.schemas import DqResultDriftSummaryView
from app.api.v1.schemas import ExceptionAnalyticsView
from app.api.v1.schemas import GxExecutionRunStatisticsView
from app.api.v1.schemas import GxExecutionRunSummaryView
from app.application.use_cases.dq_result_drift_detection import DqResultDriftQuery
from app.application.use_cases.dq_result_drift_detection import get_dq_result_drift_summary as get_dq_result_drift_summary_use_case
from app.application.use_cases.execution_queries import get_gx_execution_exception_analytics as get_gx_execution_exception_analytics_use_case
from app.application.use_cases.execution_queries import GxExecutionExceptionAnalyticsQuery
from app.application.use_cases.execution_queries import get_gx_execution_run_statistics as get_gx_execution_run_statistics_use_case
from app.application.use_cases.execution_queries import GxExecutionRunStatisticsQuery
from app.application.use_cases.execution_queries import list_gx_execution_run_summaries as list_gx_execution_run_summaries_use_case
from app.application.use_cases.execution_queries import ListGxExecutionRunsQuery
from app.domain.interfaces import DqResultEventRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import GxRunPlanRepository
from app.domain.interfaces import GxSuiteRepository
from app.domain.interfaces import RulesRepository
from dq_domain_validation import GxExecutionStatus
from dq_domain_validation import LookbackUnit


async def list_execution_runs(
    *,
    lookback_amount: int,
    lookback_unit: LookbackUnit,
    status: GxExecutionStatus | None,
    rule_name: str | None,
    owner: str | None,
    domain: str | None,
    severity: str | None,
    data_object_name: str | None,
    search: str | None,
    limit: int,
    data_product_id: str | None,
    dataset_id: str | None,
    data_object_id: str | None,
    data_object_version_id: str | None,
    delivery_id: str | None,
    workspace_id: str | None,
    run_plan_id: str | None,
    repository: GxExecutionRunRepository,
    run_plan_repository: GxRunPlanRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    suite_repository: GxSuiteRepository,
) -> list[GxExecutionRunSummaryView]:
    summaries = await list_gx_execution_run_summaries_use_case(
        query=ListGxExecutionRunsQuery(
            lookback_amount=lookback_amount,
            lookback_unit=lookback_unit,
            status=status,
            rule_name=rule_name,
            owner=owner,
            domain=domain,
            severity=severity,
            data_object_name=data_object_name,
            search=search,
            limit=limit,
            data_product_id=data_product_id,
            dataset_id=dataset_id,
            data_object_id=data_object_id,
            data_object_version_id=data_object_version_id,
            delivery_id=delivery_id,
            workspace_id=workspace_id,
            run_plan_id=run_plan_id,
        ),
        repository=repository,
        run_plan_repository=run_plan_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        suite_repository=suite_repository,
    )
    return [GxExecutionRunSummaryView.model_validate(summary) for summary in summaries]


async def list_execution_run_statistics(
    *,
    correlation_id: str,
    lookback_amount: int,
    lookback_unit: LookbackUnit,
    recent_limit: int,
    status: GxExecutionStatus | None,
    rule_name: str | None,
    owner: str | None,
    domain: str | None,
    severity: str | None,
    data_object_name: str | None,
    search: str | None,
    data_product_id: str | None,
    dataset_id: str | None,
    data_object_id: str | None,
    data_object_version_id: str | None,
    delivery_id: str | None,
    workspace_id: str | None,
    run_plan_id: str | None,
    repository: GxExecutionRunRepository,
    run_plan_repository: GxRunPlanRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    suite_repository: GxSuiteRepository,
) -> GxExecutionRunStatisticsView:
    try:
        statistics = await get_gx_execution_run_statistics_use_case(
            query=GxExecutionRunStatisticsQuery(
                lookback_amount=lookback_amount,
                lookback_unit=lookback_unit,
                recent_limit=recent_limit,
                status=status,
                rule_name=rule_name,
                owner=owner,
                domain=domain,
                severity=severity,
                data_object_name=data_object_name,
                search=search,
                data_product_id=data_product_id,
                dataset_id=dataset_id,
                data_object_id=data_object_id,
                data_object_version_id=data_object_version_id,
                delivery_id=delivery_id,
                workspace_id=workspace_id,
                run_plan_id=run_plan_id,
            ),
            repository=repository,
            run_plan_repository=run_plan_repository,
            rules_repository=rules_repository,
            data_catalog_repository=data_catalog_repository,
            suite_repository=suite_repository,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "execution_run_statistics_unavailable",
                "message": "GX execution run statistics are unavailable",
                "correlation_id": correlation_id,
                "exception": exc.__class__.__name__,
            },
        ) from exc

    return GxExecutionRunStatisticsView.model_validate(statistics)


async def get_exception_analytics(
    *,
    correlation_id: str,
    lookback_amount: int,
    lookback_unit: LookbackUnit,
    status: GxExecutionStatus | None,
    rule_name: str | None,
    data_object_name: str | None,
    search: str | None,
    reason_code: str | None,
    suite_id: str | None,
    data_product_id: str | None,
    dataset_id: str | None,
    data_object_id: str | None,
    data_object_version_id: str | None,
    delivery_id: str | None,
    rule_version_id: str | None,
    workspace_id: str | None,
    repository: GxExecutionRunRepository,
    run_plan_repository: GxRunPlanRepository,
    projection_repository: ExceptionReasonAnalyticsProjectionRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    suite_repository: GxSuiteRepository,
) -> ExceptionAnalyticsView:
    normalized_suite_id = suite_id if isinstance(suite_id, str) else None
    normalized_data_object_version_id = data_object_version_id if isinstance(data_object_version_id, str) else None
    normalized_rule_version_id = rule_version_id if isinstance(rule_version_id, str) else None
    try:
        analytics = await get_gx_execution_exception_analytics_use_case(
            query=GxExecutionExceptionAnalyticsQuery(
                lookback_amount=lookback_amount,
                lookback_unit=lookback_unit,
                status=status,
                rule_name=rule_name,
                data_object_name=data_object_name,
                search=search,
                reason_code=reason_code,
                suite_id=normalized_suite_id,
                data_product_id=data_product_id,
                dataset_id=dataset_id,
                data_object_id=data_object_id,
                data_object_version_id=normalized_data_object_version_id,
                delivery_id=delivery_id,
                rule_version_id=normalized_rule_version_id,
                workspace_id=workspace_id,
            ),
            repository=repository,
            run_plan_repository=run_plan_repository,
            projection_repository=projection_repository,
            rules_repository=rules_repository,
            data_catalog_repository=data_catalog_repository,
            suite_repository=suite_repository,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "exception_analytics_unavailable",
                "message": "GX execution exception analytics are unavailable",
                "correlation_id": correlation_id,
                "exception": exc.__class__.__name__,
            },
        ) from exc

    return ExceptionAnalyticsView.model_validate(analytics)


async def get_result_history_drift_summary(
    *,
    correlation_id: str,
    lookback_amount: int,
    lookback_unit: str,
    status: str | None,
    rule_id: str | None,
    dataset_id: str | None,
    domain_id: str | None,
    data_product_id: str | None,
    repository: DqResultEventRepository,
) -> DqResultDriftSummaryView:
    try:
        result = await get_dq_result_drift_summary_use_case(
            query=DqResultDriftQuery(
                lookback_amount=lookback_amount,
                lookback_unit=lookback_unit,
                status=status,
                rule_id=rule_id,
                dataset_id=dataset_id,
                domain_id=domain_id,
                data_product_id=data_product_id,
            ),
            repository=repository,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "dq_result_drift_unavailable",
                "message": "DQ result drift detection is unavailable",
                "correlation_id": correlation_id,
                "exception": exc.__class__.__name__,
            },
        ) from exc

    return DqResultDriftSummaryView.model_validate(result)