from __future__ import annotations

from app.api.presenters.exception_reports import (
    build_exception_summary_csv_export,
    build_exception_summary_json_export,
    build_exception_summary_markdown_report,
)


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


def test_json_export_roundtrips_classification() -> None:
    summary = {
        "delivery_id": "del-1",
        "object_storage_classification": "synthetic_test",
        "evidence_classification": "synthetic_result",
        "analytics": {"total_failed_records": 5, "top_reasons": []},
    }
    exported = build_exception_summary_json_export(summary)
    assert "synthetic_test" in exported
    assert "synthetic_result" in exported


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def test_csv_export_includes_classification_columns() -> None:
    summary = {
        "analytics": {
            "total_failed_records": 10,
            "runs_with_failures": 2,
            "top_reasons": [
                {"reason_code": "RC-001", "reason_text": "Null value", "total": 7},
            ],
        },
    }
    exported = build_exception_summary_csv_export(
        scope_kind="delivery",
        scope_id="del-1",
        serialized_summary=summary,
        object_storage_classification="real_evidence",
        evidence_classification="real_evidence",
    )
    lines = exported.strip().split("\n")
    headers = lines[0]
    assert "object_storage_classification" in headers
    assert "evidence_classification" in headers
    assert "real_evidence" in lines[1]


def test_csv_export_uses_fluctuation_data_with_classification() -> None:
    summary = {
        "analytics": {
            "total_failed_records": 20,
            "runs_with_failures": 3,
            "reason_fluctuations": [
                {
                    "reason_code": "RC-002",
                    "reason_text": "Duplicate",
                    "first_total": 5,
                    "latest_total": 10,
                    "net_change": 5,
                    "direction": "up",
                    "peak_total": 12,
                    "bucket_count": 2,
                },
            ],
        },
    }
    exported = build_exception_summary_csv_export(
        scope_kind="delivery",
        scope_id="del-2",
        serialized_summary=summary,
        object_storage_classification="synthetic_test",
        evidence_classification="synthetic_result",
    )
    lines = exported.strip().split("\n")
    assert len(lines) >= 2
    assert "synthetic_test" in lines[1]
    assert "synthetic_result" in lines[1]


def test_csv_export_empty_classification() -> None:
    summary = {
        "analytics": {
            "total_failed_records": 0,
            "runs_with_failures": 0,
            "top_reasons": [],
        },
    }
    exported = build_exception_summary_csv_export(
        scope_kind="delivery",
        scope_id="del-3",
        serialized_summary=summary,
        object_storage_classification="",
        evidence_classification="",
    )
    lines = exported.strip().split("\n")
    headers = lines[0]
    assert "object_storage_classification" in headers
    assert "evidence_classification" in headers


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def test_markdown_export_includes_classification() -> None:
    summary = {
        "analytics": {
            "total_failed_records": 15,
            "runs_with_failures": 2,
            "top_reasons": [
                {"reason_code": "RC-003", "reason_text": "Out of range", "total": 15},
            ],
            "reason_fluctuations": [],
        },
        "execution_run_ids": ["run-1", "run-2"],
        "data_object_version_ids": ["ver-1"],
    }
    exported = build_exception_summary_markdown_report(
        scope_kind="delivery",
        scope_id="del-4",
        serialized_summary=summary,
        object_storage_classification="real_evidence",
        evidence_classification="real_evidence",
    )
    assert "Object storage classification: real_evidence" in exported
    assert "Evidence classification: real_evidence" in exported


def test_markdown_export_empty_classification_shows_warning() -> None:
    summary = {
        "analytics": {
            "total_failed_records": 0,
            "runs_with_failures": 0,
            "top_reasons": [],
            "reason_fluctuations": [],
        },
        "execution_run_ids": [],
        "data_object_version_ids": [],
    }
    exported = build_exception_summary_markdown_report(
        scope_kind="delivery",
        scope_id="del-5",
        serialized_summary=summary,
        object_storage_classification="",
        evidence_classification="",
    )
    assert "WARNING" in exported
    assert "unclassified" in exported.lower()


def test_markdown_export_mixed_classification() -> None:
    summary = {
        "analytics": {
            "total_failed_records": 1,
            "runs_with_failures": 1,
            "top_reasons": [],
            "reason_fluctuations": [],
        },
        "execution_run_ids": ["run-x"],
        "data_object_version_ids": ["ver-x"],
    }
    exported = build_exception_summary_markdown_report(
        scope_kind="delivery",
        scope_id="del-6",
        serialized_summary=summary,
        object_storage_classification="synthetic_test",
        evidence_classification="synthetic_result",
    )
    assert "Object storage classification: synthetic_test" in exported
    assert "Evidence classification: synthetic_result" in exported
    assert "WARNING" not in exported
