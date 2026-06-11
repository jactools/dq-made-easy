from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1 import testing_api as testing_api


def test_persist_generated_data_test_proof_handles_create_update_and_missing() -> None:
    class CreateRepo:
        def create_test_proof(self, rule_id, proof_payload, status):
            assert rule_id == "rule-1"
            assert status == "passed"
            proof_payload["id"] = "proof-1"
            return proof_payload

    proof = testing_api._persist_generated_data_test_proof(
        repository=CreateRepo(),
        rule_id="rule-1",
        proof_id=None,
        status="passed",
        execution_context={"ruleVersionId": "rv-1"},
        message="ok",
    )
    assert proof.status == "passed"
    assert proof.proofData["executionContext"]["ruleVersionId"] == "rv-1"

    class UpdateRepo:
        def update_test_proof(self, proof_id, proof_payload, status):
            assert proof_id == "proof-2"
            assert status == "failed"
            proof_payload["id"] = proof_id
            return proof_payload

    updated = testing_api._persist_generated_data_test_proof(
        repository=UpdateRepo(),
        rule_id="rule-1",
        proof_id="proof-2",
        status="failed",
        execution_context={"ruleVersionId": "rv-2"},
        message="fail",
    )
    assert updated.status == "failed"

    class MissingRepo:
        def update_test_proof(self, proof_id, proof_payload, status):
            del proof_id, proof_payload, status
            raise KeyError("missing")

    with pytest.raises(HTTPException) as error:
        testing_api._persist_generated_data_test_proof(
            repository=MissingRepo(),
            rule_id="rule-1",
            proof_id="proof-x",
            status="failed",
            execution_context={"ruleVersionId": "rv-2"},
            message="fail",
        )
    assert error.value.status_code == 404
