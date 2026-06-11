#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FASTAPI_ROOT = REPO_ROOT / "dq-api" / "fastapi"
DQ_UTILS_SRC = REPO_ROOT / "dq-utils" / "src"
CONTRACTS_ROOT = REPO_ROOT / "docs" / "contracts" / "internal-api"
OPERATIONS_PATH = CONTRACTS_ROOT / "aggregate" / "v1" / "operations.json"
SCHEMA_PATH = CONTRACTS_ROOT / "aggregate" / "v1" / "schema.json"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
GROUP_VERSIONED_API_RE = re.compile(r"^/[a-z][a-z0-9-]*/v\d+(?:/|$)")
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

if str(FASTAPI_ROOT) not in sys.path:
    sys.path.insert(0, str(FASTAPI_ROOT))
if DQ_UTILS_SRC.exists() and str(DQ_UTILS_SRC) not in sys.path:
    sys.path.insert(0, str(DQ_UTILS_SRC))


def _prepare_fastapi_contract_env() -> None:
    os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
    os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "")


def _is_internal_api_path(path: str) -> bool:
    normalized = str(path or "")
    if normalized == "/api" or normalized.startswith("/api/"):
        return True
    return GROUP_VERSIONED_API_RE.match(normalized) is not None


def _is_json_media_type(media_type: str | None) -> bool:
    normalized = str(media_type or "").lower()
    return "application/json" in normalized or normalized.endswith("+json")


def _resolve_request_body(spec: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any] | None:
    request_body = operation.get("requestBody")
    if isinstance(request_body, dict) and isinstance(request_body.get("$ref"), str):
        ref = request_body["$ref"]
        if ref.startswith("#/components/requestBodies/"):
            request_body_name = ref.split("/")[-1]
            request_body = spec.get("components", {}).get("requestBodies", {}).get(request_body_name)
    return request_body if isinstance(request_body, dict) else None


def _load_live_openapi() -> dict[str, Any]:
    _prepare_fastapi_contract_env()
    from app.main import app

    return app.openapi()


def _collect_live_json_body_operations(spec: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    operations: dict[tuple[str, str], dict[str, Any]] = {}

    for path, path_item in (spec.get("paths") or {}).items():
        if not isinstance(path_item, dict) or not _is_internal_api_path(str(path)):
            continue

        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            request_body = _resolve_request_body(spec, operation)
            if not request_body:
                continue

            content = request_body.get("content")
            if not isinstance(content, dict):
                continue

            json_media_types = sorted(media_type for media_type in content.keys() if _is_json_media_type(media_type))
            if not json_media_types:
                continue

            operations[(method.upper(), str(path))] = {
                "operation_id": str(operation.get("operationId") or "").strip(),
                "json_media_types": tuple(json_media_types),
            }

    return operations


def _defs_ref_name(schema_ref: str) -> str | None:
    prefix = "#/$defs/"
    if not isinstance(schema_ref, str) or not schema_ref.startswith(prefix):
        return None
    return schema_ref[len(prefix) :]


def _collect_request_schema_refs(manifest: dict[str, Any], schema_bundle: dict[str, Any]) -> list[str]:
    live_ops = _collect_live_json_body_operations(_load_live_openapi())
    manifest_ops = {
        (str(operation.get("method") or "").upper(), str(operation.get("path") or "")): operation
        for operation in (manifest.get("operations") or [])
        if isinstance(operation, dict)
    }
    defs = schema_bundle.get("$defs")
    if not isinstance(defs, dict):
        raise AssertionError(f"Invalid schema bundle: missing $defs in {SCHEMA_PATH}")

    request_refs: list[str] = []
    problems: list[str] = []

    for method_path, live_operation in sorted(live_ops.items()):
        manifest_operation = manifest_ops.get(method_path)
        if manifest_operation is None:
            problems.append(
                f"{method_path[0]} {method_path[1]}: missing operation entry in {OPERATIONS_PATH.relative_to(REPO_ROOT)}"
            )
            continue

        request_body = manifest_operation.get("request_body")
        if not isinstance(request_body, dict):
            problems.append(
                f"{method_path[0]} {method_path[1]}: missing request_body contract in {OPERATIONS_PATH.relative_to(REPO_ROOT)}"
            )
            continue

        content = request_body.get("content")
        if not isinstance(content, dict):
            problems.append(
                f"{method_path[0]} {method_path[1]}: request_body has no content map in {OPERATIONS_PATH.relative_to(REPO_ROOT)}"
            )
            continue

        for media_type in live_operation["json_media_types"]:
            media_contract = content.get(media_type)
            if not isinstance(media_contract, dict):
                problems.append(
                    f"{method_path[0]} {method_path[1]}: missing {media_type} schema contract in {OPERATIONS_PATH.relative_to(REPO_ROOT)}"
                )
                continue

            schema_ref = media_contract.get("schema_ref")
            def_name = _defs_ref_name(str(schema_ref) if schema_ref is not None else "")
            if def_name is None:
                problems.append(
                    f"{method_path[0]} {method_path[1]}: invalid schema_ref for {media_type}: {schema_ref!r}"
                )
                continue
            if def_name not in defs:
                problems.append(
                    f"{method_path[0]} {method_path[1]}: schema_ref {schema_ref} does not exist in {SCHEMA_PATH.relative_to(REPO_ROOT)}"
                )
                continue

            request_refs.append(str(schema_ref))

    if problems:
        message = "\n".join(f"- {problem}" for problem in problems)
        raise AssertionError(f"Internal API JSON-body contract coverage failed:\n{message}")

    return request_refs


def _walk_schema_for_snake_case(
    defs: dict[str, Any],
    schema_ref: str,
    *,
    seen_refs: set[str],
    errors: list[str],
) -> None:
    if schema_ref in seen_refs:
        return
    seen_refs.add(schema_ref)

    def_name = _defs_ref_name(schema_ref)
    if def_name is None:
        errors.append(f"Unsupported schema ref format: {schema_ref}")
        return

    schema = defs.get(def_name)
    if not isinstance(schema, dict):
        errors.append(f"Missing schema definition for ref {schema_ref}")
        return

    def visit(node: Any, path: str) -> None:
        if isinstance(node, dict):
            ref_value = node.get("$ref")
            if isinstance(ref_value, str) and ref_value.startswith("#/$defs/"):
                _walk_schema_for_snake_case(defs, ref_value, seen_refs=seen_refs, errors=errors)

            properties = node.get("properties")
            if isinstance(properties, dict):
                for property_name, property_schema in properties.items():
                    if not SNAKE_CASE_RE.fullmatch(str(property_name)):
                        errors.append(f"{path}.properties: property '{property_name}' is not snake_case")
                    visit(property_schema, f"{path}.properties.{property_name}")

            required = node.get("required")
            if isinstance(required, list):
                for item in required:
                    if isinstance(item, str) and not SNAKE_CASE_RE.fullmatch(item):
                        errors.append(f"{path}.required: key '{item}' is not snake_case")

            for key, value in node.items():
                if key == "properties":
                    continue
                visit(value, f"{path}.{key}")
            return

        if isinstance(node, list):
            for index, item in enumerate(node):
                visit(item, f"{path}[{index}]")

    visit(schema, f"{schema_ref}")


def main() -> int:
    if not OPERATIONS_PATH.exists():
        raise AssertionError(
            f"Missing internal API operations manifest: {OPERATIONS_PATH}. Regenerate contracts before validating."
        )
    if not SCHEMA_PATH.exists():
        raise AssertionError(f"Missing internal API schema bundle: {SCHEMA_PATH}. Regenerate contracts before validating.")

    manifest = json.loads(OPERATIONS_PATH.read_text())
    schema_bundle = json.loads(SCHEMA_PATH.read_text())
    defs = schema_bundle.get("$defs")
    if not isinstance(defs, dict):
        raise AssertionError(f"Invalid internal API schema bundle: {SCHEMA_PATH}")

    request_refs = _collect_request_schema_refs(manifest, schema_bundle)

    errors: list[str] = []
    seen_refs: set[str] = set()
    for schema_ref in sorted(set(request_refs)):
        _walk_schema_for_snake_case(defs, schema_ref, seen_refs=seen_refs, errors=errors)

    if errors:
        message = "\n".join(f"- {error}" for error in errors)
        raise AssertionError(f"Internal API request-schema snake_case validation failed:\n{message}")

    print(
        "OK: internal API JSON-body contract coverage passed "
        f"({len(request_refs)} request schema references across {len(set(request_refs))} unique request schemas)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())