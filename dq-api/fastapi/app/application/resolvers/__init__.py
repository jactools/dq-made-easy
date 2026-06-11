from app.application.resolvers.admin_resolver import (
	resolve_admin_roles_view,
	resolve_admin_user_view,
	resolve_admin_users_view,
	resolve_exception_fact_access_request_view,
	resolve_id_response,
)
from app.application.resolvers.app_config_resolver import resolve_app_config_view
from app.application.resolvers.approvals_resolver import (
	resolve_approval_audit_view,
	resolve_approval_view,
	resolve_approvals_page_view,
)
from app.application.resolvers.auth_resolver import resolve_login_response_view
from app.application.resolvers.data_catalog_resolver import (
	resolve_add_rule_attributes_result_view,
	resolve_attribute_definition_mapping_upsert_result_view,
	resolve_attribute_definition_mappings_view,
	resolve_attribute_rule_counts_view,
	resolve_attributes_catalog_page_view,
	resolve_data_deliveries_page_view,
	resolve_data_delivery_inventory_page_view,
	resolve_data_delivery_note_view,
	resolve_data_object_versions_page_view,
	resolve_data_objects_catalog_page_view,
	resolve_data_objects_view,
	resolve_data_products_page_view,
	resolve_data_sets_page_view,
	resolve_rule_attributes_view,
)
from app.application.resolvers.rule_resolver import resolve_rule_view
from app.application.resolvers.testing_resolver import (
	resolve_batch_test_request_list_view,
	resolve_batch_test_request_view,
	resolve_batch_test_requests_page_view,
	resolve_batch_test_run_result_view,
	resolve_store_test_proof_result_view,
	resolve_test_data_payload_view,
	resolve_test_proofs_view,
	resolve_test_run_result_view,
)
from app.application.resolvers.utility_resolver import (
	resolve_health_view,
	resolve_readiness_view,
	resolve_system_info_view,
)
from app.application.resolvers.workspaces_resolver import (
	resolve_workspace_view,
	resolve_workspaces_page_view,
)

__all__ = [
	"resolve_add_rule_attributes_result_view",
	"resolve_attribute_definition_mapping_upsert_result_view",
	"resolve_attribute_definition_mappings_view",
	"resolve_admin_roles_view",
	"resolve_admin_user_view",
	"resolve_admin_users_view",
	"resolve_exception_fact_access_request_view",
	"resolve_app_config_view",
	"resolve_approval_audit_view",
	"resolve_approval_view",
	"resolve_approvals_page_view",
	"resolve_attribute_rule_counts_view",
	"resolve_attributes_catalog_page_view",
	"resolve_batch_test_request_list_view",
	"resolve_batch_test_request_view",
	"resolve_batch_test_requests_page_view",
	"resolve_batch_test_run_result_view",
	"resolve_data_deliveries_page_view",
	"resolve_data_delivery_inventory_page_view",
	"resolve_data_delivery_note_view",
	"resolve_data_object_versions_page_view",
	"resolve_data_objects_catalog_page_view",
	"resolve_data_objects_view",
	"resolve_data_products_page_view",
	"resolve_data_sets_page_view",
	"resolve_id_response",
	"resolve_login_response_view",
	"resolve_rule_attributes_view",
	"resolve_rule_view",
	"resolve_health_view",
	"resolve_readiness_view",
	"resolve_system_info_view",
	"resolve_store_test_proof_result_view",
	"resolve_test_data_payload_view",
	"resolve_test_proofs_view",
	"resolve_test_run_result_view",
	"resolve_workspace_view",
	"resolve_workspaces_page_view",
]
