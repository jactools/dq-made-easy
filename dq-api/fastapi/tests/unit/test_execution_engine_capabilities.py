from __future__ import annotations

import pytest

from app.application.services.execution_engine_capabilities import ExecutionEngineCapabilityError
from app.application.services.execution_engine_capabilities import get_execution_engine_capability
from app.application.services.execution_engine_capabilities import require_sql_pushdown_capability


def test_get_execution_engine_capability_returns_pyspark_native_with_sql_pushdown() -> None:
    capability = get_execution_engine_capability("pyspark_native")

    assert capability.engine_type == "pyspark_native"
    assert capability.sql_pushdown_supported is True


def test_require_sql_pushdown_capability_succeeds_for_pyspark_native() -> None:
    capability = require_sql_pushdown_capability("pyspark_native")

    assert capability.sql_pushdown_supported is True
    assert capability.engine_type == "pyspark_native"


def test_require_sql_pushdown_capability_raises_for_non_pushdown_engine() -> None:
    with pytest.raises(ExecutionEngineCapabilityError) as exc_info:
        require_sql_pushdown_capability("gx")

    assert exc_info.value.error_code == "sql_pushdown_unsupported"
    assert exc_info.value.engine_type == "gx"
