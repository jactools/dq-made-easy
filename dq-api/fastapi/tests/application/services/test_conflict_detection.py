"""Unit tests for detect_conflicts() — DQ-1.3."""
from __future__ import annotations

import pytest

import app.application.services.conflict_detection as conflict_detection_mod
from app.application.services.conflict_detection import detect_conflicts


pytestmark = pytest.mark.usefixtures("monkeypatch")


def _rule(rule_id: str, name: str, expr: str) -> dict:
    return {"ruleId": rule_id, "ruleName": name, "compiledExpression": expr}


# ── No conflicts ─────────────────────────────────────────────────────────────

def test_empty_list_returns_no_conflicts() -> None:
    assert detect_conflicts([]) == []


def test_single_rule_returns_no_conflicts() -> None:
    assert detect_conflicts([_rule("r1", "Rule A", "price > 0")]) == []


def test_distinct_rules_return_no_conflicts() -> None:
    rules = [
        _rule("r1", "Rule A", "price > 0"),
        _rule("r2", "Rule B", "status = 'active'"),
    ]
    assert detect_conflicts(rules) == []


# ── Duplicate expression ──────────────────────────────────────────────────────

def test_duplicate_expression_detected() -> None:
    rules = [
        _rule("r1", "Rule A", "price > 0"),
        _rule("r2", "Rule B", "price > 0"),
    ]
    conflicts = detect_conflicts(rules)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["conflictType"] == "duplicate_expression"
    assert set([c["ruleId"], c["conflictsWith"]]) == {"r1", "r2"}


def test_duplicate_expression_symmetric_only_once() -> None:
    rules = [
        _rule("r1", "A", "x = 1"),
        _rule("r2", "B", "x = 1"),
        _rule("r3", "C", "x = 1"),
    ]
    conflicts = detect_conflicts(rules)
    dup_expr = [c for c in conflicts if c["conflictType"] == "duplicate_expression"]
    # 3 pairs but seen_pairs deduplica­tion: r1-r2, r1-r3, r2-r3
    assert len(dup_expr) == 3


# ── Duplicate name ────────────────────────────────────────────────────────────

def test_duplicate_name_case_insensitive() -> None:
    rules = [
        _rule("r1", "Active Check", "status = 'active'"),
        _rule("r2", "active check", "amount > 0"),
    ]
    conflicts = detect_conflicts(rules)
    dup_name = [c for c in conflicts if c["conflictType"] == "duplicate_name"]
    assert len(dup_name) == 1
    assert set([dup_name[0]["ruleId"], dup_name[0]["conflictsWith"]]) == {"r1", "r2"}


def test_empty_name_not_flagged_as_duplicate() -> None:
    rules = [
        _rule("r1", "", "a > 0"),
        _rule("r2", "", "b > 0"),
    ]
    conflicts = detect_conflicts(rules)
    dup_name = [c for c in conflicts if c["conflictType"] == "duplicate_name"]
    assert len(dup_name) == 0


# ── Contradictory predicates ──────────────────────────────────────────────────

def test_contradictory_predicates_detected() -> None:
    # price > 100 vs price < 50 — cannot both be true for the same record
    rules = [
        _rule("r1", "High Price", "price > 100"),
        _rule("r2", "Low Price", "price < 50"),
    ]
    conflicts = detect_conflicts(rules)
    contras = [c for c in conflicts if c["conflictType"] == "contradictory_predicates"]
    assert len(contras) == 1


def test_non_contradictory_range_not_flagged() -> None:
    # price > 10 and price < 100 — compatible range
    rules = [
        _rule("r1", "Min", "price > 10"),
        _rule("r2", "Max", "price < 100"),
    ]
    conflicts = detect_conflicts(rules)
    contras = [c for c in conflicts if c["conflictType"] == "contradictory_predicates"]
    assert len(contras) == 0


def test_equal_bounds_considered_contradictory() -> None:
    # price >= 50 and price < 50 → empty range
    rules = [
        _rule("r1", "A", "price >= 50"),
        _rule("r2", "B", "price < 50"),
    ]
    conflicts = detect_conflicts(rules)
    contras = [c for c in conflicts if c["conflictType"] == "contradictory_predicates"]
    assert len(contras) == 1


# ── Combined scenarios ────────────────────────────────────────────────────────

def test_multiple_conflict_types_all_emitted() -> None:
    rules = [
        _rule("r1", "Dup Name", "price > 100"),
        _rule("r2", "dup name", "price > 100"),  # dup name + dup expr
    ]
    conflicts = detect_conflicts(rules)
    types = {c["conflictType"] for c in conflicts}
    # Duplicate expression takes priority (seen_pairs prevents duplicate_name for same pair)
    assert "duplicate_expression" in types


def test_blank_expressions_skip_contradiction_detection() -> None:
    rules = [
        _rule("r1", "Same Name", ""),
        _rule("r2", "same name", "   "),
    ]

    conflicts = detect_conflicts(rules)

    assert conflicts == [
        {
            "ruleId": "r1",
            "conflictsWith": "r2",
            "conflictType": "duplicate_name",
            "message": "Rule 'r1' and rule 'r2' share the same name (case-insensitive): 'same name'",
        }
    ]


def test_non_bound_scalar_operators_are_not_treated_as_contradictions() -> None:
    rules = [
        _rule("r1", "Equals", "price = 10"),
        _rule("r2", "Not Equals", "price != 11"),
    ]

    conflicts = detect_conflicts(rules)

    assert [c for c in conflicts if c["conflictType"] == "contradictory_predicates"] == []


def test_seen_pairs_skip_repeated_duplicate_expression_ids() -> None:
    rules = [
        _rule("r1", "Rule A", "x = 1"),
        _rule("r2", "Rule B", "x = 1"),
        _rule("r2", "Rule B again", "y = 2"),
    ]

    conflicts = detect_conflicts(rules)

    assert [c for c in conflicts if c["conflictType"] == "duplicate_expression"] == [
        {
            "ruleId": "r1",
            "conflictsWith": "r2",
            "conflictType": "duplicate_expression",
            "message": "Rule 'r1' and rule 'r2' share the same compiled expression: 'x = 1'",
        }
    ]


def test_extract_scalar_predicates_skips_unparseable_numeric_values(monkeypatch) -> None:
    class _FakeMatch:
        def group(self, index: int) -> str:
            return {1: "price", 2: ">", 3: "not-a-number"}[index]

    class _FakePattern:
        def finditer(self, expression: str):
            del expression
            return [_FakeMatch()]

    monkeypatch.setattr(conflict_detection_mod, "_COMPARISON_PATTERN", _FakePattern())

    assert conflict_detection_mod._extract_scalar_predicates("ignored") == {}
