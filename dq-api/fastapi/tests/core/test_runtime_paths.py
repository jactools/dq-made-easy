from __future__ import annotations

from pathlib import Path

import pytest

from app.core.runtime_paths import find_runtime_root


@pytest.fixture
def container_style_runtime_root(tmp_path: Path) -> Path:
    runtime_root = tmp_path / "runtime"
    (runtime_root / "app").mkdir(parents=True)
    (runtime_root / "docs" / "contracts" / "internal-api").mkdir(parents=True)
    (runtime_root / "docs" / "contracts" / "internal-api" / "index.json").write_text("{}", encoding="utf-8")
    (runtime_root / "data_sources" / "contracts").mkdir(parents=True)
    return runtime_root


def test_find_runtime_root_resolves_container_style_main_path(container_style_runtime_root: Path) -> None:
    main_path = container_style_runtime_root / "app" / "main.py"
    main_path.write_text("# test\n", encoding="utf-8")

    resolved = find_runtime_root(main_path, Path("docs") / "contracts" / "internal-api" / "index.json")

    assert resolved == container_style_runtime_root


def test_find_runtime_root_resolves_container_style_endpoint_path(container_style_runtime_root: Path) -> None:
    endpoint_path = container_style_runtime_root / "app" / "api" / "v1" / "endpoints" / "data_contracts.py"
    endpoint_path.parent.mkdir(parents=True)
    endpoint_path.write_text("# test\n", encoding="utf-8")

    resolved = find_runtime_root(endpoint_path, Path("data_sources") / "contracts")

    assert resolved == container_style_runtime_root


def test_find_runtime_root_fails_fast_when_required_assets_are_missing(tmp_path: Path) -> None:
    start_path = tmp_path / "app" / "main.py"
    start_path.parent.mkdir(parents=True)
    start_path.write_text("# test\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Required runtime asset path"):
        find_runtime_root(start_path, Path("docs") / "contracts" / "internal-api" / "index.json")


def test_find_runtime_root_accepts_string_paths(container_style_runtime_root: Path) -> None:
    endpoint_path = container_style_runtime_root / "app" / "api" / "v1" / "endpoints" / "runtime.py"
    endpoint_path.parent.mkdir(parents=True)
    endpoint_path.write_text("# test\n", encoding="utf-8")

    resolved = find_runtime_root(str(endpoint_path), "docs/contracts/internal-api/index.json")

    assert resolved == container_style_runtime_root