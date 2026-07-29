from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _extract_rule_id(expectation: dict[str, Any]) -> str | None:
    meta = expectation.get("meta") if isinstance(expectation.get("meta"), dict) else {}
    for candidate in (
        meta.get("dq.rule_id"),
        expectation.get("rule_id"),
        expectation.get("ruleId"),
    ):
        rule_id = str(candidate or "").strip()
        if rule_id:
            return rule_id
    return None


def _build_threshold_summary(expectation: dict[str, Any], *, passed: bool) -> dict[str, Any] | None:
    kwargs = expectation.get("kwargs") if isinstance(expectation.get("kwargs"), dict) else {}
    threshold: dict[str, Any] = {}

    for key in ("operator", "threshold", "min_value", "max_value", "value", "unit"):
        if key in kwargs and kwargs[key] is not None:
            threshold[key] = kwargs[key]

    if not threshold:
        return None

    operator = str(threshold.get("operator") or "").strip().lower()
    if operator in {"gt", "gte"}:
        threshold["relation"] = "met" if passed else "below"
    elif operator in {"lt", "lte"}:
        threshold["relation"] = "met" if passed else "above"
    elif operator == "between":
        threshold["relation"] = "within" if passed else "outside"
    else:
        threshold["relation"] = "met" if passed else "not_met"

    return threshold


def _build_rule_results(
    *,
    expectations: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]] | None,
    records_checked: int,
    evaluated_results: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    diagnostics_by_index: dict[int, list[dict[str, Any]]] = {}
    for diagnostic in diagnostics or []:
        expectation_index = diagnostic.get("expectation_index")
        try:
            normalized_index = int(expectation_index)
        except (TypeError, ValueError):
            continue
        diagnostics_by_index.setdefault(normalized_index, []).append(diagnostic)

    rule_results: list[dict[str, Any]] = []
    evaluated_by_index = {
        int(item["expectation_index"]): item
        for item in evaluated_results or []
        if isinstance(item, dict) and isinstance(item.get("expectation_index"), int)
    }
    for index, expectation in enumerate(expectations):
        failed_diagnostics = diagnostics_by_index.get(index, [])
        evaluated = evaluated_by_index.get(index, {})
        passed = evaluated.get("result") == "passed" if evaluated else not failed_diagnostics
        failed_records = evaluated.get("records_failed") if evaluated else None
        checked_records = evaluated.get("records_checked", records_checked)
        succeeded_records = evaluated.get("records_succeeded")
        if succeeded_records is None and isinstance(failed_records, int):
            succeeded_records = max(0, int(checked_records) - failed_records)
        result_item: dict[str, Any] = {
            "expectation_index": index,
            "rule_id": _extract_rule_id(expectation),
            "expectation_type": str(
                expectation.get("expectation_type")
                or expectation.get("check_type")
                or expectation.get("type")
                or ""
            ).strip() or None,
            "result": "passed" if passed else "failed",
            "records_checked": int(checked_records),
            "records_failed": failed_records,
            "records_succeeded": succeeded_records,
            "records_filtered_out": int(evaluated.get("records_filtered_out", 0)),
        }

        threshold = _build_threshold_summary(expectation, passed=passed)
        if threshold is not None:
            result_item["threshold"] = threshold

        if failed_diagnostics:
            result_item["diagnostic_count"] = len(failed_diagnostics)
            result_item["diagnostics"] = failed_diagnostics

        rule_results.append(result_item)

    return rule_results


def build_summary(
    *,
    expectations: list[dict[str, Any]],
    passed: int,
    failed: int,
    row_count: int | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    rule_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    records_checked = int(row_count or 0)
    rule_results = _build_rule_results(
        expectations=expectations,
        diagnostics=diagnostics,
        records_checked=records_checked,
        evaluated_results=rule_results,
    )
    return {
        "started_at": utc_now_iso(),
        "completed_at": utc_now_iso(),
        "expectation_count": int(len(expectations)),
        "passed_expectation_count": int(passed),
        "failed_expectation_count": int(failed),
        "passed_count": int(passed),
        "failed_count": int(failed),
        "records_checked": records_checked,
        "records_failed": None,
        "records_succeeded": None,
        "records_filtered_out": 0,
        "rule_results": rule_results,
    }


def add_row_identifiers(diagnostics: list[dict[str, Any]], *, row_identifier: str | None) -> list[dict[str, Any]]:
    if not row_identifier:
        return diagnostics
    for diagnostic in diagnostics:
        if "row_identifier" not in diagnostic:
            diagnostic["row_identifier"] = row_identifier
        if "data_primary_key" not in diagnostic:
            diagnostic["data_primary_key"] = row_identifier
    return diagnostics
