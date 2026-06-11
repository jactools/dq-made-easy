import argparse
import json
import os
import re
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

FASTAPI_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]
DQ_UTILS_SRC = REPO_ROOT / "dq-utils" / "src"
CURRENT_OPENAPI_OUTPUT = FASTAPI_ROOT / "contracts" / "current" / "openapi-fastapi-v1.json"

if str(FASTAPI_ROOT) not in sys.path:
    sys.path.insert(0, str(FASTAPI_ROOT))
if DQ_UTILS_SRC.exists() and str(DQ_UTILS_SRC) not in sys.path:
    sys.path.insert(0, str(DQ_UTILS_SRC))

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
COMPONENT_REF_PREFIX = "#/components/"
SCHEMA_REF_PREFIX = "#/components/schemas/"
AGGREGATE_GROUP = "aggregate"


def _prepare_fastapi_contract_env() -> None:
    os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
    os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "")


def _load_openapi_from_app() -> dict[str, Any]:
    _prepare_fastapi_contract_env()
    from app.main import app

    return app.openapi()


def _load_openapi_from_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _sanitize_name(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return sanitized or "anonymous"


def _path_version(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "unversioned"

    if parts[0] == "api":
        parts = parts[1:]
        if not parts:
            return "unversioned"

    if re.fullmatch(r"v\d+", parts[0]):
        return parts[0]

    if len(parts) >= 2 and re.fullmatch(r"v\d+", parts[1]):
        return parts[1]

    return "unversioned"


def _collect_component_refs(node: Any, refs: set[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        ref_value = node.get("$ref")
        if isinstance(ref_value, str) and ref_value.startswith(COMPONENT_REF_PREFIX):
            parts = ref_value[len(COMPONENT_REF_PREFIX) :].split("/")
            if len(parts) == 2 and all(parts):
                refs.add((parts[0], parts[1]))

        for value in node.values():
            _collect_component_refs(value, refs)
        return

    if isinstance(node, list):
        for item in node:
            _collect_component_refs(item, refs)


def _resolve_referenced_components(
    spec: dict[str, Any],
    initial_refs: set[tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    resolved: dict[str, dict[str, Any]] = defaultdict(dict)
    queue = list(initial_refs)
    seen: set[tuple[str, str]] = set()

    while queue:
        component_type, component_name = queue.pop()
        key = (component_type, component_name)
        if key in seen:
            continue
        seen.add(key)

        component_group = spec.get("components", {}).get(component_type, {})
        component_value = component_group.get(component_name)
        if component_value is None:
            continue

        resolved[component_type][component_name] = deepcopy(component_value)

        nested_refs: set[tuple[str, str]] = set()
        _collect_component_refs(component_value, nested_refs)
        for nested_ref in nested_refs:
            if nested_ref not in seen:
                queue.append(nested_ref)

    return {component_type: dict(sorted(values.items())) for component_type, values in sorted(resolved.items())}


def _rewrite_schema_refs(node: Any) -> Any:
    if isinstance(node, dict):
        rewritten: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith(SCHEMA_REF_PREFIX):
                rewritten[key] = f"#/$defs/{value[len(SCHEMA_REF_PREFIX):]}"
            else:
                rewritten[key] = _rewrite_schema_refs(value)
        return rewritten

    if isinstance(node, list):
        return [_rewrite_schema_refs(item) for item in node]

    return node


def _content_schema_refs(
    content: dict[str, Any],
    defs: dict[str, Any],
    base_name: str,
) -> dict[str, str]:
    refs: dict[str, str] = {}
    for media_type, media_spec in sorted(content.items()):
        schema = media_spec.get("schema")
        if not isinstance(schema, dict):
            continue

        if isinstance(schema.get("$ref"), str) and schema["$ref"].startswith(SCHEMA_REF_PREFIX):
            def_name = schema["$ref"][len(SCHEMA_REF_PREFIX) :]
        else:
            def_name = f"{base_name}_{_sanitize_name(media_type)}"
            defs[def_name] = _rewrite_schema_refs(deepcopy(schema))

        refs[media_type] = f"#/$defs/{def_name}"
    return refs


def _parameter_contracts(
    spec: dict[str, Any],
    parameters: list[Any],
    defs: dict[str, Any],
    operation_id: str,
) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []

    for index, raw_parameter in enumerate(parameters):
        parameter = raw_parameter
        if isinstance(raw_parameter, dict) and isinstance(raw_parameter.get("$ref"), str):
            ref = raw_parameter["$ref"]
            if ref.startswith("#/components/parameters/"):
                parameter_name = ref.split("/")[-1]
                parameter = spec.get("components", {}).get("parameters", {}).get(parameter_name, {})

        if not isinstance(parameter, dict):
            continue

        contract: dict[str, Any] = {
            "name": parameter.get("name", f"param_{index}"),
            "in": parameter.get("in", "unknown"),
            "required": bool(parameter.get("required", False)),
        }

        if "description" in parameter:
            contract["description"] = parameter["description"]
        if "style" in parameter:
            contract["style"] = parameter["style"]
        if "explode" in parameter:
            contract["explode"] = parameter["explode"]

        schema = parameter.get("schema")
        if isinstance(schema, dict):
            if isinstance(schema.get("$ref"), str) and schema["$ref"].startswith(SCHEMA_REF_PREFIX):
                def_name = schema["$ref"][len(SCHEMA_REF_PREFIX) :]
            else:
                def_name = (
                    f"{_sanitize_name(operation_id)}_param_"
                    f"{_sanitize_name(str(contract['in']))}_{_sanitize_name(str(contract['name']))}"
                )
                defs[def_name] = _rewrite_schema_refs(deepcopy(schema))
            contract["schema_ref"] = f"#/$defs/{def_name}"

        content = parameter.get("content")
        if isinstance(content, dict):
            base_name = (
                f"{_sanitize_name(operation_id)}_param_content_"
                f"{_sanitize_name(str(contract['in']))}_{_sanitize_name(str(contract['name']))}"
            )
            content_refs = _content_schema_refs(content, defs, base_name)
            if content_refs:
                contract["content"] = {media_type: {"schema_ref": ref} for media_type, ref in content_refs.items()}

        contracts.append(contract)

    return contracts


def _operation_id(method: str, path: str, operation: dict[str, Any]) -> str:
    explicit = operation.get("operationId")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return f"{method.lower()}_{_sanitize_name(path)}"


def _build_contract_payloads(
    spec: dict[str, Any],
    scope_group: str,
    scope_version: str,
    paths: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    initial_refs: set[tuple[str, str]] = set()
    for path_item in paths.values():
        _collect_component_refs(path_item, initial_refs)

    components = _resolve_referenced_components(spec, initial_refs)

    openapi_fragment: dict[str, Any] = {
        "openapi": spec.get("openapi", "3.1.0"),
        "info": {
            "title": spec.get("info", {}).get("title", "DQ API"),
            "version": spec.get("info", {}).get("version", "unknown"),
            "description": (
                f"Filtered OpenAPI fragment for API group '{scope_group}' ({scope_version})."
            ),
        },
        "paths": paths,
    }

    if components:
        openapi_fragment["components"] = components

    tags = [tag for tag in spec.get("tags", []) if isinstance(tag, dict)]
    used_tag_names = {
        tag_name
        for path_item in paths.values()
        for method, operation in path_item.items()
        if method.lower() in HTTP_METHODS and isinstance(operation, dict)
        for tag_name in operation.get("tags", [])
    }
    selected_tags = [tag for tag in tags if tag.get("name") in used_tag_names]
    if selected_tags:
        openapi_fragment["tags"] = selected_tags

    defs: dict[str, Any] = {}
    for component_name, component_schema in components.get("schemas", {}).items():
        defs[component_name] = _rewrite_schema_refs(deepcopy(component_schema))

    manifest_operations: list[dict[str, Any]] = []
    for path, path_item in sorted(paths.items()):
        path_parameters = path_item.get("parameters", []) if isinstance(path_item, dict) else []
        for method, operation in sorted(path_item.items()):
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            operation_id = _operation_id(method, path, operation)
            combined_parameters = list(path_parameters) + list(operation.get("parameters", []))

            operation_entry: dict[str, Any] = {
                "operation_id": operation_id,
                "method": method.upper(),
                "path": path,
                "tags": operation.get("tags", []),
            }
            if "summary" in operation:
                operation_entry["summary"] = operation["summary"]
            if "description" in operation:
                operation_entry["description"] = operation["description"]

            parameter_contracts = _parameter_contracts(spec, combined_parameters, defs, operation_id)
            if parameter_contracts:
                operation_entry["parameters"] = parameter_contracts

            request_body = operation.get("requestBody")
            if isinstance(request_body, dict) and isinstance(request_body.get("$ref"), str):
                ref = request_body["$ref"]
                if ref.startswith("#/components/requestBodies/"):
                    request_body_name = ref.split("/")[-1]
                    request_body = spec.get("components", {}).get("requestBodies", {}).get(request_body_name, {})

            if isinstance(request_body, dict) and isinstance(request_body.get("content"), dict):
                request_refs = _content_schema_refs(
                    request_body["content"],
                    defs,
                    f"{_sanitize_name(operation_id)}_request_body",
                )
                if request_refs:
                    operation_entry["request_body"] = {
                        "required": bool(request_body.get("required", False)),
                        "content": {
                            media_type: {"schema_ref": ref}
                            for media_type, ref in request_refs.items()
                        },
                    }

            responses: dict[str, Any] = {}
            for status_code, raw_response in sorted(operation.get("responses", {}).items()):
                response = raw_response
                if isinstance(raw_response, dict) and isinstance(raw_response.get("$ref"), str):
                    ref = raw_response["$ref"]
                    if ref.startswith("#/components/responses/"):
                        response_name = ref.split("/")[-1]
                        response = spec.get("components", {}).get("responses", {}).get(response_name, {})

                if not isinstance(response, dict):
                    continue

                response_entry: dict[str, Any] = {}
                if "description" in response:
                    response_entry["description"] = response["description"]

                content = response.get("content")
                if isinstance(content, dict):
                    response_refs = _content_schema_refs(
                        content,
                        defs,
                        f"{_sanitize_name(operation_id)}_response_{_sanitize_name(str(status_code))}",
                    )
                    if response_refs:
                        response_entry["content"] = {
                            media_type: {"schema_ref": ref}
                            for media_type, ref in response_refs.items()
                        }

                responses[str(status_code)] = response_entry

            if responses:
                operation_entry["responses"] = responses

            manifest_operations.append(operation_entry)

    schema_bundle = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://dq-made-easy/contracts/internal-api/{scope_group}/{scope_version}/schema.json",
        "title": f"DQ API {scope_group} {scope_version} schema bundle",
        "$comment": "Use the definitions in $defs together with operations.json to resolve request, response, and parameter contracts.",
        "$defs": dict(sorted(defs.items())),
    }

    operations_manifest = {
        "group": scope_group,
        "version": scope_version,
        "source": {
            "openapi": spec.get("openapi", "3.1.0"),
            "title": spec.get("info", {}).get("title", "DQ API"),
            "version": spec.get("info", {}).get("version", "unknown"),
        },
        "operations": manifest_operations,
    }

    return openapi_fragment, schema_bundle, operations_manifest


def export_contracts(spec: dict[str, Any], output_root: Path) -> dict[str, Any]:
    grouped_paths: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    grouped_paths_by_tag: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)

    for path, path_item in sorted(spec.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue

        version = _path_version(path)
        grouped_paths[(AGGREGATE_GROUP, version)][path] = deepcopy(path_item)

        path_level_parameters = deepcopy(path_item.get("parameters", []))
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            tags = operation.get("tags") or ["untagged"]
            for tag in tags:
                tag_key = (f"by-tag/{tag}", version)
                tag_path_item = grouped_paths_by_tag[tag_key].setdefault(path, {})
                if path_level_parameters and "parameters" not in tag_path_item:
                    tag_path_item["parameters"] = deepcopy(path_level_parameters)
                tag_path_item[method] = deepcopy(operation)

    grouped_paths.update(grouped_paths_by_tag)

    index_entries: list[dict[str, Any]] = []
    for (group, version), paths in sorted(grouped_paths.items()):
        fragment, schema_bundle, operations_manifest = _build_contract_payloads(spec, group, version, paths)
        contract_dir = output_root / group / version
        _write_json(contract_dir / "openapi.json", fragment)
        _write_json(contract_dir / "schema.json", schema_bundle)
        _write_json(contract_dir / "operations.json", operations_manifest)

        index_entries.append(
            {
                "kind": "tag" if group.startswith("by-tag/") else "aggregate",
                "group": group,
                "version": version,
                "path_count": len(paths),
                "operation_count": len(operations_manifest["operations"]),
                "files": {
                    "schema": str(Path(group) / version / "schema.json"),
                    "operations": str(Path(group) / version / "operations.json"),
                    "openapi": str(Path(group) / version / "openapi.json"),
                },
            }
        )

    index_payload = {
        "source": {
            "openapi": spec.get("openapi", "3.1.0"),
            "title": spec.get("info", {}).get("title", "DQ API"),
            "version": spec.get("info", {}).get("version", "unknown"),
        },
        "contracts": index_entries,
    }
    _write_json(output_root / "index.json", index_payload)
    return index_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export versioned JSON Schema API contract bundles into docs/contracts/internal-api."
    )
    parser.add_argument(
        "--source",
        choices=["app", "file"],
        default="app",
        help="Use the FastAPI app or an OpenAPI JSON file as the source spec.",
    )
    parser.add_argument(
        "--file",
        default=str(FASTAPI_ROOT / "contracts" / "current" / "openapi-fastapi-v1.json"),
        help="OpenAPI JSON file when --source file.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "docs" / "contracts" / "internal-api"),
        help="Output directory for generated contract bundles.",
    )
    parser.add_argument(
        "--current-openapi-output",
        default=str(CURRENT_OPENAPI_OUTPUT),
        help="Path to refresh the checked-in current FastAPI OpenAPI JSON when --source app.",
    )
    args = parser.parse_args()

    if args.source == "file":
        spec = _load_openapi_from_file(Path(args.file))
    else:
        spec = _load_openapi_from_app()
        _write_json(Path(args.current_openapi_output), spec)

    output_root = Path(args.output)
    index_payload = export_contracts(spec, output_root)

    print(f"Exported {len(index_payload['contracts'])} contract bundle(s) to: {output_root}")
    for contract in index_payload["contracts"]:
        print(
            f"- {contract['group']}/{contract['version']}: "
            f"{contract['operation_count']} operation(s), {contract['path_count']} path(s)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())