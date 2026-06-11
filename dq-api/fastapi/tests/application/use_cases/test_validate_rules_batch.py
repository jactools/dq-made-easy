import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.use_cases.validate_rules_batch import validate_rules_batch
from app.application.use_cases.validate_rules_batch import ValidateRulesBatchCommand


pytestmark = pytest.mark.usefixtures("clone_payload")


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def batch_repository():
    class _Repository:
        def __init__(self) -> None:
            self.rules = {
                "rule-1": SimpleNamespace(name="Rule One", expression="email IS NOT NULL", workspace="default"),
            }

        async def get_rule_by_id(self, rule_id: str):
            return self.rules.get(rule_id)

    return _Repository()


@pytest.fixture
def data_catalog_repository():
    class _Repository:
        def list_rule_attributes(self):
            return [SimpleNamespace(ruleId="rule-1", attributeId="attr-email")]

        def list_attributes_catalog(self, version_id: str | None = None):
            del version_id
            return [SimpleNamespace(id="attr-email")]

    return _Repository()


@pytest.fixture
def config_repository():
    class _ConfigRepository:
        def get_app_config(self):
            return SimpleNamespace(validationPolicies=[])

    return _ConfigRepository()


@pytest.fixture
def run_repository():
    class _RunRepository:
        def __init__(self) -> None:
            self.saved_runs: list[dict] = []
            self.raise_error = False

        async def save_run(self, **kwargs):
            if self.raise_error:
                raise RuntimeError("store unavailable")
            self.saved_runs.append(kwargs)
            return {"ok": True}

    return _RunRepository()


@pytest.fixture
def batch_callbacks():
    calls: dict[str, object] = {"persist": []}

    def apply_validation_policies(raw_diagnostics, raw_policies, workspace):
        del raw_policies, workspace
        return list(raw_diagnostics)

    def compile_rule_to_intermediate_model(**kwargs):
        calls.setdefault("compile", []).append(kwargs)
        return {
            "artifactKey": f"artifact-{kwargs['rule_id']}",
            "compilerVersion": "dq-7.3.0",
            "target": "dsl",
            "compilable": True,
            "filter": {"normalized": f"compiled::{kwargs['rule_id']}"},
            "diagnostics": [],
        }

    def infer_alias_expectations(expression: str):
        return [{"alias": expression, "expected": expression}]

    async def persist_compiler_artifact(repository, **kwargs):
        del repository
        calls["persist"].append(kwargs)
        return {"ok": True}

    async def resolve_current_rule_version(repository, rule_id: str):
        del repository
        return SimpleNamespace(id=f"rv-{rule_id}", versionNumber=7)

    def has_upstream_validation_issue(diagnostics):
        del diagnostics
        return False

    def detect_conflicts(compilable_summaries):
        calls["conflicts_input"] = compilable_summaries
        return [
            {
                "ruleId": "rule-1",
                "conflictsWith": "rule-missing",
                "conflictType": "duplicate_expression",
                "message": "overlap",
            }
        ]

    logger = SimpleNamespace(warnings=[])

    def warning(message, *args):
        logger.warnings.append(message % args)

    logger.warning = warning

    return SimpleNamespace(
        calls=calls,
        apply_validation_policies=apply_validation_policies,
        compile_rule_to_intermediate_model=compile_rule_to_intermediate_model,
        infer_alias_expectations=infer_alias_expectations,
        persist_compiler_artifact=persist_compiler_artifact,
        resolve_current_rule_version=resolve_current_rule_version,
        has_upstream_validation_issue=has_upstream_validation_issue,
        detect_conflicts=detect_conflicts,
        logger=logger,
    )


@pytest.fixture
def fixed_now():
    return lambda: datetime(2026, 4, 24, 12, 0, tzinfo=UTC)


def test_validate_rules_batch_returns_results_conflicts_and_persists_run(
    batch_repository,
    data_catalog_repository,
    config_repository,
    run_repository,
    batch_callbacks,
    fixed_now,
) -> None:
    payload = _run(
        validate_rules_batch(
            ValidateRulesBatchCommand(
                rule_ids=["rule-1", "rule-missing"],
                workspace="default",
                triggered_by="user-1",
            ),
            batch_repository,
            data_catalog_repository,
            config_repository,
            run_repository,
            apply_validation_policies=batch_callbacks.apply_validation_policies,
            compile_rule_to_intermediate_model=batch_callbacks.compile_rule_to_intermediate_model,
            infer_alias_expectations=batch_callbacks.infer_alias_expectations,
            persist_compiler_artifact=batch_callbacks.persist_compiler_artifact,
            resolve_current_rule_version=batch_callbacks.resolve_current_rule_version,
            has_upstream_validation_issue=batch_callbacks.has_upstream_validation_issue,
            detect_conflicts=batch_callbacks.detect_conflicts,
            logger=batch_callbacks.logger,
            uuid_factory=lambda: "run-123",
            now=fixed_now,
        )
    )

    assert payload["runId"] == "run-123"
    assert payload["summary"] == {"total": 2, "valid": 1, "invalid": 1, "errors": 1, "warnings": 0}
    assert payload["results"][0]["ruleId"] == "rule-1"
    assert payload["results"][0]["ruleVersionNumber"] == 7
    assert payload["results"][1] == {
        "ruleId": "rule-missing",
        "ruleName": None,
        "valid": False,
        "compiledExpression": "",
        "artifactKey": None,
        "compilerVersion": None,
        "errors": 1,
        "warnings": 0,
        "diagnostics": [
            {
                "code": "DQ1_RULE_NOT_FOUND",
                "severity": "error",
                "message": "Rule 'rule-missing' was not found",
                "scope": "rule",
            }
        ],
    }
    assert batch_callbacks.calls["conflicts_input"] == [
        {
            "ruleId": "rule-1",
            "ruleName": "Rule One",
            "compiledExpression": "compiled::rule-1",
        }
    ]
    assert run_repository.saved_runs == [
        {
            "run_id": "run-123",
            "workspace": "default",
            "triggered_by": "user-1",
            "run_at": "2026-04-24T12:00:00+00:00",
            "total": 2,
            "valid_count": 1,
            "invalid_count": 1,
            "status": "complete",
            "items": [
                {
                    "ruleId": "rule-1",
                    "ruleName": "Rule One",
                    "ruleVersionNumber": 7,
                    "valid": True,
                    "errors": 0,
                    "warnings": 0,
                    "diagnostics": [],
                    "conflicts": [
                        {
                            "ruleId": "rule-1",
                            "conflictsWith": "rule-missing",
                            "conflictType": "duplicate_expression",
                            "message": "overlap",
                        }
                    ],
                },
                {
                    "ruleId": "rule-missing",
                    "ruleName": None,
                    "ruleVersionNumber": None,
                    "valid": False,
                    "errors": 1,
                    "warnings": 0,
                    "diagnostics": [
                        {
                            "code": "DQ1_RULE_NOT_FOUND",
                            "severity": "error",
                            "message": "Rule 'rule-missing' was not found",
                            "scope": "rule",
                        }
                    ],
                    "conflicts": [
                        {
                            "ruleId": "rule-1",
                            "conflictsWith": "rule-missing",
                            "conflictType": "duplicate_expression",
                            "message": "overlap",
                        }
                    ],
                },
            ],
        }
    ]


@pytest.mark.parametrize(
    ("rule_ids", "message"),
    [([], "ruleIds must not be empty"), ([f"rule-{index}" for index in range(101)], "Batch size cannot exceed 100 rules")],
)
def test_validate_rules_batch_rejects_invalid_batch_sizes(
    rule_ids,
    message,
    batch_repository,
    data_catalog_repository,
    config_repository,
    run_repository,
    batch_callbacks,
    fixed_now,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _run(
            validate_rules_batch(
                ValidateRulesBatchCommand(rule_ids=rule_ids),
                batch_repository,
                data_catalog_repository,
                config_repository,
                run_repository,
                apply_validation_policies=batch_callbacks.apply_validation_policies,
                compile_rule_to_intermediate_model=batch_callbacks.compile_rule_to_intermediate_model,
                infer_alias_expectations=batch_callbacks.infer_alias_expectations,
                persist_compiler_artifact=batch_callbacks.persist_compiler_artifact,
                resolve_current_rule_version=batch_callbacks.resolve_current_rule_version,
                has_upstream_validation_issue=batch_callbacks.has_upstream_validation_issue,
                detect_conflicts=batch_callbacks.detect_conflicts,
                logger=batch_callbacks.logger,
                uuid_factory=lambda: "run-123",
                now=fixed_now,
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == message


def test_validate_rules_batch_logs_run_persistence_failure_without_raising(
    batch_repository,
    data_catalog_repository,
    config_repository,
    run_repository,
    batch_callbacks,
    fixed_now,
) -> None:
    run_repository.raise_error = True

    payload = _run(
        validate_rules_batch(
            ValidateRulesBatchCommand(rule_ids=["rule-1"]),
            batch_repository,
            data_catalog_repository,
            config_repository,
            run_repository,
            apply_validation_policies=batch_callbacks.apply_validation_policies,
            compile_rule_to_intermediate_model=batch_callbacks.compile_rule_to_intermediate_model,
            infer_alias_expectations=batch_callbacks.infer_alias_expectations,
            persist_compiler_artifact=batch_callbacks.persist_compiler_artifact,
            resolve_current_rule_version=batch_callbacks.resolve_current_rule_version,
            has_upstream_validation_issue=batch_callbacks.has_upstream_validation_issue,
            detect_conflicts=lambda items: [],
            logger=batch_callbacks.logger,
            uuid_factory=lambda: "run-456",
            now=fixed_now,
        )
    )

    assert payload["runId"] == "run-456"
    assert batch_callbacks.logger.warnings == ["Failed to persist validation run 'run-456': store unavailable"]