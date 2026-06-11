from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COVERAGE_JSON = ROOT.parent / "test-results/coverage.json"
EXCLUDED_PARTS = {
    ".git",
    ".github",
    ".pytest_cache",
    ".vscode",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "test-results",
}


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def _if_lines(file_path: Path) -> list[int]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    return [node.lineno for node in ast.walk(tree) if isinstance(node, ast.If)]


def main() -> int:
    if not COVERAGE_JSON.exists():
        print(f"Coverage file not found: {COVERAGE_JSON}")
        return 1

    payload = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
    coverage_files: dict[str, dict[str, object]] = payload.get("files", {})

    rows: list[tuple[int, int, str]] = []
    for py_file in sorted(ROOT.rglob("*.py")):
        relative = py_file.relative_to(ROOT)
        if _is_excluded(relative):
            continue

        rel_path = relative.as_posix()
        file_cov = coverage_files.get(rel_path)
        if not file_cov:
            continue

        missing_branches = {tuple(item) for item in file_cov.get("missing_branches", [])}
        try:
            if_lines = _if_lines(py_file)
        except Exception:
            continue

        if not if_lines:
            continue

        missing_if = sum(
            1 for line in if_lines if any(from_line == line for from_line, _ in missing_branches)
        )
        if missing_if:
            rows.append((missing_if, len(if_lines), rel_path))

    rows.sort(reverse=True)
    print("TOP_UNCOVERED_IF_FILES")
    for missing_if, total_if, rel_path in rows[:40]:
        print(f"{missing_if:4d}/{total_if:4d} {rel_path}")

    print(f"TOTAL_FILES_WITH_MISSING_IF {len(rows)}")
    print(f"TOTAL_MISSING_IF {sum(row[0] for row in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
