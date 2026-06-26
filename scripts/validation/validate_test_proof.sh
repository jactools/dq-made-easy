#!/usr/bin/env bash
set -euo pipefail

# validate: groups=repo
# Purpose: Validate committed test proof JSON against the canonical schema.
# What it does:
# - Fails if proof artifacts are not organized by app version and proof type
# - Validates each proof JSON file against docs/contracts/test-proof/v1/schema.json
# - Fails fast when a proof file is missing required fields or has invalid values
# Version: 1.2
# Last modified: 2026-05-27

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
proof_root="$repo_root/test-results/test-proof"
schema_path="$repo_root/docs/contracts/test-proof/v1/schema.json"
python_runner="$repo_root/scripts/python_arm64.sh"
python_bin="$repo_root/venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  echo "Expected repository virtualenv at $python_bin" >&2
  exit 1
fi

"$python_runner" --python-bin "$python_bin" - "$repo_root" "$proof_root" "$schema_path" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

repo_root = Path(sys.argv[1])
proof_root = Path(sys.argv[2])
schema_path = Path(sys.argv[3])


def is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_date_time(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate(instance: Any, schema: dict[str, Any], location: str = "<root>") -> list[str]:
    errors: list[str] = []

    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(instance, dict):
            return [f"{location}: expected object, got {type(instance).__name__}"]

        properties = schema.get("properties", {})
        required = schema.get("required", [])
        additional_properties = schema.get("additionalProperties", True)

        for key in required:
            if key not in instance:
                errors.append(f"{location}: missing required property '{key}'")

        for key, value in instance.items():
            if key in properties:
                errors.extend(validate(value, properties[key], f"{location}.{key}" if location != "<root>" else key))
                continue
            if additional_properties is False:
                errors.append(f"{location}: unexpected property '{key}'")
        return errors

    if schema_type == "array":
        if not isinstance(instance, list):
            return [f"{location}: expected array, got {type(instance).__name__}"]

        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(instance) < min_items:
            errors.append(f"{location}: expected at least {min_items} item(s), found {len(instance)}")

        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                item_location = f"{location}[{index}]"
                errors.extend(validate(item, item_schema, item_location))
        return errors

    if schema_type == "string":
        if not isinstance(instance, str):
            return [f"{location}: expected string, got {type(instance).__name__}"]

        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(instance) < min_length:
            errors.append(f"{location}: expected string length at least {min_length}, found {len(instance)}")

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and instance not in enum_values:
            errors.append(f"{location}: value {instance!r} is not one of {enum_values!r}")

        if schema.get("format") == "date-time" and not is_date_time(instance):
            errors.append(f"{location}: value {instance!r} is not a valid RFC 3339 date-time")

        return errors

    if schema_type == "integer":
        if not is_integer(instance):
            return [f"{location}: expected integer, got {type(instance).__name__}"]

        minimum = schema.get("minimum")
        if isinstance(minimum, int) and instance < minimum:
            errors.append(f"{location}: expected integer >= {minimum}, found {instance}")
        return errors

    if schema_type == "boolean":
        if not isinstance(instance, bool):
            return [f"{location}: expected boolean, got {type(instance).__name__}"]
        return errors

    if schema_type == "number":
        if not isinstance(instance, (int, float)) or isinstance(instance, bool):
            return [f"{location}: expected number, got {type(instance).__name__}"]

        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and instance < minimum:
            errors.append(f"{location}: expected number >= {minimum}, found {instance}")

        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and instance > maximum:
            errors.append(f"{location}: expected number <= {maximum}, found {instance}")

        return errors

    if "anyOf" in schema:
        option_errors = []
        for option in schema["anyOf"]:
            if not validate(instance, option, location):
                return []
            option_errors.append(validate(instance, option, location))
        errors.append(f"{location}: value does not match any allowed schema variant")
        for index, variant_errors in enumerate(option_errors, start=1):
            errors.extend([f"{location} (variant {index}): {message}" for message in variant_errors])
        return errors

    return errors


schema = json.loads(schema_path.read_text(encoding="utf-8"))
if schema.get("type") != "object":
    raise SystemExit(f"Unsupported proof schema root type: {schema.get('type')!r}")

errors: list[str] = []

for entry in sorted(proof_root.iterdir()):
    if entry.name in {"README.md", "rules"}:
        continue

    if not entry.is_dir():
        if entry.suffix.lower() == ".json":
            errors.append(
                f"Top-level proof artifacts must live under an app version directory: {entry.relative_to(repo_root).as_posix()}"
            )
        continue

    app_version = entry.name
    for path in sorted(entry.rglob("*")):
        if path.is_dir():
            continue

        if path.name == "README.md":
            continue

        relative_path = path.relative_to(repo_root).as_posix()

        if path.suffix.lower() != ".json":
            errors.append(f"Non-JSON proof artifact: {relative_path}")
            continue

        try:
            instance = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON in {relative_path}: {exc.msg}")
            continue

        if path.parent.parent.name != app_version:
            errors.append(f"{relative_path}: proof files must be nested under test-results/test-proof/<app_version>/<proof_type>/")
            continue

        if instance.get("app_version") != app_version:
            errors.append(f"{relative_path}: app_version must match the version directory name {app_version!r}")
            continue

        if path.parent.name != instance.get("proof_type"):
            errors.append(f"{relative_path}: proof_type must match the proof_type directory name {path.parent.name!r}")
            continue

        errors.extend(f"{relative_path}: {message}" for message in validate(instance, schema))

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    raise SystemExit(1)
PY