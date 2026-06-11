from app.application.services import conflict_detection as cd


def test_extract_scalar_predicates():
    expr = "price > 100 AND quantity <= 5"
    preds = cd._extract_scalar_predicates(expr)
    assert "price" in preds and any(op == ">" and val == 100.0 for op, val in preds["price"]) 
    assert "quantity" in preds and any(op == "<=" and val == 5.0 for op, val in preds["quantity"]) 


def test_has_contradictory_predicates_true():
    a = "price > 100"
    b = "price < 50"
    assert cd._has_contradictory_predicates(a, b) is True


def test_has_contradictory_predicates_false():
    a = "price > 10"
    b = "price > 5"
    assert cd._has_contradictory_predicates(a, b) is False


def test_detect_conflicts_duplicate_expression_and_name():
    rules = [
        {"ruleId": "r1", "ruleName": "SameName", "compiledExpression": "x > 1"},
        {"ruleId": "r2", "ruleName": "samename", "compiledExpression": "x > 1"},
        {"ruleId": "r3", "ruleName": "Other", "compiledExpression": "y < 5"},
    ]
    conflicts = cd.detect_conflicts(rules)
    # Expect at least one duplicate_expression
    types = {c["conflictType"] for c in conflicts}
    assert "duplicate_expression" in types


def test_detect_conflicts_contradictory_predicates():
    rules = [
        {"ruleId": "r1", "ruleName": "A", "compiledExpression": "price > 100"},
        {"ruleId": "r2", "ruleName": "B", "compiledExpression": "price < 50"},
    ]
    conflicts = cd.detect_conflicts(rules)
    assert any(c["conflictType"] == "contradictory_predicates" for c in conflicts)
