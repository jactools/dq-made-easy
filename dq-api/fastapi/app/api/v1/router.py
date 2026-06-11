from fastapi import APIRouter

from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.approvals import router as approvals_router
from app.api.v1.endpoints.app_config import router as app_config_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.catalog_governance import router as catalog_governance_router
from app.api.v1.endpoints.connectors import router as connectors_router
from app.api.v1.endpoints.onboarding import router as onboarding_router
from app.api.v1.endpoints.data_assets import router as data_assets_router
from app.api.v1.endpoints.data_catalog import router as data_catalog_router
from app.api.v1.endpoints.product_specs import router as product_specs_router
from app.api.v1.endpoints.metadata_registry import router as metadata_registry_router
from app.api.v1.endpoints.ontology import router as ontology_router
from app.api.v1.endpoints.data_protection import router as data_protection_router
from app.api.v1.endpoints.data_contracts import router as data_contracts_router
from app.api.v1.endpoints.master_data import router as master_data_router
from app.api.v1.endpoints.execution_monitoring import router as gx_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.health_scorecards import router as health_scorecards_router
from app.api.v1.endpoints.registry_definitions import router as registry_definitions_router
from app.api.v1.endpoints.reusable_assets import router as reusable_assets_router
from app.api.v1.endpoints.rules import router as rules_router
from app.api.v1.endpoints.suggestions import router as suggestions_router
from app.api.v1.endpoints.status_governance import router as status_governance_router
from app.api.v1.endpoints.system import router as system_router
from app.api.v1.endpoints.testing import router as testing_router
from app.api.v1.endpoints.validation_runs import router as validation_runs_router
from app.api.v1.endpoints.workspaces import router as workspaces_router
from app.api.v1.endpoints.profiling_enqueue import router as profiling_enqueue_router
from app.api.v1.endpoints.demo_snake import router as demo_snake_router
from app.api.v1.endpoints.exceptions import router as exceptions_router
from app.api.v1.endpoints.exception_reports import router as exception_reports_router
from app.api.v1.endpoints.exception_fact_access_requests import router as exception_fact_access_requests_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.profiling import router as profiling_router
from app.api.v1.endpoints.run_plan import router as run_plan_router
from app.api.v1.endpoints.validation_run_plans import router as validation_run_plans_router
from app.api.v1.endpoints.incidents import router as incidents_router
from app.api.v1.endpoints.support import router as support_router
from app.api.v1.endpoints.service_levels import router as service_levels_router
from app.api.v1.endpoints.user import router as user_router
from app.api.v1.endpoints.agent import router as agent_router

api_router = APIRouter()
internal_api_router = APIRouter()

# Functional-group routing: /<group>/v1/<endpoint>
auth_group = APIRouter(prefix="/auth/v1")
auth_group.include_router(auth_router)
api_router.include_router(auth_group)

admin_group = APIRouter(prefix="/admin/v1")
admin_group.include_router(admin_router)
api_router.include_router(admin_group)

user_group = APIRouter(prefix="/user/v1")
user_group.include_router(user_router)
api_router.include_router(user_group)

system_group = APIRouter(prefix="/system/v1")
system_group.include_router(system_router)
system_group.include_router(app_config_router)
system_group.include_router(data_protection_router)
system_group.include_router(health_router)
system_group.include_router(support_router)
api_router.include_router(system_group)

data_catalog_group = APIRouter(prefix="/data-catalog/v1")
data_catalog_group.include_router(data_catalog_router)
data_catalog_group.include_router(data_contracts_router)
data_catalog_group.include_router(product_specs_router)
data_catalog_group.include_router(registry_definitions_router)
data_catalog_group.include_router(metadata_registry_router)
data_catalog_group.include_router(ontology_router)
data_catalog_group.include_router(profiling_router)
data_catalog_group.include_router(suggestions_router)
api_router.include_router(data_catalog_group)

master_data_group = APIRouter(prefix="/master-data/v1")
master_data_group.include_router(master_data_router)
api_router.include_router(master_data_group)

# Default "rulebuilder" functional group for the remaining API surface.
rulebuilder_group = APIRouter(prefix="/rulebuilder/v1")
rulebuilder_group.include_router(approvals_router)
rulebuilder_group.include_router(catalog_governance_router)
rulebuilder_group.include_router(connectors_router)
rulebuilder_group.include_router(data_assets_router)
rulebuilder_group.include_router(exceptions_router)
rulebuilder_group.include_router(exception_reports_router)
rulebuilder_group.include_router(exception_fact_access_requests_router)
rulebuilder_group.include_router(health_scorecards_router)
rulebuilder_group.include_router(gx_router)
rulebuilder_group.include_router(reusable_assets_router)
rulebuilder_group.include_router(validation_runs_router)
rulebuilder_group.include_router(rules_router)
rulebuilder_group.include_router(status_governance_router)
rulebuilder_group.include_router(testing_router)
rulebuilder_group.include_router(workspaces_router)
rulebuilder_group.include_router(profiling_enqueue_router)
rulebuilder_group.include_router(demo_snake_router)
rulebuilder_group.include_router(notifications_router)
rulebuilder_group.include_router(run_plan_router)
rulebuilder_group.include_router(incidents_router)
rulebuilder_group.include_router(service_levels_router)
rulebuilder_group.include_router(onboarding_router)
api_router.include_router(rulebuilder_group)

agent_group = APIRouter(prefix="/agent/v1")
agent_group.include_router(agent_router)
api_router.include_router(agent_group)

internal_rulebuilder_group = APIRouter(prefix="/rulebuilder/v1")
internal_rulebuilder_group.include_router(validation_run_plans_router)
internal_api_router.include_router(internal_rulebuilder_group)
