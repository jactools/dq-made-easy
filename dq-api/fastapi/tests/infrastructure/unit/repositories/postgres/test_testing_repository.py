"""Unit tests for PostgresTestingRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import app.infrastructure.repositories.postgres_testing_repository as t_mod
from app.infrastructure.repositories.postgres_testing_repository import PostgresTestingRepository


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _Session:
    def __init__(self, get_map=None, scalar_values=None):
        self.get_map = dict(get_map or {})
        self.scalar_values = list(scalar_values or [])
        self.added = []
        self.committed = False

    def get(self, model, key):
        model_key = (getattr(model, "__name__", str(model)), str(key))
        if model_key in self.get_map:
            return self.get_map[model_key]
        return self.get_map.get(str(key))

    def execute(self, stmt):
        values = self.scalar_values.pop(0) if self.scalar_values else []
        return _ScalarResult(values)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_generate_test_data_for_missing_version(monkeypatch):
    session = _Session(get_map={})
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.generate_test_data_for_version("missing", sample_count=3)

    assert out.versionId == "missing"
    assert out.attributeCount == 0
    assert out.sampleCount == 3


def test_generate_test_data_for_version_maps_attributes(
    monkeypatch,
    testing_version_entity_row: dict[str, object],
    testing_attribute_entity_rows: list[dict[str, object]],
    clone_payload,
):
    version_row = SimpleNamespace(**clone_payload(testing_version_entity_row))
    attr1 = SimpleNamespace(**clone_payload(testing_attribute_entity_rows[0]))
    attr2 = SimpleNamespace(**clone_payload(testing_attribute_entity_rows[1]))

    sessions = [
        _Session(get_map={"v1": version_row}),
        _Session(scalar_values=[[attr1, attr2]]),
    ]

    def fake_scope(db_url):
        return _Ctx(sessions.pop(0))

    monkeypatch.setattr(t_mod, "session_scope", fake_scope)

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.generate_test_data_for_version("v1", sample_count=2)

    assert out.versionId == "v1"
    assert out.versionName == 2
    assert out.attributeCount == 2
    assert len(out.samples) == 2
    assert "email" in out.samples[0]


def test_run_rule_against_test_data_evaluates_expression(
    monkeypatch,
    testing_contains_rule_row: dict[str, object],
    clone_payload,
):
    rule_row = SimpleNamespace(**clone_payload(testing_contains_rule_row))
    session = _Session(get_map={"r1": rule_row})
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.run_rule_against_test_data(
        "r1",
        [{"email": "a@example.com"}, {"email": "invalid"}],
        version_id_source="v1",
    )

    assert out.ruleId == "r1"
    assert out.totalTests == 2
    assert out.passedCount == 1
    assert out.failedCount == 1


def test_run_rule_against_test_data_evaluates_regexp_matches_expression(
    monkeypatch,
    testing_contains_rule_row: dict[str, object],
    clone_payload,
):
    rule_row = SimpleNamespace(**clone_payload(testing_contains_rule_row))
    session = _Session(get_map={"r1": rule_row})
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.run_rule_against_test_data(
        "r1",
        [{"email": "user1@example.com"}, {"email": "bad"}],
        version_id_source="v1",
        compiled_expression=r"REGEXP_MATCHES(email, '^[^\s@]+@[^\s@]+\.[^\s@]+$')",
    )

    assert out.ruleId == "r1"
    assert out.totalTests == 2
    assert out.passedCount == 1
    assert out.failedCount == 1


def test_run_rule_against_test_data_applies_threshold_rule_pass_logic(
    monkeypatch,
    testing_contains_rule_row: dict[str, object],
    clone_payload,
):
    payload = clone_payload(testing_contains_rule_row)
    payload["check_type"] = "THRESHOLD"
    payload["check_type_params"] = '{"checkType":"THRESHOLD","attribute":"email","metric":"null_pct","operator":"gte","threshold":50}'
    rule_row = SimpleNamespace(**payload)
    session = _Session(get_map={"r1": rule_row})
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.run_rule_against_test_data(
        "r1",
        [{"email": "a@example.com"}, {"email": "invalid"}],
        version_id_source="v1",
    )

    assert out.successRate == 50
    assert out.rulePassed is True
    assert out.requiredSuccessRate == 50


def test_run_rule_against_test_data_prefers_current_version_threshold_snapshot(
    monkeypatch,
    testing_contains_rule_row: dict[str, object],
    clone_payload,
):
    payload = clone_payload(testing_contains_rule_row)
    payload["check_type"] = "THRESHOLD"
    payload["check_type_params"] = '{"checkType":"THRESHOLD","attribute":"email","metric":"null_pct","operator":"gte","threshold":100}'
    rule_row = SimpleNamespace(**payload)

    current_version_row = SimpleNamespace(rule_id="r1", version_id="rv-current-1")
    version_row = SimpleNamespace(
        id="rv-current-1",
        check_type="THRESHOLD",
        check_type_params='{"checkType":"THRESHOLD","attribute":"email","metric":"null_pct","operator":"gte","threshold":50}',
    )

    session = _Session(get_map={
        ("RuleRow", "r1"): rule_row,
        ("RuleCurrentVersionRow", "r1"): current_version_row,
        ("RuleVersionRow", "rv-current-1"): version_row,
    })
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.run_rule_against_test_data(
        "r1",
        [{"email": "a@example.com"}, {"email": "invalid"}],
        version_id_source="v1",
    )

    assert out.successRate == 50
    assert out.rulePassed is True
    assert out.requiredSuccessRate == 50


def test_run_rule_with_generated_data_delegates(monkeypatch):
    repo = PostgresTestingRepository("postgresql://example")

    monkeypatch.setattr(
        repo,
        "generate_test_data_for_version",
        lambda version_id, sample_count: SimpleNamespace(samples=[{"x": 1}]),
    )
    monkeypatch.setattr(
        repo,
        "run_rule_against_test_data",
        lambda rule_id, data, version_id_source=None, compiled_expression=None, semantic_config=None: SimpleNamespace(
            ruleId=rule_id,
            totalTests=len(data),
        ),
    )

    out = repo.run_rule_with_generated_data("r1", "v1", sample_count=1)

    assert out.ruleId == "r1"
    assert out.totalTests == 1


def test_store_test_proof_computes_success_rate(monkeypatch):
    session = _Session()
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))
    repo = PostgresTestingRepository("postgresql://example")

    out = repo.store_test_proof(
        "r1",
        {
            "recordsTestedCount": 10,
            "failuresFound": 2,
            "coverage": 88.2,
            "passed": True,
            "proofData": {"k": "v"},
        },
    )

    assert out.ruleId == "r1"
    assert out.proofId.startswith("proof-")
    assert out.successRate == 80.0
    assert out.proofData["k"] == "v"
    assert out.proofData["executionTrace"]["executionId"]
    assert out.proofData["executionTrace"]["correlationId"]
    assert out.proofData["executionTrace"]["resultStatus"] == "passed"
    assert out.executionTrace is not None
    assert out.executionTrace.correlationId
    assert out.executionTrace.resultStatus == "passed"
    assert len(session.added) == 1
    assert session.committed is True


def test_create_batch_test_requests_sets_defaults(monkeypatch):
    session = _Session()
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresTestingRepository("postgresql://example")

    out = repo.create_batch_test_requests(["r1", "r2"])

    assert len(out) == 2
    assert out[0].status == "pending"
    assert out[0].workspace == "default"
    assert len(session.added) == 2
    assert session.committed is True


def test_list_batch_test_requests_maps_rows(
    monkeypatch,
    testing_batch_request_row: dict[str, object],
    clone_payload,
):
    row_payload = clone_payload(testing_batch_request_row)
    row = SimpleNamespace(
        **{**row_payload, "requested_at": datetime.fromisoformat(str(row_payload["requested_at"]))}
    )
    session = _Session(scalar_values=[[row]])
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.list_batch_test_requests(workspace="w1", status="pending")

    assert len(out) == 1
    assert out[0].id == "b1"
    assert out[0].ruleId == "r1"


def test_get_batch_test_request_returns_none_when_missing(monkeypatch):
    session = _Session(get_map={})
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresTestingRepository("postgresql://example")
    assert repo.get_batch_test_request("missing") is None


def test_get_batch_test_request_maps_row(
    monkeypatch,
    testing_batch_request_row: dict[str, object],
    clone_payload,
):
    row_payload = clone_payload(testing_batch_request_row)
    row_payload["test_data_config"] = {}
    row = SimpleNamespace(
        **{**row_payload, "requested_at": datetime.fromisoformat(str(row_payload["requested_at"]))}
    )
    session = _Session(get_map={"b1": row})
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.get_batch_test_request("b1")

    assert out is not None
    assert out.id == "b1"
    assert out.ruleId == "r1"


def test_run_batch_test_request_updates_pending_row(monkeypatch):
    row = SimpleNamespace(
        id="b1",
        rule_id="r1",
        requested_by="system",
        requested_at=datetime.now(UTC),
        status="pending",
        workspace="default",
        proof_id=None,
        completed_at=None,
        test_data_config={},
    )
    session = _Session(get_map={"b1": row})
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    fake_proof = SimpleNamespace(proofId="proof-abc")
    monkeypatch.setattr(t_mod.PostgresTestingRepository, "store_test_proof", lambda self, rule_id, payload: fake_proof)

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.run_batch_test_request("b1")

    assert out.id == "b1"
    assert out.status == "completed"
    assert row.status == "completed"
    assert row.proof_id == "proof-abc"
    assert row.completed_at is not None
    assert row.test_data_config["executionCorrelationId"]
    assert session.committed is True

    mapped = repo.get_batch_test_request("b1")
    assert mapped is not None
    assert mapped.executionCorrelationId == row.test_data_config["executionCorrelationId"]


def test_run_batch_test_request_sets_failed_status_for_runtime_error(monkeypatch):
    row = SimpleNamespace(
        status="pending",
        rule_id="r1",
        proof_id=None,
        completed_at=None,
        test_data_config={"versionId": "dov-23"},
    )
    session = _Session(get_map={"b1": row})
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    store_calls: list[tuple[str, dict]] = []
    run_calls: list[tuple[str, str, int]] = []

    def _fake_store(self, rule_id, payload):
        store_calls.append((rule_id, payload))
        return SimpleNamespace(proofId="proof-should-not-be-created")

    def _fake_run(self, rule_id, version_id, sample_count=10, compiled_expression=None):
        run_calls.append((rule_id, version_id, sample_count))
        raise RuntimeError("worker unavailable")

    monkeypatch.setattr(t_mod.PostgresTestingRepository, "store_test_proof", _fake_store)
    monkeypatch.setattr(t_mod.PostgresTestingRepository, "run_rule_with_generated_data", _fake_run)

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.run_batch_test_request("b1")

    assert out.id == "b1"
    assert out.status == "failed"
    assert row.status == "failed"
    assert row.proof_id is None
    assert row.completed_at is not None
    assert row.test_data_config["executionFailure"]["reason"] == "executor-runtime-error"
    assert row.test_data_config["executionFailure"]["errorType"] == "RuntimeError"
    assert row.test_data_config["executionFailure"]["errorCode"] == "EXECUTOR_RUNTIME_ERROR"
    assert row.test_data_config["executionFailure"]["correlationId"]
    assert row.test_data_config["executionCorrelationId"] == row.test_data_config["executionFailure"]["correlationId"]
    assert run_calls == [("r1", "dov-23", 10)]
    assert store_calls == []
    assert session.committed is True


def test_run_batch_test_request_uses_executor_supplied_error_metadata(monkeypatch):
    row = SimpleNamespace(
        status="pending",
        rule_id="r1",
        proof_id=None,
        completed_at=None,
        test_data_config={"versionId": "dov-23"},
    )
    session = _Session(get_map={"b1": row})
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    class ExecutorDown(RuntimeError):
        error_code = "ENGINE_TIMEOUT"
        correlation_id = "corr-xyz-123"

    def _fake_run(self, rule_id, version_id, sample_count=10, compiled_expression=None):
        raise ExecutorDown("engine timeout")

    monkeypatch.setattr(t_mod.PostgresTestingRepository, "run_rule_with_generated_data", _fake_run)

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.run_batch_test_request("b1")

    assert out.status == "failed"
    assert row.test_data_config["executionFailure"]["errorCode"] == "ENGINE_TIMEOUT"
    assert row.test_data_config["executionFailure"]["correlationId"] == "corr-xyz-123"


def test_list_test_proofs_maps_rows(
    monkeypatch,
    testing_proof_row: dict[str, object],
    clone_payload,
):
    row_payload = clone_payload(testing_proof_row)
    row = SimpleNamespace(
        **{**row_payload, "test_date": datetime.fromisoformat(str(row_payload["test_date"]))}
    )
    session = _Session(scalar_values=[[row]])
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.list_test_proofs("r1")

    assert len(out) == 1
    assert out[0].status == "passed"
    assert out[0].coverage == 95.5
    assert out[0].executionTrace is not None
    assert out[0].executionTrace.executionId == "exec-p1"
    assert out[0].executionTrace.correlationId == "corr-p1"
    assert out[0].executionTrace.resultStatus == "passed"


def test_matcher_and_helpers():
    repo = PostgresTestingRepository("postgresql://example")

    contains = repo._build_rule_matcher("email contains '@'")
    assert contains({"email": "a@example.com"}) is True
    assert contains({"email": "bad"}) is False

    regex = repo._build_rule_matcher("email ~ '.*@.*'")
    assert regex({"email": "a@example.com"}) is True

    equals = repo._build_rule_matcher("status = 'active'")
    assert equals({"status": "active"}) is True


def test_run_rule_against_test_data_surfaces_non_executable_expression_warning(
    monkeypatch,
    testing_contains_rule_row: dict[str, object],
    clone_payload,
):
    rule_row = SimpleNamespace(**clone_payload(testing_contains_rule_row))
    session = _Session(get_map={"r1": rule_row})
    monkeypatch.setattr(t_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresTestingRepository("postgresql://example")
    out = repo.run_rule_against_test_data(
        "r1",
        [{"email": "user1@example.com"}, {"email": "user2@example.com"}],
        version_id_source="v1",
        compiled_expression="UNSUPPORTED_FUNC(email)",
    )

    assert out.totalTests == 2
    assert out.passedCount == 0
    assert out.failedCount == 2
    assert out.executionContext is not None
    assert out.executionContext["reason"] == "expression-not-executable"
    assert "not executable" in str(out.executionContext["message"]).lower()
    assert "evaluationWarning" in out.ruleDetails

    assert repo._sample_value_for_attribute({"name": "email", "type": "text"}, 0) == "user1@example.com"
    assert repo._sample_value_for_attribute({"name": "count", "type": "integer"}, 0) == 1
    assert repo._to_optional_text(None) is None
