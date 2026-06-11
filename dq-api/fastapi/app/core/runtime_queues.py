from __future__ import annotations

import os


def _resolve_env_alias(*names: str) -> str | None:
    for name in names:
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value
    return None


def resolve_profiling_queue_key() -> str | None:
    return _resolve_env_alias("PROFILING_QUEUE_KEY", "DQ_PROFILING_QUEUE_KEY")


def resolve_natural_language_draft_queue_key() -> str | None:
    return _resolve_env_alias("NATURAL_LANGUAGE_DRAFT_QUEUE_KEY")


def resolve_gx_execution_queue_key() -> str | None:
    return _resolve_env_alias("GX_EXECUTION_QUEUE_KEY", "DQ_GX_EXECUTION_QUEUE_KEY")


def resolve_gx_join_pair_materialization_queue_key() -> str | None:
    return _resolve_env_alias(
        "GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY",
        "DQ_GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY",
    )


def resolve_test_data_materialization_queue_key() -> str | None:
    return _resolve_env_alias(
        "TEST_DATA_MATERIALIZATION_QUEUE_KEY",
        "DQ_TEST_DATA_MATERIALIZATION_QUEUE_KEY",
    )