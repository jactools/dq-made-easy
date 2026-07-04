from functools import lru_cache
from uuid import uuid4

from fastapi import HTTPException

from app.application.services.data_contract_resolver import JoinConsistencyContractResolver
from app.application.services.data_contract_resolver import OpenMetadataContractResolver
from app.application.services.ui_registry import RegistryConfiguration
from app.application.services.ui_registry import RegistryManifest
from app.application.services.ui_registry import RegistryManager
from app.application.services.ui_registry import RegistrySource
from app.application.services.product_spec_resolver import OpenMetadataProductSpecResolver
from app.application.services.product_spec_resolver import ProductSpecResolver
from app.application.services.grouped_execution_planner import GroupedExecutionPlanner
from app.application.services.registry_definition_resolver import OpenMetadataRegistryDefinitionResolver
from app.application.services.registry_definition_resolver import RegistryDefinitionResolver
from app.application.services.source_data_resolver import SourceDataResolver
from app.core.config import PRIMARY_DATABASE_URL_ENV_NAMES
from app.core.config import get_settings
from app.core.request_context import get_correlation_id
from app.domain.entities.connector import build_connector_registry
from app.domain.entities.connector import load_connector_registry
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import AgentRequestAuditRepository
from app.domain.interfaces import ConnectorAuditRepository
from app.domain.interfaces import ConnectorInstanceRepository
from app.domain.interfaces import ConnectorRegistryRepository
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DataAssetRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import DataProtectionRepository
from app.domain.interfaces import DqResultEventRepository
from app.domain.interfaces import ExceptionFactRepository
from app.domain.interfaces import ExceptionAnalysisSessionRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.domain.interfaces import MasterDataRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import GxRunPlanRepository
from app.domain.interfaces import GxSuiteRepository
from app.domain.interfaces import ValidationArtifactRepository
from app.domain.interfaces import ValidationRunPlanRepository
from app.domain.interfaces import RulesRepository
from app.domain.interfaces import SuggestionsRepository
from app.domain.interfaces import SystemRepository
from app.domain.interfaces import TestingRepository
from app.domain.interfaces import ValidationRunRepository
from app.domain.interfaces import WorkspacesRepository
from app.domain.interfaces import ProfilingRepository
from app.domain.interfaces import MonitorScheduleRepository
from app.domain.interfaces import SlaSloRepository
from app.domain.interfaces import IncidentRepository
from app.domain.interfaces import OntologyGraphRepository
from app.domain.interfaces import FederatedMetadataRegistryRepository
from app.domain.interfaces import DQPlanTemplateRepository
from app.infrastructure.repositories import (
    InMemoryAdminRepository,
    InMemoryAgentRequestAuditRepository,
    InMemoryConnectorAuditRepository,
    InMemoryConnectorInstanceRepository,
    InMemoryApprovalsRepository,
    InMemoryAppConfigRepository,
    InMemoryDataCatalogRepository,
    InMemoryDataProtectionRepository,
    InMemoryDqResultEventRepository,
    InMemoryFederatedMetadataRegistryRepository,
    InMemoryGxExecutionRunRepository,
    InMemoryGxRunPlanRepository,
    InMemoryGxExecutionViolationRepository,
    InMemoryExceptionAnalysisSessionRepository,
    InMemoryGxSuiteRepository,
    InMemoryRulesRepository,
    InMemorySystemRepository,
    InMemoryTestingRepository,
    InMemoryValidationRunRepository,
    InMemoryWorkspacesRepository,
    PostgresAdminRepository,
    PostgresAgentRequestAuditRepository,
    PostgresConnectorAuditRepository,
    PostgresConnectorInstanceRepository,
    PostgresConnectorRegistryRepository,
    PostgresApprovalsRepository,
    PostgresAppConfigRepository,
    PostgresDataCatalogRepository,
    PostgresDataProtectionRepository,
    PostgresDqResultEventRepository,
    PostgresFederatedMetadataRegistryRepository,
    PostgresUiRegistryRepository,
    PostgresMasterDataRepository,
    PostgresDataAssetRepository,
    PostgresOntologyGraphRepository,
    PostgresGxExecutionRunRepository,
    PostgresGxRunPlanRepository,
    PostgresGxExecutionViolationRepository,
    PostgresExceptionAnalysisSessionRepository,
    PostgresExceptionReasonAnalyticsProjectionRepository,
    PostgresGxSuiteRepository,
    PostgresValidationArtifactRepository,
    PostgresValidationRunPlanRepository,
    PostgresRulesRepository,
    PostgresSuggestionsRepository,
    PostgresSystemRepository,
    PostgresTestingRepository,
    PostgresValidationRunRepository,
    PostgresWorkspacesRepository,
    PostgresSessionRepository,
    InMemoryProfilingRepository,
    RedisProfilingRepository,
    PostgresProfilingRepository,
    InMemoryMonitorScheduleRepository,
    InMemorySlaSloRepository,
    PostgresMonitorScheduleRepository,
    PostgresSlaSloRepository,
    InMemoryIncidentRepository,
    PostgresIncidentRepository,
)

_rules_repository = InMemoryRulesRepository()
_catalog_repository = InMemoryDataCatalogRepository()
_data_protection_repository = InMemoryDataProtectionRepository()
_system_repository = InMemorySystemRepository()
_app_config_repository = InMemoryAppConfigRepository()
_testing_repository = InMemoryTestingRepository()
_approvals_repository = InMemoryApprovalsRepository()
_agent_request_audit_repository = InMemoryAgentRequestAuditRepository()
_connector_audit_repository = InMemoryConnectorAuditRepository()
_workspaces_repository = InMemoryWorkspacesRepository()
_validation_run_repository = InMemoryValidationRunRepository()
_gx_suite_repository = InMemoryGxSuiteRepository()
_dq_result_event_repository = InMemoryDqResultEventRepository()
_gx_run_plan_repository = InMemoryGxRunPlanRepository()
_profiling_repository = InMemoryProfilingRepository()
_exception_fact_repository = InMemoryGxExecutionViolationRepository()
_exception_analysis_session_repository = InMemoryExceptionAnalysisSessionRepository()
_monitor_schedule_repository = InMemoryMonitorScheduleRepository()

_SUGGESTIONS_UNAVAILABLE_MESSAGE = (
    f"Suggestions API requires a configured {PRIMARY_DATABASE_URL_ENV_NAMES}. "
    "Feature is unavailable in this runtime."
)
_SESSION_STORE_UNAVAILABLE_DETAIL = {
    "error": "session_store_unavailable",
    "service": "session-store",
    "message": "Session store is unavailable",
}


def _repository_unavailable_detail(*, service: str, message: str) -> dict[str, str]:
    return {
        "error": "repository_unavailable",
        "service": service,
        "message": message,
        "correlation_id": get_correlation_id() or str(uuid4()),
    }


def _require_database_url(*, service: str, display_name: str) -> str:
    settings = get_settings()
    database_url = _get_database_url(settings)
    if database_url:
        return database_url
    raise HTTPException(
        status_code=503,
        detail=_repository_unavailable_detail(
            service=service,
            message=f"{display_name} requires a configured {PRIMARY_DATABASE_URL_ENV_NAMES}",
        ),
    )


def _get_database_url(settings) -> str | None:
    database_url = getattr(settings, "database_url", None)
    if database_url:
        return database_url
    if getattr(settings, "require_database", False):
        raise RuntimeError(f"{PRIMARY_DATABASE_URL_ENV_NAMES} is required when REQUIRE_DATABASE=true")
    return None


@lru_cache
def _get_postgres_rules_repository(database_url: str) -> PostgresRulesRepository:
    return PostgresRulesRepository(database_url)


def get_rules_repository() -> RulesRepository:
    database_url = _require_database_url(service="rules-repository", display_name="Rules repository")
    return _get_postgres_rules_repository(database_url)


@lru_cache
def _get_postgres_admin_repository(database_url: str) -> PostgresAdminRepository:
    return PostgresAdminRepository(database_url)


@lru_cache
def _get_postgres_catalog_repository(database_url: str) -> PostgresDataCatalogRepository:
    return PostgresDataCatalogRepository(database_url)


@lru_cache
def _get_postgres_data_protection_repository(database_url: str) -> PostgresDataProtectionRepository:
    return PostgresDataProtectionRepository(database_url)


@lru_cache
def _get_postgres_master_data_repository(database_url: str) -> PostgresMasterDataRepository:
    return PostgresMasterDataRepository(database_url)


@lru_cache
def _get_postgres_data_asset_repository(database_url: str) -> PostgresDataAssetRepository:
    return PostgresDataAssetRepository(database_url)


@lru_cache
def _get_postgres_dq_result_event_repository(database_url: str) -> PostgresDqResultEventRepository:
    return PostgresDqResultEventRepository(database_url)


@lru_cache
def _get_postgres_app_config_repository(database_url: str) -> PostgresAppConfigRepository:
    return PostgresAppConfigRepository(database_url)


@lru_cache
def _get_postgres_session_repository(database_url: str) -> PostgresSessionRepository:
    return PostgresSessionRepository(database_url)


@lru_cache
def _get_postgres_approvals_repository(database_url: str) -> PostgresApprovalsRepository:
    return PostgresApprovalsRepository(database_url)


@lru_cache
def _get_postgres_agent_request_audit_repository(database_url: str) -> PostgresAgentRequestAuditRepository:
    return PostgresAgentRequestAuditRepository(database_url)


@lru_cache
def _get_postgres_connector_audit_repository(database_url: str) -> PostgresConnectorAuditRepository:
    return PostgresConnectorAuditRepository(database_url)


@lru_cache
def _get_postgres_connector_instance_repository(database_url: str) -> PostgresConnectorInstanceRepository:
    return PostgresConnectorInstanceRepository(database_url)


@lru_cache
def _get_postgres_connector_registry_repository(database_url: str) -> PostgresConnectorRegistryRepository:
    return PostgresConnectorRegistryRepository(database_url)


@lru_cache(maxsize=8)
def _get_postgres_ui_registry_repository(database_url: str) -> PostgresUiRegistryRepository:
    return PostgresUiRegistryRepository(database_url)


@lru_cache
def _get_postgres_workspaces_repository(database_url: str) -> PostgresWorkspacesRepository:
    return PostgresWorkspacesRepository(database_url)


@lru_cache
def _get_postgres_system_repository(database_url: str) -> PostgresSystemRepository:
    return PostgresSystemRepository(database_url)


@lru_cache
def _get_postgres_suggestions_repository(database_url: str) -> PostgresSuggestionsRepository:
    return PostgresSuggestionsRepository(database_url)


@lru_cache
def _get_postgres_testing_repository(database_url: str) -> PostgresTestingRepository:
    return PostgresTestingRepository(database_url)


def get_data_catalog_repository() -> DataCatalogRepository:
    database_url = _require_database_url(service="data-catalog-repository", display_name="Data catalog repository")
    return _get_postgres_catalog_repository(database_url)


@lru_cache
def _get_openmetadata_product_spec_resolver(
    provider: str | None,
    endpoint: str | None,
    api_key: str | None,
    oidc_issuer: str | None,
    oidc_token_url: str | None,
    oidc_client_id: str | None,
    oidc_client_secret: str | None,
    oidc_scope: str | None,
    oidc_username: str | None,
    oidc_password: str | None,
    timeout_seconds: int,
) -> OpenMetadataProductSpecResolver:
    return OpenMetadataProductSpecResolver(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        oidc_issuer=oidc_issuer,
        oidc_token_url=oidc_token_url,
        oidc_client_id=oidc_client_id,
        oidc_client_secret=oidc_client_secret,
        oidc_scope=oidc_scope,
        oidc_username=oidc_username,
        oidc_password=oidc_password,
        timeout_seconds=timeout_seconds,
    )


def get_product_spec_resolver() -> ProductSpecResolver:
    settings = get_settings()
    return _get_openmetadata_product_spec_resolver(
        settings.catalog_provider,
        settings.catalog_endpoint,
        settings.catalog_api_key,
        settings.catalog_oidc_issuer,
        settings.catalog_oidc_token_url,
        settings.catalog_oidc_client_id,
        settings.catalog_oidc_client_secret,
        settings.catalog_oidc_scope,
        settings.catalog_oidc_username,
        settings.catalog_oidc_password,
        settings.catalog_timeout_seconds,
    )


def get_data_protection_repository() -> DataProtectionRepository:
    database_url = _require_database_url(service="data-protection-repository", display_name="Data protection repository")
    return _get_postgres_data_protection_repository(database_url)


def get_master_data_repository() -> MasterDataRepository:
    database_url = _require_database_url(service="master-data-repository", display_name="Master data repository")
    return _get_postgres_master_data_repository(database_url)


def get_data_asset_repository() -> DataAssetRepository:
    database_url = _require_database_url(service="data-asset-repository", display_name="Data asset repository")
    return _get_postgres_data_asset_repository(database_url)


@lru_cache
def _get_postgres_federated_metadata_registry_repository(database_url: str) -> PostgresFederatedMetadataRegistryRepository:
    return PostgresFederatedMetadataRegistryRepository(database_url)


def get_federated_metadata_registry_repository() -> FederatedMetadataRegistryRepository:
    database_url = _require_database_url(
        service="federated-metadata-registry-repository",
        display_name="Federated metadata registry repository",
    )
    return _get_postgres_federated_metadata_registry_repository(database_url)


@lru_cache
def _get_postgres_ontology_graph_repository(database_url: str) -> PostgresOntologyGraphRepository:
    return PostgresOntologyGraphRepository(database_url)


def get_ontology_graph_repository() -> OntologyGraphRepository:
    database_url = _require_database_url(service="ontology-graph-repository", display_name="Ontology graph repository")
    return _get_postgres_ontology_graph_repository(database_url)


def get_dq_result_event_repository() -> DqResultEventRepository:
    database_url = _require_database_url(service="dq-result-event-repository", display_name="DQ result event repository")
    return _get_postgres_dq_result_event_repository(database_url)


def get_admin_repository() -> AdminRepository:
    database_url = _require_database_url(service="admin-repository", display_name="Admin repository")
    return _get_postgres_admin_repository(database_url)


def get_app_config_repository() -> AppConfigRepository:
    database_url = _require_database_url(service="app-config-repository", display_name="App config repository")
    return _get_postgres_app_config_repository(database_url)


@lru_cache
def _get_ui_registry_manager(
    source: str,
    json_payload: str | None,
    file_path: str | None,
    url: str | None,
    expected_version: str,
    cache_ttl_seconds: int,
    repository: PostgresUiRegistryRepository | None,
) -> RegistryManager:
    configuration = RegistryConfiguration(
        source=None if source == "default" else RegistrySource(source),
        json_payload=json_payload,
        file_path=file_path,
        url=url,
        expected_version=expected_version,
        cache_ttl_seconds=cache_ttl_seconds,
    )
    return RegistryManager.from_configuration(configuration, repository=repository)


def get_ui_registry_manager() -> RegistryManager:
    settings = get_settings()
    repository = _get_postgres_ui_registry_repository(settings.database_url)
    return _get_ui_registry_manager(
        settings.ui_registry_source,
        settings.ui_registry_json,
        settings.ui_registry_file,
        settings.ui_registry_url,
        settings.ui_registry_manifest_version,
        settings.ui_registry_cache_ttl_seconds,
        repository,
    )


def get_ui_registry_manifest() -> RegistryManifest:
    return get_ui_registry_manager().load()


def get_session_repository() -> "SessionRepository":
    settings = get_settings()
    database_url = _get_database_url(settings)
    if database_url:
        return _get_postgres_session_repository(database_url)
    raise HTTPException(status_code=503, detail=dict(_SESSION_STORE_UNAVAILABLE_DETAIL))


def get_approvals_repository() -> ApprovalsRepository:
    database_url = _require_database_url(service="approvals-repository", display_name="Approvals repository")
    return _get_postgres_approvals_repository(database_url)


def get_agent_request_audit_repository() -> AgentRequestAuditRepository:
    database_url = _require_database_url(
        service="agent-request-audit-repository",
        display_name="Agent request audit repository",
    )
    return _get_postgres_agent_request_audit_repository(database_url)


def get_connector_audit_repository() -> ConnectorAuditRepository:
    database_url = _require_database_url(
        service="connector-audit-repository",
        display_name="Connector audit repository",
    )
    return _get_postgres_connector_audit_repository(database_url)


def get_connector_instance_repository() -> ConnectorInstanceRepository:
    database_url = _require_database_url(
        service="connector-instance-repository",
        display_name="Connector instance repository",
    )
    return _get_postgres_connector_instance_repository(database_url)


def bootstrap_connector_registry() -> ConnectorRegistryRepository:
    database_url = _require_database_url(
        service="connector-registry-repository",
        display_name="Connector registry repository",
    )
    repository = _get_postgres_connector_registry_repository(database_url)
    persisted_entries = repository.list_entries()
    if not persisted_entries:
        for entry in build_connector_registry().entries:
            repository.upsert_entry(entry)
        persisted_entries = repository.list_entries()
    load_connector_registry(persisted_entries)
    return repository


def get_connector_registry_repository() -> ConnectorRegistryRepository:
    database_url = _require_database_url(
        service="connector-registry-repository",
        display_name="Connector registry repository",
    )
    repository = _get_postgres_connector_registry_repository(database_url)
    if not repository.list_entries():
        for entry in build_connector_registry().entries:
            repository.upsert_entry(entry)
    return repository


def get_workspaces_repository() -> WorkspacesRepository:
    database_url = _require_database_url(service="workspaces-repository", display_name="Workspaces repository")
    return _get_postgres_workspaces_repository(database_url)


def get_system_repository() -> SystemRepository:
    database_url = _require_database_url(service="system-repository", display_name="System repository")
    return _get_postgres_system_repository(database_url)


def get_suggestions_repository() -> SuggestionsRepository:
    settings = get_settings()
    database_url = _get_database_url(settings)
    if database_url:
        return _get_postgres_suggestions_repository(database_url)
    raise HTTPException(status_code=503, detail=_SUGGESTIONS_UNAVAILABLE_MESSAGE)


def get_testing_repository() -> TestingRepository:
    database_url = _require_database_url(service="testing-repository", display_name="Testing repository")
    return _get_postgres_testing_repository(database_url)


@lru_cache
def _get_postgres_validation_run_repository(database_url: str) -> PostgresValidationRunRepository:
    return PostgresValidationRunRepository(database_url)


def get_validation_run_repository() -> ValidationRunRepository:
    database_url = _require_database_url(service="validation-run-repository", display_name="Validation run repository")
    return _get_postgres_validation_run_repository(database_url)


@lru_cache
def _get_postgres_validation_artifact_repository(database_url: str) -> PostgresValidationArtifactRepository:
    return PostgresValidationArtifactRepository(database_url)


def get_validation_artifact_repository() -> ValidationArtifactRepository:
    database_url = _require_database_url(
        service="validation-artifact-repository",
        display_name="Validation artifact repository",
    )
    return _get_postgres_validation_artifact_repository(database_url)


_gx_execution_run_repository = InMemoryGxExecutionRunRepository()


@lru_cache
def _get_postgres_gx_execution_run_repository(database_url: str) -> PostgresGxExecutionRunRepository:
    return PostgresGxExecutionRunRepository(database_url)


def get_gx_execution_run_repository() -> GxExecutionRunRepository:
    database_url = _require_database_url(service="gx-execution-run-repository", display_name="GX execution run repository")
    return _get_postgres_gx_execution_run_repository(database_url)


@lru_cache
def _get_postgres_gx_run_plan_repository(database_url: str) -> PostgresGxRunPlanRepository:
    return PostgresGxRunPlanRepository(database_url)


def get_gx_run_plan_repository() -> GxRunPlanRepository:
    database_url = _require_database_url(service="gx-run-plan-repository", display_name="GX run plan repository")
    return _get_postgres_gx_run_plan_repository(database_url)


@lru_cache
def _get_postgres_validation_run_plan_repository(database_url: str) -> PostgresValidationRunPlanRepository:
    return PostgresValidationRunPlanRepository(database_url)


def get_validation_run_plan_repository() -> ValidationRunPlanRepository:
    database_url = _require_database_url(
        service="validation-run-plan-repository",
        display_name="Validation run plan repository",
    )
    return _get_postgres_validation_run_plan_repository(database_url)


@lru_cache
def _get_postgres_exception_fact_repository(database_url: str) -> PostgresGxExecutionViolationRepository:
    return PostgresGxExecutionViolationRepository(database_url)


@lru_cache
def _get_postgres_exception_analysis_session_repository(database_url: str) -> PostgresExceptionAnalysisSessionRepository:
    return PostgresExceptionAnalysisSessionRepository(database_url)


def get_exception_fact_repository() -> ExceptionFactRepository:
    database_url = _require_database_url(
        service="exception-fact-repository",
        display_name="Exception fact repository",
    )
    return _get_postgres_exception_fact_repository(database_url)


def get_exception_analysis_session_repository() -> ExceptionAnalysisSessionRepository:
    database_url = _require_database_url(
        service="exception-analysis-session-repository",
        display_name="Exception analysis session repository",
    )
    return _get_postgres_exception_analysis_session_repository(database_url)


@lru_cache
def _get_postgres_exception_reason_analytics_projection_repository(database_url: str) -> PostgresExceptionReasonAnalyticsProjectionRepository:
    return PostgresExceptionReasonAnalyticsProjectionRepository(database_url)


def get_exception_reason_analytics_projection_repository() -> ExceptionReasonAnalyticsProjectionRepository:
    database_url = _require_database_url(
        service="exception-reason-analytics-projection-repository",
        display_name="Exception reason analytics projection repository",
    )
    return _get_postgres_exception_reason_analytics_projection_repository(database_url)


@lru_cache
def _get_postgres_gx_suite_repository(database_url: str) -> PostgresGxSuiteRepository:
    return PostgresGxSuiteRepository(database_url)


def get_gx_suite_repository() -> GxSuiteRepository:
    database_url = _require_database_url(service="gx-suite-repository", display_name="GX suite repository")
    return _get_postgres_gx_suite_repository(database_url)


@lru_cache
def _get_postgres_profiling_repository(database_url: str) -> PostgresProfilingRepository:
    return PostgresProfilingRepository(database_url)


def get_profiling_repository() -> ProfilingRepository:
    database_url = _require_database_url(service="profiling-repository", display_name="Profiling repository")
    return _get_postgres_profiling_repository(database_url)


@lru_cache
def _get_openmetadata_contract_resolver(
    provider: str | None,
    endpoint: str | None,
    api_key: str | None,
    oidc_issuer: str | None,
    oidc_token_url: str | None,
    oidc_client_id: str | None,
    oidc_client_secret: str | None,
    oidc_scope: str | None,
    oidc_username: str | None,
    oidc_password: str | None,
    timeout_seconds: int,
    redis_host: str | None,
    redis_port: int,
    redis_db: int,
    redis_password: str | None,
    redis_contract_cache_key_prefix: str,
) -> OpenMetadataContractResolver:
    return OpenMetadataContractResolver(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        oidc_issuer=oidc_issuer,
        oidc_token_url=oidc_token_url,
        oidc_client_id=oidc_client_id,
        oidc_client_secret=oidc_client_secret,
        oidc_scope=oidc_scope,
        oidc_username=oidc_username,
        oidc_password=oidc_password,
        timeout_seconds=timeout_seconds,
        redis_host=redis_host,
        redis_port=redis_port,
        redis_db=redis_db,
        redis_password=redis_password,
        redis_contract_cache_key_prefix=redis_contract_cache_key_prefix,
    )


def get_join_consistency_contract_resolver() -> JoinConsistencyContractResolver:
    settings = get_settings()
    return _get_openmetadata_contract_resolver(
        settings.catalog_provider,
        settings.catalog_endpoint,
        settings.catalog_api_key,
        settings.catalog_oidc_issuer,
        settings.catalog_oidc_token_url,
        settings.catalog_oidc_client_id,
        settings.catalog_oidc_client_secret,
        settings.catalog_oidc_scope,
        settings.catalog_oidc_username,
        settings.catalog_oidc_password,
        settings.catalog_timeout_seconds,
        settings.redis_host,
        settings.redis_port,
        settings.redis_db,
        settings.redis_password,
        settings.redis_contract_cache_key_prefix,
    )


@lru_cache
def _get_openmetadata_registry_definition_resolver(
    provider: str | None,
    endpoint: str | None,
    api_key: str | None,
    oidc_issuer: str | None,
    oidc_token_url: str | None,
    oidc_client_id: str | None,
    oidc_client_secret: str | None,
    oidc_scope: str | None,
    oidc_username: str | None,
    oidc_password: str | None,
    timeout_seconds: int,
) -> OpenMetadataRegistryDefinitionResolver:
    return OpenMetadataRegistryDefinitionResolver(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        oidc_issuer=oidc_issuer,
        oidc_token_url=oidc_token_url,
        oidc_client_id=oidc_client_id,
        oidc_client_secret=oidc_client_secret,
        oidc_scope=oidc_scope,
        oidc_username=oidc_username,
        oidc_password=oidc_password,
        timeout_seconds=timeout_seconds,
    )


def get_registry_definition_resolver() -> RegistryDefinitionResolver:
    settings = get_settings()
    return _get_openmetadata_registry_definition_resolver(
        settings.catalog_provider,
        settings.catalog_endpoint,
        settings.catalog_api_key,
        settings.catalog_oidc_issuer,
        settings.catalog_oidc_token_url,
        settings.catalog_oidc_client_id,
        settings.catalog_oidc_client_secret,
        settings.catalog_oidc_scope,
        settings.catalog_oidc_username,
        settings.catalog_oidc_password,
        settings.catalog_timeout_seconds,
    )


def get_source_data_resolver() -> SourceDataResolver:
    return SourceDataResolver(catalog_repository=get_data_catalog_repository())


def get_grouped_execution_planner() -> GroupedExecutionPlanner:
    return GroupedExecutionPlanner()


@lru_cache
def _get_postgres_monitor_schedule_repository(database_url: str) -> PostgresMonitorScheduleRepository:
    return PostgresMonitorScheduleRepository(database_url)


@lru_cache
def _get_postgres_sla_slo_repository(database_url: str) -> PostgresSlaSloRepository:
    return PostgresSlaSloRepository(database_url)


def get_monitor_schedule_repository() -> MonitorScheduleRepository:
    database_url = _require_database_url(
        service="monitor-schedule-repository", display_name="Monitor schedule repository"
    )
    return _get_postgres_monitor_schedule_repository(database_url)


def get_sla_slo_repository() -> SlaSloRepository:
    database_url = _require_database_url(
        service="sla-slo-repository", display_name="SLA/SLO repository"
    )
    return _get_postgres_sla_slo_repository(database_url)


@lru_cache
def _get_postgres_incident_repository(database_url: str) -> PostgresIncidentRepository:
    return PostgresIncidentRepository(database_url)


def get_incident_repository() -> IncidentRepository:
    database_url = _require_database_url(
        service="incident-repository", display_name="Incident repository"
    )
    return _get_postgres_incident_repository(database_url)


@lru_cache
def _get_postgres_dq_plan_template_repository(database_url: str) -> PostgresDQPlanTemplateRepository:
    from app.infrastructure.repositories.postgres_dq_plan_template_repository import PostgresDQPlanTemplateRepository
    return PostgresDQPlanTemplateRepository(database_url)


def get_dq_plan_template_repository() -> DQPlanTemplateRepository:
    database_url = _require_database_url(
        service="dq-plan-template-repository", display_name="DQ Plan template repository"
    )
    return _get_postgres_dq_plan_template_repository(database_url)
