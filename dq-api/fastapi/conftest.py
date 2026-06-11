from __future__ import annotations

pytest_plugins = [
    "tests.fixtures.shared_fixtures",
    "tests.fixtures.app_config_fixtures",
    "tests.fixtures.approvals_fixtures",
    "tests.fixtures.auth_fixtures",
    "tests.fixtures.data_catalog_fixtures",
    "tests.fixtures.database_fixtures",
    "tests.fixtures.if_statement_audit_fixtures",
    "tests.fixtures.rule_compiler_fixtures",
    "tests.fixtures.suggestions_fixtures",
    "tests.fixtures.reusable_assets_fixtures",
    "tests.fixtures.system_fixtures",
    "tests.fixtures.testing_fixtures",
    "tests.fixtures.user_fixtures",
    "tests.fixtures.workspace_fixtures",
]