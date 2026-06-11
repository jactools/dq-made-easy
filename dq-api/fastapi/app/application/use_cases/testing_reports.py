from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


def _normalize_optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


@dataclass(slots=True)
class ListTestProofsCommand:
    rule_id: str


@dataclass(slots=True)
class ExportTestProofReportCommand:
    rule_id: str
    output_format: str = "markdown"
    proof_id: str | None = None


@dataclass(slots=True)
class TestProofReportResult:
    body: str | bytes
    media_type: str
    filename: str


@dataclass(slots=True)
class TestProofReportServices:
    list_test_proofs: ListTestProofs
    resolve_test_proof_views: ResolveTestProofViews
    compare_rule_versions: CompareRuleVersions
    get_rule_by_id: GetRuleById
    get_rule_version: GetRuleVersion
    render_version_diff_section: RenderVersionDiffSection
    build_markdown_report: BuildMarkdownReport
    render_pdf: RenderPdf


ListTestProofs = Callable[[str], list[Any]]
ResolveTestProofViews = Callable[[list[Any]], list[Any]]
CompareRuleVersions = Callable[[str, str, str], Awaitable[Any]]
GetRuleById = Callable[[str], Awaitable[Any]]
GetRuleVersion = Callable[[str, str], Awaitable[Any]]
RenderVersionDiffSection = Callable[[Mapping[str, Any] | None, Any, Any | None], str]
BuildMarkdownReport = Callable[..., str]
RenderPdf = Callable[[str], bytes]


def list_test_proofs(
    command: ListTestProofsCommand,
    list_test_proofs: ListTestProofs,
    resolve_test_proof_views: ResolveTestProofViews,
) -> list[Any]:
    return resolve_test_proof_views(list_test_proofs(command.rule_id))


async def export_test_proof_report(
    command: ExportTestProofReportCommand,
    services: TestProofReportServices,
) -> TestProofReportResult:
    proofs = services.resolve_test_proof_views(services.list_test_proofs(command.rule_id))
    if not proofs:
        raise HTTPException(status_code=404, detail=f"No test proofs found for rule '{command.rule_id}'")

    if command.proof_id:
        selected_proof = next((proof for proof in proofs if str(getattr(proof, "id", "")) == str(command.proof_id)), None)
        if selected_proof is None:
            raise HTTPException(status_code=404, detail=f"Proof '{command.proof_id}' not found for rule '{command.rule_id}'")
    else:
        selected_proof = proofs[0]

    selected_index = proofs.index(selected_proof)
    previous_proof = proofs[selected_index + 1] if selected_index + 1 < len(proofs) else None

    latest_trace = getattr(selected_proof, "executionTrace", None)
    previous_trace = getattr(previous_proof, "executionTrace", None) if previous_proof is not None else None
    latest_rule_version_id = _normalize_optional_str(getattr(latest_trace, "ruleVersionId", None))
    previous_rule_version_id = _normalize_optional_str(getattr(previous_trace, "ruleVersionId", None))

    diff_payload = None
    if latest_rule_version_id and previous_rule_version_id and latest_rule_version_id != previous_rule_version_id:
        try:
            compared = await services.compare_rule_versions(command.rule_id, previous_rule_version_id, latest_rule_version_id)
            diff_payload = compared if isinstance(compared, Mapping) else None
        except Exception:
            diff_payload = None

    rule_entity = await services.get_rule_by_id(command.rule_id)
    rule_name = getattr(rule_entity, "name", None) if rule_entity is not None else None
    dimension = getattr(rule_entity, "dimension", None) if rule_entity is not None else None

    expression = ""
    if latest_rule_version_id:
        try:
            rule_version = await services.get_rule_version(command.rule_id, latest_rule_version_id)
            expression = str((rule_version or {}).get("expression") or "")
        except Exception:
            expression = ""

    version_diff_section = services.render_version_diff_section(diff_payload, selected_proof, previous_proof)
    markdown_report = services.build_markdown_report(
        rule_id=command.rule_id,
        proof=selected_proof,
        rule_name=str(rule_name or command.rule_id),
        dimension=str(dimension or ""),
        compiled_expression=expression,
        version_diff_section=version_diff_section,
    )

    safe_rule_id = str(command.rule_id).replace("/", "-")
    safe_proof_id = str(getattr(selected_proof, "id", "")).replace("/", "-")
    if command.output_format == "pdf":
        return TestProofReportResult(
            body=services.render_pdf(markdown_report),
            media_type="application/pdf",
            filename=f"test-report-{safe_rule_id}-{safe_proof_id}.pdf",
        )

    return TestProofReportResult(
        body=markdown_report,
        media_type="text/markdown",
        filename=f"test-report-{safe_rule_id}-{safe_proof_id}.md",
    )