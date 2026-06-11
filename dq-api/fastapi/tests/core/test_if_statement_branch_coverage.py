from __future__ import annotations

from tests.fixtures.if_statement_audit_fixtures import IfBranchAudit


# Keep this test as a quality gate without requiring immediate 100% branch parity.
# This ceiling tracks the current full-suite baseline and should only move downward
# as branch coverage improves.
MAX_ALLOWED_IF_BRANCH_GAPS = 1149


def test_every_if_statement_has_two_tested_branches(
    if_statement_branch_audit: IfBranchAudit,
) -> None:
    audit = if_statement_branch_audit
    assert audit.total_if_statements > 0

    gap_count = len(audit.gaps)
    if gap_count == 0:
        return

    sample = "\n".join(
        f"- {gap.file_path}:{gap.line_number} outgoing_arcs={list(gap.outgoing_arcs)}"
        for gap in audit.gaps[:200]
    )
    assert gap_count <= MAX_ALLOWED_IF_BRANCH_GAPS, (
        "If-branch coverage regression detected. "
        f"scanned_files={audit.scanned_files} total_if_statements={audit.total_if_statements} "
        f"missing={gap_count} allowed={MAX_ALLOWED_IF_BRANCH_GAPS}\n"
        f"Examples:\n{sample}"
    )
