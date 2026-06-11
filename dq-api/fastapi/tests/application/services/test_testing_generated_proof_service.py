from __future__ import annotations

from app.application.resolvers import resolve_test_proofs_view
from app.application.services import testing_generated_proof_service


def test_resolve_failure_message_variants() -> None:
    assert testing_generated_proof_service.resolve_failure_message("boom") == "boom"
    assert testing_generated_proof_service.resolve_failure_message({"message": "boom"}) == "boom"
    assert testing_generated_proof_service.resolve_failure_message({"error": "boom"}) == "boom"
    assert testing_generated_proof_service.resolve_failure_message(object()) == "Queued test data generation failed"


def test_serialize_test_proof_uses_view_resolver() -> None:
    payload = {
        "id": "proof-1",
        "status": "passed",
        "coverage": 0.5,
        "recordsTestedCount": 1,
        "failuresFound": 0,
        "proofData": {"executionContext": {}, "executionTrace": {}},
        "executionTrace": {},
    }

    serialized = testing_generated_proof_service.serialize_test_proof(payload, resolve_test_proofs_view)
    assert serialized["id"] == "proof-1"
    assert serialized["status"] == "passed"
