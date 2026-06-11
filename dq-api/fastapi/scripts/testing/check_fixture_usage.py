from __future__ import annotations

import ast
import sys
from pathlib import Path

_INLINE_PAYLOAD_KEYS = {"json", "body", "payload", "join_definition", "joinDefinition"}
_INLINE_PAYLOAD_POLICY_PREFIXES = ("tests/application/services/",)


def _is_orm_related(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    return any("orm" in part for part in parts)


def _module_uses_usefixtures(module: ast.Module) -> bool:
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "pytestmark":
                value = ast.unparse(node.value)
                if "usefixtures" in value:
                    return True
    return False


def _has_fixture_declaration(module: ast.Module) -> bool:
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            text = ast.unparse(decorator)
            if text.startswith("pytest.fixture") or ".fixture" in text:
                return True
    return False


def _has_fixture_params_in_tests(module: ast.Module) -> bool:
    for node in ast.walk(module):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        if node.args.args:
            return True
    return False


def _uses_inline_payload_policy(path: Path, repo_root: Path) -> bool:
    relative = path.relative_to(repo_root).as_posix()
    return any(relative.startswith(prefix) for prefix in _INLINE_PAYLOAD_POLICY_PREFIXES)


def _is_complex_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Dict):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        if any(isinstance(element, (ast.Dict, ast.List, ast.Tuple, ast.Set)) for element in node.elts):
            return True
        return len(node.elts) >= 3
    return False


def _find_inline_payload_violations(module: ast.Module) -> list[int]:
    violations: list[int] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg not in _INLINE_PAYLOAD_KEYS:
                continue
            if _is_complex_literal(keyword.value):
                violations.append(node.lineno)
    return sorted(set(violations))


def check_file(path: Path, repo_root: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    violations: list[str] = []

    if _module_uses_usefixtures(module):
        pass
    elif _has_fixture_declaration(module):
        pass
    elif _has_fixture_params_in_tests(module):
        pass
    else:
        violations.append("missing-fixture-usage")

    if _uses_inline_payload_policy(path, repo_root):
        inline_literal_lines = _find_inline_payload_violations(module)
        for line in inline_literal_lines:
            violations.append(f"inline-complex-payload-literal@L{line}")

    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    tests_root = repo_root / "tests"
    files = sorted(tests_root.rglob("test_*.py"))

    violations: list[tuple[Path, list[str]]] = []
    for file_path in files:
        if _is_orm_related(file_path):
            continue
        file_violations = check_file(file_path, repo_root)
        if file_violations:
            violations.append((file_path.relative_to(repo_root), file_violations))

    if not violations:
        print("Fixture usage check passed for non-ORM tests.")
        return 0

    print("Fixture usage check failed. Non-ORM test policy violations:")
    for violation_path, violation_codes in violations:
        print(f"- {violation_path.as_posix()} ({', '.join(violation_codes)})")
    print(
        "\nAdd fixture parameters, @pytest.mark.usefixtures(...), fixture declarations, "
        "and move complex inline payload literals into fixtures for application service tests."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
