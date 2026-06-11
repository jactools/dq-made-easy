from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.application.use_cases.testing_generated_data import generate_test_data_for_version
from app.application.use_cases.testing_generated_data import GenerateTestDataForVersionCommand
from app.application.use_cases.testing_generated_data import generate_test_data_for_data_asset
from app.application.use_cases.testing_generated_data import GenerateTestDataForDataAssetCommand
from app.application.use_cases.testing_generated_data import GeneratedDataRuleTestCommand
from app.application.use_cases.testing_generated_data import GeneratedDataRuleTestServices
from app.application.use_cases.testing_generated_data import GeneratedDataAssetServices
from app.application.use_cases.testing_generated_data import GeneratedTestDataServices
from app.application.use_cases.testing_generated_data import start_generated_data_rule_test
from app.application.use_cases.testing_generated_data import StartGeneratedDataRuleTestServices
from app.application.use_cases.testing_generated_data import StartGeneratedDataRuleTestCommand
from app.application.use_cases.testing_generated_data import execute_rule_with_generated_data


@pytest.fixture
def compiled_execution_context() -> dict[str, object]:
    return {
        "compiledExpression": "email contains '@'",
        "ruleVersionId": "rv-1",
    }


@pytest.mark.anyio
async def test_generate_test_data_for_version_returns_completed_result() -> None:
    captured: dict[str, object] = {}

    async def _enqueue(request_payload: dict[str, object]):
        captured["request_payload"] = request_payload
        return {"request_id": "req-1"}

    async def _wait(request_id: str):
        captured["request_id"] = request_id
        return {
            "result": {
                "version_id": "dov-1",
                "sample_count": 2,
                "samples": [{"email": "user1@example.com"}, {"email": "user2@example.com"}],
            }
        }

    result = await generate_test_data_for_version(
        command=GenerateTestDataForVersionCommand(version_id="dov-1", sample_count=2),
        services=GeneratedTestDataServices(
            resolve_version_generation_payload=lambda version_id, sample_count: {
                "target_id": version_id,
                "sample_count": sample_count,
            },
            enqueue_queued_test_data_request=_enqueue,
            wait_for_test_data_request_result=_wait,
        ),
    )

    assert captured["request_payload"] == {"target_id": "dov-1", "sample_count": 2}
    assert captured["request_id"] == "req-1"
    assert result["version_id"] == "dov-1"
    assert len(result["samples"]) == 2


@pytest.mark.anyio
async def test_generate_test_data_for_data_asset_returns_completed_result() -> None:
    captured: dict[str, object] = {}

    async def _enqueue(request_payload: dict[str, object]):
        captured["request_payload"] = request_payload
        return {"request_id": "req-asset-1"}

    async def _wait(request_id: str):
        captured["request_id"] = request_id
        return {
            "result": {
                "version_id": "asset-1-v1",
                "sample_count": 4,
                "samples": [{"email": "asset-user1@example.com"}],
            }
        }

    result = await generate_test_data_for_data_asset(
        command=GenerateTestDataForDataAssetCommand(asset_id="asset-1", sample_count=4),
        services=GeneratedDataAssetServices(
            resolve_data_asset_generation_payload=lambda asset_id, sample_count: {
                "target_type": "data_asset",
                "target_id": asset_id,
                "sample_count": sample_count,
                "version_id": "asset-1-v1",
                "data_object_id": "asset-1",
                "data_object_name": "Customer health",
                "attributes": [{"name": "customer_id", "type": "string", "nullable": False}],
            },
            enqueue_queued_test_data_request=_enqueue,
            wait_for_test_data_request_result=_wait,
        ),
    )

    assert captured["request_payload"]["target_type"] == "data_asset"
    assert captured["request_payload"]["target_id"] == "asset-1"
    assert captured["request_id"] == "req-asset-1"
    assert result["version_id"] == "asset-1-v1"
    assert len(result["samples"]) == 1


@pytest.mark.anyio
async def test_start_generated_data_rule_test_persists_pending_proof(compiled_execution_context: dict[str, object]) -> None:
    captured: dict[str, object] = {}

    async def _build_execution_context(rule_id: str):
        captured["rule_id"] = rule_id
        return compiled_execution_context

    def _persist_generated_data_proof(**kwargs):
        captured["proof"] = kwargs
        return SimpleNamespace(id="proof-1", status=kwargs["status"])

    proof = await start_generated_data_rule_test(
        command=StartGeneratedDataRuleTestCommand(
            rule_id="rule-1",
            version_id="dov-1",
            sample_count=3,
            correlation_id="corr-1",
            requested_by_user_id="user-1",
            semantic_matching={"enabled": True},
        ),
        services=StartGeneratedDataRuleTestServices(
            build_execution_context=_build_execution_context,
            persist_generated_data_proof=_persist_generated_data_proof,
        ),
    )

    assert captured["rule_id"] == "rule-1"
    assert captured["proof"]["status"] == "pending"
    assert captured["proof"]["version_id"] == "dov-1"
    assert proof.id == "proof-1"


@pytest.mark.anyio
async def test_test_rule_with_generated_data_uses_generated_samples_and_updates_proof(
    compiled_execution_context: dict[str, object],
) -> None:
    captured: dict[str, object] = {}

    async def _build_execution_context(rule_id: str):
        captured["rule_id"] = rule_id
        return compiled_execution_context

    async def _enqueue(request_payload: dict[str, object]):
        captured["request_payload"] = request_payload
        return {"request_id": "req-1", "correlation_id": "corr-1"}

    async def _wait(request_id: str):
        captured["wait_request_id"] = request_id
        return {"result": {"samples": [{"email": "user@example.com"}]}}

    def _persist_generated_data_proof(**kwargs):
        captured.setdefault("persisted_statuses", []).append(kwargs["status"])
        return SimpleNamespace(id=kwargs.get("proof_id") or "proof-1", status=kwargs["status"])

    def _update_generated_data_proof(**kwargs):
        captured["updated_proof"] = kwargs
        return SimpleNamespace(id=kwargs["proof_id"], status=kwargs["final_status"])

    def _run_rule_against_test_data(rule_id, test_data, version_id_source=None, compiled_expression=None, semantic_config=None):
        captured["run_call"] = {
            "rule_id": rule_id,
            "test_data": list(test_data),
            "version_id_source": version_id_source,
            "compiled_expression": compiled_expression,
            "semantic_config": semantic_config,
        }
        return SimpleNamespace(
            totalTests=1,
            model_dump=lambda: {
                "ruleId": rule_id,
                "rulePassed": True,
                "totalTests": 1,
                "passedCount": 1,
                "failedCount": 0,
            },
        )

    def _merge_execution_context(response_payload, execution_context, compiled_expression: str):
        del response_payload, execution_context
        return {
            "executedExpressionSource": "compiled-artifact",
            "compiledExpression": compiled_expression,
        }

    def _serialize_proof(proof: object) -> dict[str, object]:
        return {"id": getattr(proof, "id"), "status": getattr(proof, "status")}

    async def _resolve_current_rule_status(rule_id: str):
        captured["status_rule_id"] = rule_id
        return "validated"

    async def _record_rule_tested_transition(rule_id: str, current_status: str, actor_id: str | None):
        captured["transition"] = (rule_id, current_status, actor_id)

    result = await execute_rule_with_generated_data(
        command=GeneratedDataRuleTestCommand(
            rule_id="rule-1",
            version_id="dov-1",
            sample_count=1,
            requested_by_user_id="user-1",
            semantic_matching={"enabled": True},
        ),
        services=GeneratedDataRuleTestServices(
            build_execution_context=_build_execution_context,
            serialize_execution_context=lambda context: dict(context),
            resolve_version_generation_payload=lambda version_id, sample_count: {
                "version_id": version_id,
                "sample_count": sample_count,
                "data_object_id": "do-1",
                "data_object_name": "Orders",
                "version_name": 1,
            },
            enqueue_queued_test_data_request=_enqueue,
            wait_for_test_data_request_result=_wait,
            persist_generated_data_proof=_persist_generated_data_proof,
            update_generated_data_proof=_update_generated_data_proof,
            run_rule_against_test_data=_run_rule_against_test_data,
            merge_execution_context=_merge_execution_context,
            serialize_proof=_serialize_proof,
            resolve_current_rule_status=_resolve_current_rule_status,
            record_rule_tested_transition=_record_rule_tested_transition,
        ),
    )

    assert captured["persisted_statuses"] == ["running"]
    assert captured["wait_request_id"] == "req-1"
    assert captured["run_call"]["compiled_expression"] == "email contains '@'"
    assert captured["run_call"]["semantic_config"] == {"enabled": True}
    assert captured["transition"] == ("rule-1", "validated", "user-1")
    assert result.response_payload["storedProof"]["status"] == "passed"
    assert result.response_payload["executionContext"]["executedExpressionSource"] == "compiled-artifact"