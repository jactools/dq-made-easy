from types import SimpleNamespace

from app.api.v1.endpoints import testing as testing_mod
from app.domain.entities import testing_endpoint_support as testing_support


def test_extract_selected_attributes():
    data = {
        "selectedAttributes": [
            {"name": "a"},
            {"id": "b"},
            "c",
            None,
            {"name": ""},
        ]
    }
    out = testing_support.extract_test_selected_attributes(data)
    assert out == ["a", "b", "c"]

    assert testing_support.extract_test_selected_attributes({}) == []


def test_build_failure_analysis_from_reasons_and_diagnostics():
    proof = {
        "failureReasons": ["reason1", "reason2", "reason1"],
        "diagnostics": [{"message": "diag1"}, {"message": ""}],
        "results": [],
    }
    out = testing_support.build_test_failure_analysis(proof, failures_found=2)
    # unique reasons preserved, diagnostics appended, length limited to 3
    assert "reason1" in out[0]
    assert len(out) <= 3


def test_build_failure_analysis_from_failed_rows():
    proof = {
        "results": [
            {"passed": False, "data": {"a": None, "b": ""}},
            {"passed": False, "data": {"a": None, "b": "x"}},
        ],
    }
    out = testing_support.build_test_failure_analysis(proof, failures_found=2)
    # Should include Likely cause and Example failing row fields
    joined = " ".join(out)
    assert "Likely cause" in joined or "Example failing row fields" in joined


def test_build_scheduler_handoff_payload_defaults_and_override():
    payload = testing_mod._build_scheduler_handoff_payload("req-1", None, "corr-1")
    assert payload["batchRequestId"] == "req-1"
    assert payload["executorTarget"] == "dq-engine"
    assert payload["handoffStatus"] == "accepted"

    exec_ctx = {"executionContract": {"engineTarget": "spark"}, "handoffReady": True}
    payload = testing_mod._build_scheduler_handoff_payload("req-2", exec_ctx, "corr-2")
    assert payload["executorTarget"] == "spark"
    assert payload["handoffReady"] is True


def test_render_version_diff_section_variants():
    latest = {"executionTrace": {"ruleVersionNumber": 2}}
    prev = {"executionTrace": {"ruleVersionNumber": 2}}
    # same versions
    out = testing_support.render_test_proof_version_diff_section(None, latest, prev)
    assert "No rule version change detected" in out

    prev = {"executionTrace": {"ruleVersionNumber": 1}}
    # no diff payload
    out = testing_support.render_test_proof_version_diff_section(None, latest, prev)
    assert "Version changed from" in out

    diff_payload = {"changes": {"details": [{"field": "f1", "oldValue": 1, "newValue": 2}]}}
    out = testing_support.render_test_proof_version_diff_section(diff_payload, latest, prev)
    assert "Detected differences" in out and "f1" in out
