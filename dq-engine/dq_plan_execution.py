"""Public facade for engine-agnostic plan execution (Layer 4).

Re-exports all public symbols from the sub-modules below.
Contains no implementation code. Callers should import from this module
unless they need a specific sub-module directly.

Sub-modules:
    dq_plan_execution_payload      — parse_dispatch_payload, coerce_*, normalize_*
    dq_plan_execution_api          — build_token_provider, api_request, build_execution_progress
    dq_plan_execution_report       — report_run, report_execution_progress
    dq_plan_execution_persistence  — persist_execution_payload
    dq_plan_execution_streaming    — publish_violations_to_kafka
    dq_plan_execution_orchestrator — execute_engine_rule_payload, process_engine_dispatch_message,
                                     build_execution_report_summary, build_execution_report_details
"""

from __future__ import annotations

# Payload helpers (Layer 3)
from dq_plan_execution_payload import (
    coerce_int,
    coerce_str,
    normalize_execution_engine,
    parse_dispatch_payload,
)

# API helpers (Layer 3)
from dq_plan_execution_api import (
    ExecutePayloadFn,
    ReportProgressFn,
    ReportRunFn,
    TokenProviderFactory,
    api_request,
    build_execution_progress,
    build_token_provider,
)

# Reporting helpers (Layer 3.5)
from dq_plan_execution_report import (
    report_execution_progress,
    report_run,
)

# Persistence helpers (Layer 3.5)
from dq_plan_execution_persistence import persist_execution_payload

# Orchestrator (Layer 3)
from dq_plan_execution_orchestrator import (
    SUPPORTED_EXECUTION_ENGINES,
    build_execution_report_details,
    build_execution_report_summary,
    execute_engine_rule_payload,
    process_engine_dispatch_message,
)

__all__ = [
    # Payload
    "coerce_int",
    "coerce_str",
    "normalize_execution_engine",
    "parse_dispatch_payload",
    # API
    "api_request",
    "build_execution_progress",
    "build_token_provider",
    # Reporting
    "report_execution_progress",
    "report_run",
    "ReportRunFn",
    "ReportProgressFn",
    "TokenProviderFactory",
    "ExecutePayloadFn",
    # Persistence
    "persist_execution_payload",
    # Orchestrator
    "SUPPORTED_EXECUTION_ENGINES",
    "build_execution_report_details",
    "build_execution_report_summary",
    "execute_engine_rule_payload",
    "process_engine_dispatch_message",
]
