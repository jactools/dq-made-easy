#!/usr/bin/env python3
"""Enforce snake_case in all API payloads and schemas.

Checks:
  1. No Pydantic Field(alias="camelCase") in API schema files
  2. No camelCase keys in JSON test fixtures under tests/fixtures/api/
  3. No camelCase keys in JSON scenario spec files under tools/demo/deliveries-*.json

Run:
    python scripts/validate_snake_case.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Pattern that matches camelCase (lowercase followed by uppercase)
CAMELCASE_RE = re.compile(r"[a-z][A-Z]")

# Directories to scan for JSON fixtures/specs
REPO_ROOT = Path(__file__).resolve().parent.parent


def find_json_files(directory: Path, pattern: str) -> list[Path]:
    """Find JSON files matching a glob pattern."""
    return sorted(directory.glob(pattern))


def check_json_file(path: Path) -> list[str]:
    """Check a JSON file for camelCase keys. Returns list of violations."""
    violations: list[str] = []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return violations

    # Flatten the JSON to find all keys
    keys = _collect_keys(data)
    for key in keys:
        if CAMELCASE_RE.search(key):
            violations.append(f"  {path.relative_to(REPO_ROOT)}: '{key}' (should be '{_to_snake(key)}')")
    return violations


def _collect_keys(obj: object) -> list[str]:
    """Recursively collect all keys from a nested dict/list structure."""
    keys: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_collect_keys(v))
    elif isinstance(obj, list):
        for item in obj:
            keys.extend(_collect_keys(item))
    return keys


def _to_snake(name: str) -> str:
    """Convert camelCase to snake_case for suggestion."""
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s1).lower()


def check_pydantic_aliases() -> list[str]:
    """Check Pydantic models for Field(alias="camelCase") patterns."""
    violations: list[str] = []
    for py_file in REPO_ROOT.glob("packages/**/*.py"):
        if "__pycache__" in str(py_file) or "build/" in str(py_file):
            continue
        content = py_file.read_text()

        # Match Field(alias="camelCase") patterns
        for match in re.finditer(r'Field\(.*?alias\s*=\s*"([^"]+)"', content):
            alias = match.group(1)
            if CAMELCASE_RE.search(alias):
                # Find the line number
                line_no = content[:match.start()].count("\n") + 1
                violations.append(
                    f"  {py_file.relative_to(REPO_ROOT)}:{line_no}: "
                    f'Field(alias="{alias}") — remove alias, use snake_case directly'
                )

        # Also warn about populate_by_name used for camelCase compatibility
        if "populate_by_name=True" in content and "camel" not in content.lower():
            for match in re.finditer(r'Field\(.*?alias\s*=\s*', content):
                pass  # Only flag if there are actual camelCase aliases

    return violations


def main() -> int:
    violations: list[str] = []

    # 1. Check Pydantic aliases in schema files
    print("Checking Pydantic aliases in packages/...")
    alias_violations = check_pydantic_aliases()
    violations.extend(alias_violations)

    # 2. Check JSON test fixtures
    print("Checking JSON test fixtures...")
    for json_file in (
        find_json_files(REPO_ROOT / "tests/fixtures", "**/*.json")
    ):
        violations.extend(check_json_file(json_file))

    # 3. Check scenario spec files
    print("Checking scenario spec files...")
    for json_file in find_json_files(REPO_ROOT / "tools/demo", "deliveries-*.json"):
        violations.extend(check_json_file(json_file))

    # 4. Check scenario YAML files for camelCase in step body keys
    print("Checking scenario YAML files...")
    try:
        import yaml
        for yml_file in sorted(REPO_ROOT.glob("tools/demo/scenarios/*.yml")):
            data = yaml.safe_load(yml_file.read_text())
            for step in data.get("steps", []):
                body = step.get("body")
                if isinstance(body, dict):
                    for key in body:
                        if CAMELCASE_RE.search(key):
                            violations.append(
                                f"  {yml_file.relative_to(REPO_ROOT)}: "
                                f"step '{step.get('name', '?')}' body key '{key}' (should be '{_to_snake(key)}')"
                            )
    except ImportError:
        pass  # yaml not available

    # 5. Check Python enum values are ALL_CAPS
    print("Checking enum values are ALL_CAPS...")
    for py_file in REPO_ROOT.glob("packages/**/*.py"):
        if "__pycache__" in str(py_file) or "build/" in str(py_file):
            continue
        content = py_file.read_text()

        # Match class definitions that inherit from Enum
        import ast
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check if this class inherits from Enum
                inherits_enum = False
                for base in node.bases:
                    base_name = getattr(base, 'id', None) or getattr(base, 'attr', None) or ''
                    if 'Enum' in base_name:
                        inherits_enum = True
                        break

                if not inherits_enum:
                    continue

                # Check each member's value
                class_name = node.name
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                member_name = target.id
                                # Skip dunder methods and private attrs
                                if member_name.startswith('_'):
                                    continue
                                # The value should be ALL_CAPS if it's a string constant
                                if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                                    val = item.value.value
                                    if val != val.upper():
                                        line_no = item.lineno
                                        violations.append(
                                            f"  {py_file.relative_to(REPO_ROOT)}:{line_no}: "
                                            f"{class_name}.{member_name} = '{val}' (should be '{val.upper()}')"
                                        )
                    elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        member_name = item.target.id
                        if member_name.startswith('_'):
                            continue
                        if item.value and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                            val = item.value.value
                            if val != val.upper():
                                line_no = item.lineno
                                violations.append(
                                    f"  {py_file.relative_to(REPO_ROOT)}:{line_no}: "
                                    f"{class_name}.{member_name} = '{val}' (should be '{val.upper()}')"
                                )

    # Report
    if violations:
        print(f"\n✗ Found {len(violations)} camelCase violation(s):\n")
        for v in violations:
            print(v)
        print("\nFix: Use snake_case in all API payloads, schemas, and fixtures.")
        return 1
    else:
        print("\n✓ All API payloads use snake_case — no violations found.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
