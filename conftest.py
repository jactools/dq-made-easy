from __future__ import annotations

"""Top-level pytest conftest to aid local test runs.

This file mirrors key environment setup from `dq-api/fastapi/tests/conftest.py`,
adds local package `src/` folders to `sys.path` so subpackages (e.g. `dq_utils`,
`dq_domain_validation`, and `app`) are importable during collection, and
re-exports the pytest plugins declared in the API tests so pytest no longer
errors about non-top-level `pytest_plugins` definitions.

This is a local developer convenience to run the whole test suite in-place.
"""

import importlib.util
import os
import subprocess
import sys

import pytest

from spark_container_test_harness import build_container_test_command, should_route_spark_tests_to_container

ROOT = os.path.dirname(__file__)

# Replicate important environment defaults used by API tests
os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
_database_url_explicit = "DQ_DB_LOCAL_URL" in os.environ
os.environ.setdefault("DQ_DB_HOST", os.environ.get("DQ_DB_HOST", "dq-db.jac.dot"))
if not _database_url_explicit:
    os.environ["DQ_DB_LOCAL_URL"] = f"postgresql://postgres:postgres@{os.environ['DQ_DB_HOST']}:5432/dq"
    os.environ["DQ_TEST_DEFAULT_DATABASE_URL"] = "1"
os.environ.setdefault("REQUIRE_DATABASE", "false")
os.environ.setdefault("SSO_ENABLED", "true")
os.environ.setdefault("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
os.environ.setdefault("SSO_CLIENT_ID", "dq-rules-ui")
os.environ["NATURAL_LANGUAGE_DRAFT_QUEUE_KEY"] = ""
# Disable OTEL exporters during tests (matches API tests)
os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")
os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "")
os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "")
os.environ["APP_CONFIG_ENCRYPTION_KEY"] = "i0aU2BE0dzqEVAWxfEsvffw5zw93FjFZrr24RPVyo8c="

# Make commonly-used local package source dirs importable during tests
local_src_paths = [
    os.path.join(ROOT, "dq-api", "fastapi"),
    os.path.join(ROOT, "dq-utils", "src"),
    os.path.join(ROOT, "dq-domain-validation", "src"),
]
for p in local_src_paths:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

# Re-export pytest plugins declared in dq-api/fastapi/tests/conftest.py so pytest
# no longer errors about non-top-level pytest_plugins definitions.
_api_plugins = [
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

# Register the API test fixtures under a unique namespace to avoid colliding
# with the repo's top-level `tests` package. Each original plugin like
# `tests.fixtures.shared_fixtures` will be exposed as
# `dq_api_tests.fixtures.shared_fixtures` for pytest to discover.
plugin_map: dict[str, str] = {}
for orig in _api_plugins:
    suffix = ".".join(orig.split(".")[1:])
    new_name = f"dq_api_tests.{suffix}"
    file_path = os.path.join(ROOT, "dq-api", "fastapi", *orig.split(".")) + ".py"
    plugin_map[new_name] = file_path

# Load plugin modules first so they are present in sys.modules when pytest
# tries to import them (pytest imports plugin names early during conftest
# registration).
for name, file_path in plugin_map.items():
    try:
        if os.path.exists(file_path):
            # Ensure parent package modules exist so Python can import the
            # dotted module name (e.g. 'dq_api_tests.fixtures.shared_fixtures').
            parts = name.split(".")
            for i in range(1, len(parts)):
                pkg_name = ".".join(parts[:i])
                if pkg_name not in sys.modules:
                    import types

                    pkg = types.ModuleType(pkg_name)
                    # Mark as a package
                    pkg.__path__ = []
                    sys.modules[pkg_name] = pkg

            spec = importlib.util.spec_from_file_location(name, file_path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            assert spec.loader is not None
            spec.loader.exec_module(mod)
    except Exception:
        # best-effort import; let pytest surface import-time errors later
        pass

pytest_plugins = list(plugin_map.keys())


def pytest_configure(config):
    """Route Spark Expectations test runs to the containerized validation harness."""
    if os.getenv("DQ_SPARK_CONTAINER_TESTS_ROUTED") == "1":
        return

    if os.getenv("DQ_DISABLE_CONTAINER_SPARK_TEST_ROUTING"):
        return

    invocation_params = getattr(config, "invocation_params", None)
    args = list(getattr(invocation_params, "args", []) or [])
    if should_route_spark_tests_to_container(args):
        command = build_container_test_command(args)
        if command:
            os.environ["DQ_SPARK_CONTAINER_TESTS_ROUTED"] = "1"
            print(f"Routing Spark Expectations pytest targets to container: {' '.join(command)}", file=sys.stderr)
            returncode = subprocess.run(command, check=False).returncode
            raise pytest.exit(f"Spark Expectations pytest run completed with exit code {returncode}", returncode=returncode)
