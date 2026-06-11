from __future__ import annotations

from types import SimpleNamespace

import pytest

from fastapi import HTTPException

from app.application.use_cases.testing_reports import export_test_proof_report
from app.application.use_cases.testing_reports import ExportTestProofReportCommand
from app.application.use_cases.testing_reports import list_test_proofs
from app.application.use_cases.testing_reports import ListTestProofsCommand
from app.application.use_cases.testing_reports import TestProofReportServices as ReportServices


def test_list_test_proofs_resolves_views() -> None:
    result = list_test_proofs(
        command=ListTestProofsCommand(rule_id="rule-1"),
        list_test_proofs=lambda rule_id: [{"id": "p1", "ruleId": rule_id}],
        resolve_test_proof_views=lambda proofs: [SimpleNamespace(id=item["id"], ruleId=item["ruleId"], status="passed") for item in proofs],
    )

    assert result[0].id == "p1"
    assert result[0].ruleId == "rule-1"


@pytest.mark.anyio
async def test_export_test_proof_report_returns_pdf_result() -> None:
    proofs = [
        SimpleNamespace(id="p2", executionTrace=SimpleNamespace(ruleVersionId="rv-2")),
        SimpleNamespace(id="p1", executionTrace=SimpleNamespace(ruleVersionId="rv-1")),
    ]

    result = await export_test_proof_report(
        command=ExportTestProofReportCommand(rule_id="rule-1", output_format="pdf"),
        services=ReportServices(
            list_test_proofs=lambda _rule_id: proofs,
            resolve_test_proof_views=lambda rows: rows,
            compare_rule_versions=lambda *_args: _async_return({"changes": {"details": []}}),
            get_rule_by_id=lambda _rule_id: _async_return(SimpleNamespace(name="Rule One", dimension="validity")),
            get_rule_version=lambda _rule_id, _version_id: _async_return({"expression": "email contains '@'"}),
            render_version_diff_section=lambda *_args: "diff",
            build_markdown_report=lambda **_kwargs: "report",
            render_pdf=lambda markdown: f"PDF:{markdown}".encode("utf-8"),
        ),
    )

    assert result.media_type == "application/pdf"
    assert result.filename == "test-report-rule-1-p2.pdf"
    assert result.body == b"PDF:report"


@pytest.mark.anyio
async def test_export_test_proof_report_raises_for_missing_proof() -> None:
    with pytest.raises(HTTPException) as error:
        await export_test_proof_report(
            command=ExportTestProofReportCommand(rule_id="rule-1", proof_id="missing"),
            services=ReportServices(
                list_test_proofs=lambda _rule_id: [SimpleNamespace(id="p1", executionTrace=None)],
                resolve_test_proof_views=lambda rows: rows,
                compare_rule_versions=lambda *_args: _async_return(None),
                get_rule_by_id=lambda _rule_id: _async_return(None),
                get_rule_version=lambda _rule_id, _version_id: _async_return({}),
                render_version_diff_section=lambda *_args: "diff",
                build_markdown_report=lambda **_kwargs: "report",
                render_pdf=lambda markdown: markdown.encode("utf-8"),
            ),
        )
    assert error.value.status_code == 404


async def _async_return(value):
    return value