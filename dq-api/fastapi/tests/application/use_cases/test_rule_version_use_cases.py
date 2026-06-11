import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.use_cases.rule_version_mutations import mark_rule_version_for_rollback
from app.application.use_cases.rule_version_mutations import MarkRuleVersionForRollbackCommand
from app.application.use_cases.rule_version_mutations import rollback_rule
from app.application.use_cases.rule_version_mutations import RollbackRuleCommand
from app.application.use_cases.rule_version_mutations import save_rule_as_template
from app.application.use_cases.rule_version_mutations import SaveRuleTemplateCommand
from app.application.use_cases.rule_version_mutations import update_rule_version_tags
from app.application.use_cases.rule_version_mutations import UpdateRuleVersionTagsCommand
from app.application.use_cases.rule_version_queries import get_rule_version_active_compiler_artifact
from app.application.use_cases.rule_version_queries import list_rule_compiler_versions
from app.application.use_cases.rule_version_queries import list_rule_version_compiler_artifacts
from app.application.use_cases.rule_version_queries import RuleCompilerVersionsQuery
from app.application.use_cases.rule_version_queries import RuleVersionLookup
from app.application.use_cases.validate_rule_enriched import validate_rule_enriched
from app.application.use_cases.validate_rule_enriched import ValidateRuleEnrichedCommand
from app.domain.entities import build_rule_record_entity


pytestmark = pytest.mark.usefixtures("clone_payload")


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def version_repository():
    class _Repository:
        def __init__(self) -> None:
            self.template_payload = {"id": "tpl-1", "is_template": True}
            self.rollback_payload = {"id": "rule-1", "rolled_back": True}
            self.update_tags_payload = {"ok": True}
            self.mark_payload = {"ok": True}

        async def list_rule_records(self, **kwargs):
            del kwargs
            return [build_rule_record_entity({"id": "rule-1", "name": "Email Rule", "expression": "TRUE", "dimension": "validity"})]

        async def get_active_compiler_artifact(self, version_id: str):
            if version_id == "missing-version":
                return None
            return {
                "id": "artifact-1",
                "isActive": True,
                "createdAt": "2026-04-24T12:00:00Z",
                "artifactKey": "artifact-key",
                "compilerVersion": "dq-7.3.0",
                "compilerRevision": 4,
                "compileStatus": "success",
                "artifactPayload": {
                    "schemaVersion": "1.1.0",
                    "filter": {"normalized": "email IS NOT NULL", "source": "email IS NOT NULL"},
                },
            }

        async def get_rule_version(self, rule_id: str, version_id: str):
            del rule_id
            if version_id == "missing-version":
                return None
            return {"id": version_id, "versionNumber": 4, "isCurrentVersion": True}

        async def list_compiler_artifacts(self, version_id: str):
            return [{"id": f"history-{version_id}", "is_active": False}]

        async def save_rule_as_template(self, **kwargs):
            return self.template_payload

        async def execute_rule_rollback(self, **kwargs):
            return self.rollback_payload

        async def update_rule_version_tags(self, **kwargs):
            return self.update_tags_payload

        async def mark_rule_version_for_rollback(self, **kwargs):
            return self.mark_payload

        async def get_rule_by_id(self, rule_id: str):
            if rule_id == "missing-rule":
                return None
            return SimpleNamespace(id=rule_id)

    return _Repository()


@pytest.fixture
def version_resolver():
    async def _resolve(repository, rule_id: str):
        del repository
        return SimpleNamespace(id=f"rv-{rule_id}", versionNumber=4)

    return _resolve


def test_list_rule_compiler_versions_maps_active_artifact_fields(version_repository, version_resolver) -> None:
    payload = _run(
        list_rule_compiler_versions(
            RuleCompilerVersionsQuery(page=1, limit=20, workspace="default"),
            version_repository,
            resolve_current_rule_version=version_resolver,
        )
    )

    assert payload == {
        "data": [
            {
                "ruleId": "rule-1",
                "ruleName": "Email Rule",
                "ruleVersionId": "rv-rule-1",
                "ruleVersionNumber": 4,
                "compilerVersion": "dq-7.3.0",
                "compilerRevision": 4,
                "compileStatus": "success",
                "artifactKey": "artifact-key",
                "compiledAt": "2026-04-24T12:00:00Z",
                "compiledExpression": "email IS NOT NULL",
            }
        ],
        "pagination": {
            "total": 1,
            "page": 1,
            "limit": 20,
            "total_pages": 1,
            "has_next": False,
            "has_previous": False,
        },
    }


def test_rule_version_artifact_queries_map_payloads_and_404(version_repository) -> None:
    history = _run(
        list_rule_version_compiler_artifacts(
            RuleVersionLookup(rule_id="rule-1", version_id="rv-1"),
            version_repository,
        )
    )
    active = _run(
        get_rule_version_active_compiler_artifact(
            RuleVersionLookup(rule_id="rule-1", version_id="rv-1"),
            version_repository,
        )
    )

    assert history == {
        "ruleId": "rule-1",
        "ruleVersionId": "rv-1",
        "ruleVersionNumber": 4,
        "activeArtifactId": "artifact-1",
        "items": [{"id": "history-rv-1", "is_active": False}],
    }
    assert active["id"] == "artifact-1"
    assert active["artifactKey"] == "artifact-key"

    with pytest.raises(HTTPException) as exc_info:
        _run(
            list_rule_version_compiler_artifacts(
                RuleVersionLookup(rule_id="rule-1", version_id="missing-version"),
                version_repository,
            )
        )

    assert exc_info.value.status_code == 404


def test_rule_version_mutations_map_success_and_errors(version_repository) -> None:
    template_payload = _run(
        save_rule_as_template(
            SaveRuleTemplateCommand(
                rule_id="rule-1",
                template_name="Template",
                template_description="desc",
                created_by="user-1",
            ),
            version_repository,
        )
    )
    rollback_payload = _run(
        rollback_rule(
            RollbackRuleCommand(
                rule_id="rule-1",
                to_version_id=" rv-1 ",
                reason=" because ",
                requested_by_user_id="user-1",
            ),
            version_repository,
        )
    )
    tags_payload = _run(
        update_rule_version_tags(
            UpdateRuleVersionTagsCommand(
                rule_id="rule-1",
                version_id="rv-1",
                tags=["critical"],
                updated_by_user_id="user-1",
            ),
            version_repository,
        )
    )
    mark_payload = _run(
        mark_rule_version_for_rollback(
            MarkRuleVersionForRollbackCommand(rule_id="rule-1", version_id="rv-1", marked=True),
            version_repository,
        )
    )

    assert template_payload == {"id": "tpl-1", "is_template": True}
    assert rollback_payload == {"id": "rule-1", "rolled_back": True}
    assert tags_payload == {"ok": True}
    assert mark_payload == {"ok": True}

    with pytest.raises(HTTPException) as exc_info:
        _run(
            rollback_rule(
                RollbackRuleCommand(
                    rule_id="rule-1",
                    to_version_id=" ",
                    reason=" ",
                    requested_by_user_id="user-1",
                ),
                version_repository,
            )
        )

    assert exc_info.value.status_code == 400


def test_validate_rule_enriched_maps_resolution_sources_and_missing_rule(version_repository) -> None:
    payload = _run(
        validate_rule_enriched(
            ValidateRuleEnrichedCommand(
                rule_id="rule-1",
                rule_version_id="rv-1",
                expression="email IS NOT NULL",
                detected_aliases=["email", "country", "status"],
                unresolved_aliases=["country"],
                issues=["country unresolved"],
                manual_alias_mappings={"email": "attr-email"},
            ),
            version_repository,
        )
    )

    assert payload["ruleId"] == "rule-1"
    assert payload["ruleVersionId"] == "rv-1"
    assert payload["isValid"] is False
    assert payload["diagnostics"]["email"]["source"] == "manual"
    assert payload["diagnostics"]["country"]["source"] == "unresolved"
    assert payload["diagnostics"]["status"]["source"] == "catalog"
    assert payload["stats"] == {
        "catalogSourcedAliases": 1,
        "manualSourcedAliases": 1,
        "unresolvedCount": 1,
    }

    with pytest.raises(HTTPException) as exc_info:
        _run(
            validate_rule_enriched(
                ValidateRuleEnrichedCommand(
                    rule_id="missing-rule",
                    rule_version_id="rv-missing",
                    expression="x",
                ),
                version_repository,
            )
        )

    assert exc_info.value.status_code == 404