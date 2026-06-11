from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest
from coverage import Coverage
from coverage import CoverageData


_EXCLUDED_DIR_NAMES = {
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


@dataclass(frozen=True)
class IfBranchGap:
    file_path: str
    line_number: int
    outgoing_arcs: tuple[int, ...]


@dataclass(frozen=True)
class IfBranchAudit:
    scanned_files: int
    total_if_statements: int
    gaps: tuple[IfBranchGap, ...]


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def _is_excluded(path: Path, repo_root: Path) -> bool:
    relative_parts = path.relative_to(repo_root).parts
    return any(part in _EXCLUDED_DIR_NAMES for part in relative_parts)


def _iter_python_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*.py"):
        if _is_excluded(path, repo_root):
            continue
        files.append(path)
    return sorted(files)


def _resolve_coverage_key(path: Path, project_root: Path, coverage_data: CoverageData) -> str | None:
    measured = coverage_data.measured_files()
    if not measured:
        return None

    candidates: list[str] = [
        str(path),
        path.as_posix(),
    ]
    try:
        candidates.append(path.relative_to(project_root).as_posix())
    except ValueError:
        pass

    for candidate in candidates:
        if candidate in measured:
            return candidate

    path_posix = path.as_posix()
    for measured_name in measured:
        if measured_name.endswith(path_posix):
            return measured_name

    try:
        rel = path.relative_to(project_root).as_posix()
    except ValueError:
        return None

    for measured_name in measured:
        if measured_name.endswith(rel):
            return measured_name

    return None


def _if_lines(path: Path) -> list[int]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return sorted(node.lineno for node in ast.walk(tree) if isinstance(node, ast.If))


def _collect_outgoing_arcs(arcs: list[tuple[int, int]] | None) -> dict[int, set[int]]:
    outgoing: dict[int, set[int]] = {}
    if not arcs:
        return outgoing

    for from_line, to_line in arcs:
        if from_line <= 0 or to_line <= 0:
            continue
        outgoing.setdefault(from_line, set()).add(to_line)
    return outgoing


@pytest.fixture(scope="session")
def if_statement_branch_audit() -> IfBranchAudit:
    current_cov = Coverage.current()
    if current_cov is None:
        pytest.skip("Coverage runtime is not active; run pytest with pytest-cov enabled")

    coverage_data = current_cov.get_data()
    repo_root = _find_repo_root(Path(__file__).resolve())
    project_root = Path(__file__).resolve().parents[2]

    files = _iter_python_files(project_root / "app")
    gaps: list[IfBranchGap] = []
    total_if_statements = 0

    for path in files:
        coverage_key = _resolve_coverage_key(path, project_root, coverage_data)
        if coverage_key is None:
            continue

        if_lines = _if_lines(path)
        if not if_lines:
            continue

        arcs = coverage_data.arcs(coverage_key)
        executed_lines = set(coverage_data.lines(coverage_key) or [])
        outgoing = _collect_outgoing_arcs(arcs)

        for line_number in if_lines:
            if line_number not in executed_lines:
                continue

            total_if_statements += 1
            destinations = outgoing.get(line_number, set())
            if len(destinations) >= 2:
                continue
            gaps.append(
                IfBranchGap(
                    file_path=str(path.relative_to(project_root)),
                    line_number=line_number,
                    outgoing_arcs=tuple(sorted(destinations)),
                )
            )

    return IfBranchAudit(
        scanned_files=len(files),
        total_if_statements=total_if_statements,
        gaps=tuple(gaps),
    )
