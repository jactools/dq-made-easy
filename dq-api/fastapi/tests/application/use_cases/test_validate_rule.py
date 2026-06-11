import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.use_cases.validate_rule import validate_rule
from app.application.use_cases.validate_rule import ValidateRuleCommand


pytestmark = pytest.mark.usefixtures("clone_payload")


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def validation_repository():
    class _Repository:
        def __init__(self) -> None:
            self.validation_updates: list[dict] = []

        async def get_rule_by_id(self, rule_id: str):
            if rule_id != "rule-1":
                return None
            return SimpleNamespace(name="Email rule", expression="email IS NOT NULL", workspace="default")

        async def set_current_rule_version_validation(self, **kwargs):
            self.validation_updates.append(kwargs)
            return {"ok": True}

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
            return SimpleNamespace(
                validationPolicies=[
                    SimpleNamespace(model_dump=lambda: {"checkId": "DQ7_AST_PARSE", "enabled": True})
                ]
            )

    return _ConfigRepository()


@pytest.fixture
def validation_callbacks():
    calls: dict[str, object] = {}

    def apply_validation_policies(raw_diagnostics, raw_policies, workspace):
        calls["apply"] = {
            "raw_diagnostics": raw_diagnostics,
            "raw_policies": raw_policies,
            "workspace": workspace,
        }
        return list(raw_diagnostics)

    def compile_rule_to_intermediate_model(**kwargs):
        calls["compile"] = kwargs
        return {
            "artifactKey": "artifact-1",
            "compilerVersion": "dq-7.3.0",
            "target": "dsl",
            "compilable": True,
            "filter": {"normalized": "email IS NOT NULL"},
            "diagnostics": [
                {
                    "code": "DQ7_AST_PARSE",
                    "severity": "warning",
                    "message": "warning",
                }
            ],
        }

    def infer_alias_expectations(expression: str):
        calls["infer"] = expression
        return [{"alias": "email", "expected": "attr-email"}]

    async def persist_compiler_artifact(repository, **kwargs):
        del repository
        calls["persist"] = kwargs
        return {"ok": True}

    async def resolve_current_rule_version(repository, rule_id: str):
        del repository
        calls["resolve"] = rule_id
        return SimpleNamespace(id="rv-1", versionNumber=3)

    def has_upstream_validation_issue(diagnostics):
        calls["upstream"] = diagnostics
        return False

    return SimpleNamespace(
        calls=calls,
        apply_validation_policies=apply_validation_policies,
        compile_rule_to_intermediate_model=compile_rule_to_intermediate_model,
        infer_alias_expectations=infer_alias_expectations,
        persist_compiler_artifact=persist_compiler_artifact,
        resolve_current_rule_version=resolve_current_rule_version,
        has_upstream_validation_issue=has_upstream_validation_issue,
    )


def test_validate_rule_returns_payload_and_persists_validation_state(
    validation_repository,
    data_catalog_repository,
    config_repository,
    validation_callbacks,
) -> None:
    payload = _run(
        validate_rule(
            ValidateRuleCommand(rule_id="rule-1", validated_by="user-1"),
            validation_repository,
            data_catalog_repository,
            config_repository,
            apply_validation_policies=validation_callbacks.apply_validation_policies,
            compile_rule_to_intermediate_model=validation_callbacks.compile_rule_to_intermediate_model,
            infer_alias_expectations=validation_callbacks.infer_alias_expectations,
            persist_compiler_artifact=validation_callbacks.persist_compiler_artifact,
            resolve_current_rule_version=validation_callbacks.resolve_current_rule_version,
            has_upstream_validation_issue=validation_callbacks.has_upstream_validation_issue,
        )
    )

    assert payload["valid"] is True
    assert payload["compiledExpression"] == "email IS NOT NULL"
    assert payload["summary"] == {"errors": 0, "warnings": 1}
    assert payload["inferredAliases"] == [{"alias": "email", "expected": "attr-email"}]
    assert validation_callbacks.calls["apply"] == {
        "raw_diagnostics": [
            {
                "scope": "rule",
                "severity": "warning",
                "message": "warning",
                "code": "DQ7_AST_PARSE",
            }
        ],
        "raw_policies": [{"checkId": "DQ7_AST_PARSE", "enabled": True}],
        "workspace": "default",
    }
    assert validation_callbacks.calls["persist"] == {
        "rule_id": "rule-1",
        "filter_expression": "email IS NOT NULL",
        "intermediate_model": {
            "artifactKey": "artifact-1",
            "compilerVersion": "dq-7.3.0",
            "target": "dsl",
            "compilable": True,
            "filter": {"normalized": "email IS NOT NULL"},
            "diagnostics": [
                {
                    "code": "DQ7_AST_PARSE",
                    "severity": "warning",
                    "message": "warning",
                }
            ],
        },
    }
    assert validation_repository.validation_updates == [
        {
            "rule_id": "rule-1",
            "validation_status": "valid",
            "validated_by": "user-1",
        }
    ]


def test_validate_rule_raises_not_found_for_missing_rule(
    validation_repository,
    data_catalog_repository,
    config_repository,
    validation_callbacks,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _run(
            validate_rule(
                ValidateRuleCommand(rule_id="missing-rule"),
                validation_repository,
                data_catalog_repository,
                config_repository,
                apply_validation_policies=validation_callbacks.apply_validation_policies,
                compile_rule_to_intermediate_model=validation_callbacks.compile_rule_to_intermediate_model,
                infer_alias_expectations=validation_callbacks.infer_alias_expectations,
                persist_compiler_artifact=validation_callbacks.persist_compiler_artifact,
                resolve_current_rule_version=validation_callbacks.resolve_current_rule_version,
                has_upstream_validation_issue=validation_callbacks.has_upstream_validation_issue,
            )
        )

    assert exc_info.value.status_code == 404
    assert "missing-rule" in str(exc_info.value.detail)


def test_validate_rule_rejects_rules_without_resolvable_attributes(
    validation_repository,
    config_repository,
    validation_callbacks,
) -> None:
    class _EmptyCatalogRepository:
        def list_rule_attributes(self):
            return [SimpleNamespace(ruleId="rule-1", attributeId="attr-missing")]

        def list_attributes_catalog(self, version_id: str | None = None):
            del version_id
            return []

    with pytest.raises(HTTPException) as exc_info:
        _run(
            validate_rule(
                ValidateRuleCommand(rule_id="rule-1"),
                validation_repository,
                _EmptyCatalogRepository(),
                config_repository,
                apply_validation_policies=validation_callbacks.apply_validation_policies,
                compile_rule_to_intermediate_model=validation_callbacks.compile_rule_to_intermediate_model,
                infer_alias_expectations=validation_callbacks.infer_alias_expectations,
                persist_compiler_artifact=validation_callbacks.persist_compiler_artifact,
                resolve_current_rule_version=validation_callbacks.resolve_current_rule_version,
                has_upstream_validation_issue=validation_callbacks.has_upstream_validation_issue,
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "unresolved_rule_attributes"
    assert exc_info.value.detail["assigned_attribute_ids"] == ["attr-missing"]