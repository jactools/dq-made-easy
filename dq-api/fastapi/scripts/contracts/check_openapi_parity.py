import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class ParityIssue:
    kind: str
    operation: str
    detail: str


@dataclass
class ParityResult:
    issues: list[ParityIssue] = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return len(self.issues) == 0


def _normalize_path(path: str, strip_prefix: str) -> str:
    if strip_prefix and path.startswith(strip_prefix):
        normalized = path[len(strip_prefix) :]
        return normalized if normalized.startswith("/") else f"/{normalized}"
    return path


def _operation_index(spec: dict[str, Any], strip_prefix: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for raw_path, path_item in spec.get("paths", {}).items():
        path = _normalize_path(raw_path, strip_prefix)
        for method, operation in path_item.items():
            m = method.lower()
            if m in HTTP_METHODS:
                index[f"{m.upper()} {path}"] = operation
    return index


def _required_param_names(operation: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for param in operation.get("parameters", []):
        if param.get("required"):
            names.add(f"{param.get('in', 'unknown')}:{param.get('name', '')}")
    return names


def _response_codes(operation: dict[str, Any]) -> set[str]:
    return set(operation.get("responses", {}).keys())


def _compare_operations(
    baseline_ops: dict[str, dict[str, Any]],
    current_ops: dict[str, dict[str, Any]],
) -> ParityResult:
    result = ParityResult()

    for operation_key, baseline_operation in baseline_ops.items():
        current_operation = current_ops.get(operation_key)
        if current_operation is None:
            result.issues.append(
                ParityIssue("missing-operation", operation_key, "Operation missing in current spec")
            )
            continue

        baseline_params = _required_param_names(baseline_operation)
        current_params = _required_param_names(current_operation)
        if baseline_params != current_params:
            result.issues.append(
                ParityIssue(
                    "param-mismatch",
                    operation_key,
                    f"required params baseline={sorted(baseline_params)} current={sorted(current_params)}",
                )
            )

        baseline_has_body = "requestBody" in baseline_operation
        current_has_body = "requestBody" in current_operation
        if baseline_has_body != current_has_body:
            result.issues.append(
                ParityIssue(
                    "request-body-mismatch",
                    operation_key,
                    f"requestBody baseline={baseline_has_body} current={current_has_body}",
                )
            )

        baseline_codes = _response_codes(baseline_operation)
        current_codes = _response_codes(current_operation)
        if not baseline_codes.issubset(current_codes):
            result.issues.append(
                ParityIssue(
                    "response-code-mismatch",
                    operation_key,
                    f"baseline codes missing in current: {sorted(baseline_codes - current_codes)}",
                )
            )

    for operation_key in sorted(current_ops.keys() - baseline_ops.keys()):
        result.issues.append(
            ParityIssue("new-operation", operation_key, "Operation exists in current but not in baseline")
        )

    return result


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _load_current_from_app() -> dict[str, Any]:
    from app.main import app

    return app.openapi()


def _load_required_operations(path: Path) -> set[str]:
    payload = _load_json(path)
    operations = payload.get("operations")
    if not isinstance(operations, list):
        raise ValueError("required operations file must contain an 'operations' list")
    normalized = {str(operation).strip() for operation in operations if str(operation).strip()}
    if not normalized:
        raise ValueError("required operations file contains no operations")
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description="Check OpenAPI parity against a baseline")
    parser.add_argument(
        "--baseline",
        default="contracts/baseline/openapi-legacy-v1.json",
        help="Path to baseline OpenAPI JSON.",
    )
    parser.add_argument(
        "--current",
        default="contracts/current/openapi-fastapi-v1.json",
        help="Path to current OpenAPI JSON (used with --current-source file).",
    )
    parser.add_argument(
        "--current-source",
        choices=["app", "file"],
        default="app",
        help="Use FastAPI app.open API or a JSON file for current contract.",
    )
    parser.add_argument(
        "--strip-prefix",
        default="",
        help="Optional path prefix strip (for example /api) before comparing.",
    )
    parser.add_argument(
        "--required-operations",
        default="",
        help="Optional JSON file with an 'operations' array of operation keys to require in current contract.",
    )
    parser.add_argument(
        "--ignore-new-operations",
        action="store_true",
        help="Ignore operations that exist in current but not in baseline.",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        print(f"ERROR: baseline not found: {baseline_path}")
        return 2

    baseline_spec = _load_json(baseline_path)

    if args.current_source == "file":
        current_path = Path(args.current)
        if not current_path.exists():
            print(f"ERROR: current spec not found: {current_path}")
            return 2
        current_spec = _load_json(current_path)
    else:
        current_spec = _load_current_from_app()
        current_path = Path(args.current)
        current_path.parent.mkdir(parents=True, exist_ok=True)
        current_path.write_text(json.dumps(current_spec, indent=2, sort_keys=True) + "\n")

    baseline_ops = _operation_index(baseline_spec, args.strip_prefix)
    current_ops = _operation_index(current_spec, args.strip_prefix)
    parity = _compare_operations(baseline_ops, current_ops)

    if args.ignore_new_operations:
        parity.issues = [issue for issue in parity.issues if issue.kind != "new-operation"]

    if args.required_operations:
        required_path = Path(args.required_operations)
        if not required_path.exists():
            print(f"ERROR: required operations file not found: {required_path}")
            return 2
        try:
            required_ops = _load_required_operations(required_path)
        except ValueError as exc:
            print(f"ERROR: invalid required operations file: {exc}")
            return 2

        for operation_key in sorted(required_ops):
            if operation_key not in current_ops:
                parity.issues.append(
                    ParityIssue("missing-required-operation", operation_key, "Required operation missing in current spec")
                )

    print(f"Baseline operations: {len(baseline_ops)}")
    print(f"Current operations: {len(current_ops)}")

    if parity.is_ok:
        print("PARITY OK: no differences found")
        return 0

    print(f"PARITY FAILED: {len(parity.issues)} difference(s)")
    for issue in parity.issues:
        print(f"- [{issue.kind}] {issue.operation}: {issue.detail}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
