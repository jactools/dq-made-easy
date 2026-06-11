import os

from app.core.runtime_queues import (
    resolve_gx_execution_queue_key,
    resolve_gx_join_pair_materialization_queue_key,
    resolve_natural_language_draft_queue_key,
    resolve_profiling_queue_key,
    resolve_test_data_materialization_queue_key,
)


def test_resolve_profiling_queue_key_prefers_primary_alias(monkeypatch) -> None:
    monkeypatch.setenv("PROFILING_QUEUE_KEY", "profiling.primary")
    monkeypatch.setenv("DQ_PROFILING_QUEUE_KEY", "profiling.fallback")

    assert resolve_profiling_queue_key() == "profiling.primary"


def test_resolve_profiling_queue_key_uses_fallback_alias(monkeypatch) -> None:
    monkeypatch.delenv("PROFILING_QUEUE_KEY", raising=False)
    monkeypatch.setenv("DQ_PROFILING_QUEUE_KEY", "profiling.fallback")

    assert resolve_profiling_queue_key() == "profiling.fallback"


def test_resolve_natural_language_draft_queue_key_returns_none_for_blank_value(monkeypatch) -> None:
    monkeypatch.setenv("NATURAL_LANGUAGE_DRAFT_QUEUE_KEY", "   ")

    assert resolve_natural_language_draft_queue_key() is None


def test_resolve_gx_execution_queue_key_uses_fallback_alias(monkeypatch) -> None:
    monkeypatch.delenv("GX_EXECUTION_QUEUE_KEY", raising=False)
    monkeypatch.setenv("DQ_GX_EXECUTION_QUEUE_KEY", "gx.exec.fallback")

    assert resolve_gx_execution_queue_key() == "gx.exec.fallback"


def test_resolve_join_pair_materialization_queue_key_prefers_primary_alias(monkeypatch) -> None:
    monkeypatch.setenv("GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY", "gx.join.primary")
    monkeypatch.setenv("DQ_GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY", "gx.join.fallback")

    assert resolve_gx_join_pair_materialization_queue_key() == "gx.join.primary"


def test_resolve_test_data_materialization_queue_key_uses_fallback_alias(monkeypatch) -> None:
    monkeypatch.delenv("TEST_DATA_MATERIALIZATION_QUEUE_KEY", raising=False)
    monkeypatch.setenv("DQ_TEST_DATA_MATERIALIZATION_QUEUE_KEY", "test.data.fallback")

    assert resolve_test_data_materialization_queue_key() == "test.data.fallback"


def test_resolve_queue_keys_return_none_when_aliases_missing(monkeypatch) -> None:
    keys = [
        "PROFILING_QUEUE_KEY",
        "DQ_PROFILING_QUEUE_KEY",
        "NATURAL_LANGUAGE_DRAFT_QUEUE_KEY",
        "GX_EXECUTION_QUEUE_KEY",
        "DQ_GX_EXECUTION_QUEUE_KEY",
        "GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY",
        "DQ_GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY",
        "TEST_DATA_MATERIALIZATION_QUEUE_KEY",
        "DQ_TEST_DATA_MATERIALIZATION_QUEUE_KEY",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)

    assert resolve_profiling_queue_key() is None
    assert resolve_natural_language_draft_queue_key() is None
    assert resolve_gx_execution_queue_key() is None
    assert resolve_gx_join_pair_materialization_queue_key() is None
    assert resolve_test_data_materialization_queue_key() is None


def test_runtime_queue_resolvers_read_os_environ_directly(monkeypatch) -> None:
    monkeypatch.setitem(os.environ, "NATURAL_LANGUAGE_DRAFT_QUEUE_KEY", "nl.queue")

    assert resolve_natural_language_draft_queue_key() == "nl.queue"