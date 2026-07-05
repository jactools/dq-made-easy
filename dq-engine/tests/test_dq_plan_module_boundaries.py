"""Module boundary tests — enforce the dependency architecture.

These tests scan import statements to ensure no upward or cross-layer
imports slip in.  They catch regressions before they break the module
split.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENGINE_DIR = Path(__file__).resolve().parent.parent


def _collect_imports(path: Path) -> set[str]:
    """Return the set of top-level module names imported by *path*."""
    with path.open() as fh:
        tree = ast.parse(fh.read(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def _module_files(pattern: str) -> list[Path]:
    """Return .py files matching *pattern* inside dq-engine/."""
    return sorted(_ENGINE_DIR.glob(pattern))


# ---------------------------------------------------------------------------
# Test fixtures — the modules we care about
# ---------------------------------------------------------------------------


@pytest.fixture
def gx_dispatch_modules() -> list[Path]:
    return _module_files("gx_dispatch_*.py")


@pytest.fixture
def dq_plan_execution_modules() -> list[Path]:
    return _module_files("dq_plan_execution*.py")


@pytest.fixture
def dq_plan_lowerers_modules() -> list[Path]:
    return _module_files("dq_plan_lowerers*.py")


# ---------------------------------------------------------------------------
# 1. gx_dispatch modules must not import legacy execution modules
# ---------------------------------------------------------------------------


class TestGxDispatchBoundary:
    """gx_dispatch modules may only import from:
    - dq_plan_* modules
    - gx_dispatch_* siblings
    - standard library / third-party packages
    """

    FORBIDDEN_LEGACY = {"execution_dispatch", "runtime_lowerers", "execution_contract"}

    def test_no_legacy_imports(self, gx_dispatch_modules: list[Path]) -> None:
        for mod_path in gx_dispatch_modules:
            imports = _collect_imports(mod_path)
            # Skip test files themselves
            if mod_path.name.startswith("test_"):
                continue
            violations = imports & self.FORBIDDEN_LEGACY
            assert not violations, (
                f"{mod_path.name} imports legacy modules: {violations}"
            )


# ---------------------------------------------------------------------------
# 2. dq_plan_execution modules must not import gx_dispatch modules
#    (enforce one-way dependency: execution → gx_dispatch, not reverse)
# ---------------------------------------------------------------------------


class TestDqPlanExecutionBoundary:
    """dq_plan_execution* must never import gx_dispatch*."""

    def test_no_gx_imports(self, dq_plan_execution_modules: list[Path]) -> None:
        for mod_path in dq_plan_execution_modules:
            if mod_path.name.startswith("test_"):
                continue
            imports = _collect_imports(mod_path)
            gx_imports = {
                name for name in imports if name.startswith("gx_dispatch")
            }
            assert not gx_imports, (
                f"{mod_path.name} imports gx_dispatch modules: {gx_imports}"
            )


# ---------------------------------------------------------------------------
# 3. dq_plan_lowerers per-engine modules must not import each other
#    (no cross-engine coupling — each engine stays independent)
# ---------------------------------------------------------------------------


class TestDqPlanLowerersBoundary:
    """Per-engine lowerers must not import from each other."""

    _PER_ENGINE = {
        "dq_plan_lowerers_gx": "dq_plan_lowerers_gx.py",
        "dq_plan_lowerers_trino": "dq_plan_lowerers_trino.py",
        "dq_plan_lowerers_soda": "dq_plan_lowerers_soda.py",
    }

    def test_no_cross_engine_imports(self) -> None:
        for engine_name, engine_file in self._PER_ENGINE.items():
            mod_path = _ENGINE_DIR / engine_file
            if not mod_path.exists():
                continue
            imports = _collect_imports(mod_path)
            other_names = {n for n, _ in self._PER_ENGINE.items() if n != engine_name}
            cross_imports = imports & other_names
            assert not cross_imports, (
                f"{engine_file} imports other engine modules: {cross_imports}"
            )

    # The registry (dq_plan_lowerers.py) MAY import from per-engine modules
    # (that's the whole point), but it must not import from gx_dispatch.

    def test_registry_no_gx_imports(self) -> None:
        mod_path = _ENGINE_DIR / "dq_plan_lowerers.py"
        if not mod_path.exists():
            pytest.skip("dq_plan_lowerers.py not found")
        imports = _collect_imports(mod_path)
        gx_imports = {
            name for name in imports if name.startswith("gx_dispatch")
        }
        assert not gx_imports, (
            f"dq_plan_lowerers.py imports gx_dispatch modules: {gx_imports}"
        )


# ---------------------------------------------------------------------------
# 4. Legacy modules should not exist (Phase 7 cleanup)
# ---------------------------------------------------------------------------


class TestLegacyModulesRemoved:
    """Verify that legacy modules have been fully removed."""

    def test_execution_dispatch_removed(self) -> None:
        assert not (_ENGINE_DIR / "execution_dispatch.py").exists(), (
            "execution_dispatch.py still exists — should have been removed in Phase 7"
        )

    def test_runtime_lowerers_removed(self) -> None:
        assert not (_ENGINE_DIR / "runtime_lowerers.py").exists(), (
            "runtime_lowerers.py still exists — should have been removed in Phase 7"
        )

    def test_execution_contract_removed(self) -> None:
        assert not (_ENGINE_DIR / "execution_contract.py").exists(), (
            "execution_contract.py still exists — should have been removed in Phase 7"
        )


# ---------------------------------------------------------------------------
# 5. New modules must exist
# ---------------------------------------------------------------------------


class TestNewModulesExist:
    """Verify all expected new modules are present."""

    EXPECTED_EXECUTION = [
        "dq_plan_execution.py",
        "dq_plan_execution_types.py",
        "dq_plan_execution_payload.py",
        "dq_plan_execution_api.py",
        "dq_plan_execution_orchestrator.py",
        "dq_plan_execution_contract.py",
        "dq_plan_execution_report.py",
        "dq_plan_execution_persistence.py",
        "dq_plan_execution_streaming.py",
    ]

    EXPECTED_LOWERERS = [
        "dq_plan_lowerers.py",
        "dq_plan_lowerers_gx.py",
        "dq_plan_lowerers_trino.py",
        "dq_plan_lowerers_soda.py",
    ]

    def test_execution_modules_exist(self) -> None:
        for name in self.EXPECTED_EXECUTION:
            assert (_ENGINE_DIR / name).exists(), f"{name} is missing"

    def test_lowerers_modules_exist(self) -> None:
        for name in self.EXPECTED_LOWERERS:
            assert (_ENGINE_DIR / name).exists(), f"{name} is missing"
