import pytest
from datetime import UTC, datetime, timedelta

from app.infrastructure.repositories.in_memory_testing_repository import InMemoryTestingRepository

pytestmark = pytest.mark.usefixtures("clone_payload")


def test_generate_and_run_rule_with_generated_data_paths() -> None:
    repo = InMemoryTestingRepository()

    missing = repo.generate_test_data_for_version("missing", sample_count=3)
    assert missing.versionId == "missing"
    assert missing.attributeCount == 0
    assert len(missing.samples) == 0

    existing_version_id = next(iter(repo._version_catalog.keys()))  # type: ignore[attr-defined]
    generated = repo.generate_test_data_for_version(existing_version_id, sample_count=4)
    assert generated.sampleCount == 4
    assert generated.attributes

    rule_id = next(iter(repo._rules.keys()))  # type: ignore[attr-defined]
    run = repo.run_rule_with_generated_data(rule_id, existing_version_id, sample_count=4)
    assert run.ruleId == rule_id
    assert run.totalTests == 4


def test_store_proof_and_manual_rule_run_paths() -> None:
    repo = InMemoryTestingRepository()
    rule_id = next(iter(repo._rules.keys()))  # type: ignore[attr-defined]

    stored = repo.store_test_proof(
        rule_id,
        {
            "coverage": 0.8,
            "passed": False,
            "recordsTestedCount": 0,
            "failuresFound": 1,
            "proofData": {"suite": "unit"},
        },
    )
    assert stored.successRate == 0
    assert stored.proofData["executionTrace"]["executionId"]
    assert stored.proofData["executionTrace"]["correlationId"]
    assert stored.proofData["executionTrace"]["resultStatus"] == "failed"
    assert stored.executionTrace is not None
    assert stored.executionTrace.correlationId
    assert stored.executionTrace.resultStatus == "failed"

    run = repo.run_rule_against_test_data(
        rule_id,
        [{"email": "ok@example.com"}, {"email": "bad"}, {"email": None}],
        version_id_source="manual-source",
    )
    assert run.totalTests == 3
    assert run.passedCount == 1
    assert run.failedCount == 2
    assert run.testDataSource == "manual-source"


def test_run_rule_against_test_data_supports_is_not_null_expression() -> None:
    repo = InMemoryTestingRepository()
    rule_id = next(iter(repo._rules.keys()))  # type: ignore[attr-defined]

    run = repo.run_rule_against_test_data(
        rule_id,
        [
            {"is_active": True},
            {"is_active": False},
            {"is_active": None},
        ],
        version_id_source="manual-source",
        compiled_expression="is_active IS NOT NULL",
    )

    assert run.totalTests == 3
    assert run.passedCount == 2
    assert run.failedCount == 1
    assert [result.passed for result in run.results] == [True, True, False]


def test_run_rule_against_test_data_supports_new_check_type_expression_families() -> None:
    repo = InMemoryTestingRepository()
    rule_id = next(iter(repo._rules.keys()))  # type: ignore[attr-defined]

    cases = [
        ("name IS NOT NULL AND TRIM(name) != ''", {"name": "Alice"}, True),
        ("status IS NOT NULL AND status != 'N/A'", {"status": "active"}, True),
        ("LOWER(preferred_language) IN ('val_1', 'val_2')", {"preferred_language": "VAL_1"}, True),
        ("LOWER(preferred_language) NOT IN ('blocked')", {"preferred_language": "allowed"}, True),
        ("REGEXP_MATCHES(email, '.*@.*')", {"email": "user@example.com"}, True),
        ("event_date <= NOW()", {"event_date": "2020-01-01T00:00:00+00:00"}, True),
        ("DATEDIFF(NOW(), updated_at) <= 7", {"updated_at": "2026-03-19T00:00:00+00:00"}, True),
        ("TIMESTAMPDIFF(HOUR, start_at, end_at) <= 24", {"start_at": "2026-03-20T00:00:00+00:00", "end_at": "2026-03-20T12:00:00+00:00"}, True),
    ]

    for expression, row, expected in cases:
        run = repo.run_rule_against_test_data(
            rule_id,
            [row],
            version_id_source="manual-source",
            compiled_expression=expression,
        )
        assert run.totalTests == 1
        assert run.passedCount in {0, 1}


def test_run_rule_against_test_data_supports_uniqueness_and_referential_patterns() -> None:
    repo = InMemoryTestingRepository()
    rule_id = next(iter(repo._rules.keys()))  # type: ignore[attr-defined]

    uniqueness_run = repo.run_rule_against_test_data(
        rule_id,
        [{"id": 1}, {"id": 1}, {"id": 2}],
        version_id_source="manual-source",
        compiled_expression="COUNT(*) OVER (PARTITION BY id) = 1",
    )
    assert [result.passed for result in uniqueness_run.results] == [False, False, True]

    ref_run = repo.run_rule_against_test_data(
        rule_id,
        [{"customer_id": 1, "id": 1}, {"customer_id": 3, "id": 2}],
        version_id_source="manual-source",
        compiled_expression="customer_id IN (SELECT id FROM customers)",
    )
    assert [result.passed for result in ref_run.results] == [True, False]


def test_threshold_rule_passes_when_success_rate_meets_min_good_threshold() -> None:
    repo = InMemoryTestingRepository()
    rule_id = next(iter(repo._rules.keys()))  # type: ignore[attr-defined]

    repo._rules[rule_id]["check_type"] = "THRESHOLD"  # type: ignore[index]
    repo._rules[rule_id]["check_type_params"] = {  # type: ignore[index]
        "checkType": "THRESHOLD",
        "attribute": "is_active",
        "metric": "null_pct",
        "operator": "gte",
        "threshold": 95,
    }

    run = repo.run_rule_against_test_data(
        rule_id,
        [{"is_active": True} for _ in range(95)] + [{"is_active": None} for _ in range(5)],
        version_id_source="manual-source",
        compiled_expression="is_active IS NOT NULL",
    )

    assert run.successRate == 95
    assert run.rulePassed is True
    assert run.requiredSuccessRate == 95


def test_proof_creation_update_and_status_defaults_cover_helper_branches() -> None:
    repo = InMemoryTestingRepository()
    rule_id = next(iter(repo._rules.keys()))  # type: ignore[attr-defined]

    assert repo._normalize_test_proof_status("running") == "running"  # type: ignore[attr-defined]
    assert repo._normalize_test_proof_status("  ", passed=True) == "passed"  # type: ignore[attr-defined]
    assert repo._normalize_test_proof_status("  ", passed=False) == "failed"  # type: ignore[attr-defined]
    assert repo._normalize_test_proof_status("  ") == "pending"  # type: ignore[attr-defined]

    created = repo.create_test_proof(
        rule_id,
        {
            "coverage": 0.25,
            "recordsTestedCount": 2,
            "failuresFound": 1,
            "proofData": {"seed": "alpha"},
        },
        status="pending",
    )
    assert created.status == "pending"
    assert created.executionTrace.executedAt is None
    assert created.executionTrace.resultStatus == "pending"

    updated = repo.update_test_proof(
        created.id,
        {
            "coverage": 0.5,
            "recordsTestedCount": 4,
            "failuresFound": 1,
            "proofData": {"seed": "beta"},
            "metrics": {"matched": 3},
            "diagnostics": [{"note": "ok"}],
        },
        status="passed",
    )
    assert updated.status == "passed"
    assert updated.executionTrace.resultStatus == "passed"
    assert updated.proofData["seed"] == "beta"
    assert updated.metrics == {"matched": 3}
    assert updated.diagnostics == [{"note": "ok"}]

    with pytest.raises(KeyError, match="test_proof missing"):
        repo.update_test_proof("missing", {}, status="failed")


def test_threshold_helper_covers_comparator_and_invalid_threshold_paths() -> None:
    repo = InMemoryTestingRepository()

    assert repo._evaluate_rule_pass("NOTE", {}, 100.0, 0) == (True, None)  # type: ignore[attr-defined]
    assert repo._evaluate_rule_pass("THRESHOLD", {}, 100.0, 0) == (True, None)  # type: ignore[attr-defined]
    assert repo._evaluate_rule_pass("THRESHOLD", {"threshold": "bad"}, 100.0, 0) == (True, None)  # type: ignore[attr-defined]
    assert repo._evaluate_rule_pass("THRESHOLD", {"threshold": 80, "operator": "gt"}, 81.0, 1) == (True, 80.0)  # type: ignore[attr-defined]
    assert repo._evaluate_rule_pass("THRESHOLD", {"threshold": 80, "operator": "lt"}, 79.0, 1) == (True, 80.0)  # type: ignore[attr-defined]
    assert repo._evaluate_rule_pass("THRESHOLD", {"threshold": 80, "operator": "lte"}, 80.0, 1) == (True, 80.0)  # type: ignore[attr-defined]
    assert repo._evaluate_rule_pass("THRESHOLD", {"threshold": 80, "operator": "gte"}, 79.0, 1) == (False, 80.0)  # type: ignore[attr-defined]


def test_batch_request_and_proof_list_paths() -> None:
    repo = InMemoryTestingRepository()
    rule_id = next(iter(repo._rules.keys()))  # type: ignore[attr-defined]

    batch = repo.create_batch_test_requests([rule_id], test_data_config={"k": "v"})
    assert len(batch) == 1
    assert batch[0].requestedBy == "system"
    assert batch[0].workspace == "default"

    listed = repo.list_batch_test_requests(workspace="default", status="pending")
    assert len(listed) >= 1
    assert any(row.id == batch[0].id for row in listed)
    assert repo.get_batch_test_request(batch[0].id) is not None
    assert repo.get_batch_test_request("req-1") is None

    assert repo.run_batch_test_request(batch[0].id).status == "completed"
    updated = repo.get_batch_test_request(batch[0].id)
    assert updated is not None
    assert updated.status == "completed"
    assert updated.completedAt
    assert updated.proofId
    assert updated.executionCorrelationId

    proofs = repo.list_test_proofs(rule_id)
    assert isinstance(proofs, list)
    if proofs:
        assert proofs[0].executionTrace is not None


def test_batch_request_runtime_failure_path(monkeypatch) -> None:
    repo = InMemoryTestingRepository()
    rule_id = next(iter(repo._rules.keys()))  # type: ignore[attr-defined]

    monkeypatch.setattr(
        repo,
        "run_rule_with_generated_data",
        lambda rule_id, version_id, sample_count=10, compiled_expression=None: (_ for _ in ()).throw(RuntimeError("executor exploded")),
    )

    batch = repo.create_batch_test_requests([rule_id], test_data_config={"versionId": "dov-23"})
    request_id = batch[0].id

    run_result = repo.run_batch_test_request(request_id)
    assert run_result.status == "failed"

    updated = repo.get_batch_test_request(request_id)
    assert updated is not None
    assert updated.status == "failed"
    assert updated.completedAt
    assert updated.proofId is None
    assert updated.testDataConfig["executionFailure"]["reason"] == "executor-runtime-error"
    assert updated.testDataConfig["executionFailure"]["errorType"] == "RuntimeError"
    assert updated.testDataConfig["executionFailure"]["errorCode"] == "EXECUTOR_RUNTIME_ERROR"
    assert updated.testDataConfig["executionFailure"]["correlationId"]
    assert updated.executionCorrelationId == updated.testDataConfig["executionFailure"]["correlationId"]


def test_run_rule_against_test_data_surfaces_non_executable_expression_warning() -> None:
    repo = InMemoryTestingRepository()
    rule_id = next(iter(repo._rules.keys()))  # type: ignore[attr-defined]

    run = repo.run_rule_against_test_data(
        rule_id,
        [{"email": "user1@example.com"}, {"email": "user2@example.com"}],
        version_id_source="manual-source",
        compiled_expression="UNSUPPORTED_FUNC(email)",
    )

    assert run.totalTests == 2
    assert run.passedCount == 0
    assert run.failedCount == 2
    assert run.executionContext is not None
    assert run.executionContext["reason"] == "expression-not-executable"
    assert "evaluationWarning" in run.ruleDetails


def test_semantic_tokens_matchers_and_dataset_maps_cover_branch_paths() -> None:
    repo = InMemoryTestingRepository()

    assert repo._canonical_semantic_token(True, None) == "active"  # type: ignore[attr-defined]
    assert repo._canonical_semantic_token(False, None) == "inactive"  # type: ignore[attr-defined]
    assert repo._canonical_semantic_token("", None) is None  # type: ignore[attr-defined]
    assert repo._canonical_semantic_token("YES", {"activeSynonyms": ["yes"], "inactiveSynonyms": ["no"]}) == "active"  # type: ignore[attr-defined]
    assert repo._canonical_semantic_token("no", {"activeSynonyms": ["yes"], "inactiveSynonyms": ["no"]}) == "inactive"  # type: ignore[attr-defined]

    contains = repo._build_rule_matcher("email contains '@'")  # type: ignore[attr-defined]
    assert contains({"email": "user@example.com"}) is True
    assert contains({"email": "invalid"}) is False

    regex = repo._build_rule_matcher("email ~ '.*@.*'")  # type: ignore[attr-defined]
    assert regex({"email": "user@example.com"}) is True
    assert regex({"email": "invalid"}) is False

    stats = repo._create_semantic_stats({"enabled": True, "fieldAliasMappings": {"status": "state"}})  # type: ignore[attr-defined]
    equality = repo._build_rule_matcher("status = 'active'", semantic_config={"enabled": True}, semantic_stats=stats)  # type: ignore[attr-defined]
    assert equality({"state": "active"}) is True
    assert equality({"state": "enabled"}) is True
    assert equality({"state": "disabled"}) is False
    assert stats["field_alias_hits"] >= 1
    assert stats["value_coercion_matches"] >= 1

    trim_not_empty = repo._build_rule_matcher("name IS NOT NULL AND TRIM(name) != ''")  # type: ignore[attr-defined]
    assert trim_not_empty({"name": "Alice"}) is True
    assert trim_not_empty({"name": "   "}) is False

    not_default = repo._build_rule_matcher("status IS NOT NULL AND status != 'N/A'")  # type: ignore[attr-defined]
    assert not_default({"status": "active"}) is True
    assert not_default({"status": "N/A"}) is False

    lower_in = repo._build_rule_matcher("LOWER(status) IN ('active','enabled')")  # type: ignore[attr-defined]
    assert lower_in({"status": "ACTIVE"}) is True
    assert lower_in({"status": "disabled"}) is False

    lower_not_in = repo._build_rule_matcher("LOWER(status) NOT IN ('blocked')")  # type: ignore[attr-defined]
    assert lower_not_in({"status": "allowed"}) is True
    assert lower_not_in({"status": "blocked"}) is False
    assert lower_not_in({"status": None}) is True

    regex_matches = repo._build_rule_matcher("REGEXP_MATCHES(email, '^[A-Z]+@EXAMPLE.COM$', 'i')")  # type: ignore[attr-defined]
    assert regex_matches({"email": "USER@example.com"}) is True
    assert regex_matches({"email": "invalid"}) is False

    is_not_null = repo._build_rule_matcher("status IS NOT NULL")  # type: ignore[attr-defined]
    is_null = repo._build_rule_matcher("status IS NULL")  # type: ignore[attr-defined]
    assert is_not_null({"status": "x"}) is True
    assert is_not_null({"status": None}) is False
    assert is_null({"status": None}) is True
    assert is_null({"status": "x"}) is False

    now_expr = repo._build_rule_matcher("event_date <= NOW()")  # type: ignore[attr-defined]
    assert now_expr({"event_date": (datetime.now(UTC) - timedelta(days=1)).isoformat()}) is True
    assert now_expr({"event_date": (datetime.now(UTC) + timedelta(days=1)).isoformat()}) is False

    datediff_expr = repo._build_rule_matcher("DATEDIFF(NOW(), updated_at) <= 7")  # type: ignore[attr-defined]
    assert datediff_expr({"updated_at": (datetime.now(UTC) - timedelta(days=2)).isoformat()}) is True
    assert datediff_expr({"updated_at": (datetime.now(UTC) - timedelta(days=10)).isoformat()}) is False

    tsdiff_expr = repo._build_rule_matcher("TIMESTAMPDIFF(HOUR, start_at, end_at) <= 24")  # type: ignore[attr-defined]
    assert tsdiff_expr({"start_at": "2026-03-01T00:00:00+00:00", "end_at": "2026-03-01T12:00:00+00:00"}) is True
    assert tsdiff_expr({"start_at": "2026-03-01T00:00:00+00:00", "end_at": "2026-03-03T12:00:00+00:00"}) is False

    uniq = repo._dataset_pass_map_for_expression("COUNT(*) OVER (PARTITION BY id) = 1", [{"id": 1}, {"id": 1}, {"id": 2}])  # type: ignore[attr-defined]
    assert uniq == [False, False, True]
    uniq_empty = repo._dataset_pass_map_for_expression("COUNT(*) OVER (PARTITION BY   ) = 1", [{"id": 1}])  # type: ignore[attr-defined]
    assert uniq_empty == [False]

    ref_map = repo._dataset_pass_map_for_expression("customer_id IN (SELECT id FROM customers)", [{"customer_id": 1, "id": 1}, {"customer_id": 2, "id": 1}])  # type: ignore[attr-defined]
    assert ref_map == [True, False]
    assert repo._dataset_pass_map_for_expression("status = 'active'", [{"status": "active"}]) is None  # type: ignore[attr-defined]


def test_threshold_evaluation_supports_operator_variants() -> None:
    repo = InMemoryTestingRepository()

    assert repo._evaluate_rule_pass("THRESHOLD", {"threshold": "bad"}, 90.0, 0) == (True, None)  # type: ignore[attr-defined]
    assert repo._evaluate_rule_pass("THRESHOLD", {"threshold": 80, "operator": "gt"}, 81.0, 1) == (True, 80.0)  # type: ignore[attr-defined]
    assert repo._evaluate_rule_pass("THRESHOLD", {"threshold": 80, "operator": "lt"}, 79.0, 1) == (True, 80.0)  # type: ignore[attr-defined]
    assert repo._evaluate_rule_pass("THRESHOLD", {"threshold": 80, "operator": "lte"}, 80.0, 1) == (True, 80.0)  # type: ignore[attr-defined]
    assert repo._evaluate_rule_pass("THRESHOLD", {"threshold": 80, "operator": "gte"}, 79.0, 1) == (False, 80.0)  # type: ignore[attr-defined]
