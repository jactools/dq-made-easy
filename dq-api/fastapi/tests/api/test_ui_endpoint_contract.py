from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.main import app

pytestmark = pytest.mark.usefixtures("clone_payload")


def _normalize_path_params(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{param}", path)


def _fastapi_route_set() -> set[str]:
    routes: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            routes.add(_normalize_path_params(path))
    return routes


def _ui_validate_calls() -> list[str]:
    repo_root = Path(__file__).resolve().parents[4]
    ui_src = repo_root / "dq-ui" / "src"

    # Match template-literal fetch calls that use apiBase and target /rules/{id}/validate,
    # excluding /validate/enriched (separate, optional flow).
    pattern = re.compile(
        r"fetch\(\s*`[^`]*\$\{[A-Za-z_][A-Za-z0-9_]*\}/rules/\$\{[^}]+\}/validate(?!/enriched)[^`]*`",
        re.MULTILINE,
    )

    matches: list[str] = []
    for file_path in ui_src.rglob("*.ts"):
        content = file_path.read_text(encoding="utf-8")
        if pattern.search(content):
            matches.append(str(file_path.relative_to(repo_root)))
    for file_path in ui_src.rglob("*.tsx"):
        content = file_path.read_text(encoding="utf-8")
        if pattern.search(content):
            matches.append(str(file_path.relative_to(repo_root)))

    return sorted(set(matches))


def test_ui_validate_rule_calls_have_fastapi_route() -> None:
    ui_call_files = _ui_validate_calls()
    assert ui_call_files, "No UI /rules/{id}/validate fetch call found; contract guard is misconfigured"

    routes = _fastapi_route_set()
    expected = "/rulebuilder/v1/rules/{param}/validate"

    assert expected in routes, (
        "UI calls /rules/{id}/validate but FastAPI route is missing. "
        f"UI call files: {ui_call_files}"
    )
