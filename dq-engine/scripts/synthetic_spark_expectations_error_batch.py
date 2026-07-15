#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DQ_ENGINE_ROOT = ROOT / "dq-engine"
if str(DQ_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(DQ_ENGINE_ROOT))

from spark_expectations_execution_adapter import build_error_management_plan


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a chunked error-management plan for a synthetic batch")
    parser.add_argument("--error-count", type=int, default=250_000)
    parser.add_argument("--chunk-size", type=int, default=10_000)
    parser.add_argument("--sample-size", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    failed_rows = (
        {"row_id": row_id, "reason": f"synthetic-failure-{row_id}"}
        for row_id in range(max(args.error_count, 0))
    )
    plan = build_error_management_plan(
        failed_rows,
        chunk_size=max(args.chunk_size, 1),
        max_samples=max(args.sample_size, 0),
    )
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
