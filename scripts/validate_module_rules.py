#!/usr/bin/env python3
"""Validate that Python modules follow repository rules.

Rules:
    1. Modules must have less than 1000 lines of code.
    2. Modules must adhere to the Single Responsibility Principle (SRP).
       - Each module should focus on one responsibility.
       - Mixing unrelated concerns (e.g., entities + services + persistence) is a violation.
       - Related classes (e.g., request/response pairs, enum groups, error hierarchies) are OK.

Usage:
    python scripts/validate_module_rules.py [paths...]

If no paths are given, scans all packages/.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

MAX_LINES = 1000

# Default scan targets — supports both DDD packages/ and legacy layout
DEFAULT_PACKAGES = Path("packages")
DEFAULT_SCAN_DIRS = [
    # Legacy dq-made-easy source directories
    "dq-api/fastapi/app",
    "dq-engine",
    "dq-utils/src",
    "dq-profiling/python",
]

# Directories to skip
SKIP_DIRS = {"__pycache__", "build", "dist", ".venv", "venv", "node_modules", ".git"}


def count_lines(path: Path) -> int:
    """Count non-empty, non-comment lines in a Python file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    count = 0
    in_docstring = False
    docstring_char = None
    for line in lines:
        stripped = line.strip()
        # Track triple-quoted docstrings
        if in_docstring:
            if docstring_char in stripped and stripped.endswith(docstring_char):
                in_docstring = False
            continue

        # Start of a docstring?
        if stripped.startswith('"""') or stripped.startswith("'''"):
            docstring_char = stripped[:3]
            # Single-line docstring?
            if stripped.count(docstring_char) >= 2 and len(stripped) > 3:
                continue
            in_docstring = True
            continue

        # Skip blank lines and comments
        if not stripped or stripped.startswith("#"):
            continue
        count += 1
    return count


def _is_proxy_route_module(source: str, tree: ast.Module) -> bool:
    """Detect proxy route modules.

    A proxy route module is a FastAPI route file where every async function
    is a route handler that forwards requests to a backend service.
    Detection criteria:
    1. Imports APIRouter and creates a router instance
    2. Imports proxy helpers or uses HTTP client (aiohttp, httpx, proxy_get, etc.)
    3. No domain logic classes (no Service, Repository, Store, etc.)

    When detected, all route functions in the file share one concern:
    proxying to ONE backend service. Name heuristics (get_/create_/list_)
    describe the *proxied operation*, not a different BFF concern.
    """
    # Criterion 1: APIRouter usage
    if "APIRouter" not in source or "router" not in source:
        return False

    # Criterion 2: proxy helpers or HTTP client imports
    # Pure proxy: imports helper functions (proxy_get, proxy_post, etc.)
    # Aggregation: uses aiohttp/httpx directly to fetch from multiple backends
    # Both count as proxy route modules since every function is an HTTP boundary.
    proxy_indicators = (
        "proxy_get", "proxy_post", "proxy_patch", "proxy_delete",
        "aiohttp", "httpx", "proxy.py", "extern.proxy",
        "control_plane_headers", "central_repo_headers", "orchestrator_headers",
    )
    if not any(ind in source for ind in proxy_indicators):
        return False

    # Criterion 3: no domain logic classes
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            return False  # has a non-private class → not a pure proxy route file

    return True


def _classify_node(node: ast.AST, is_proxy_route: bool = False) -> str | None:
    """Classify a top-level AST node into a concern category."""
    if isinstance(node, ast.ClassDef):
        # Skip private helpers
        if node.name.startswith("_"):
            return None
        name = node.name
        # Enums and pure dataclasses
        bases = [b.attr if isinstance(b, ast.Attribute) else b.id if isinstance(b, ast.Name) else "" for b in node.bases]
        if "Enum" in bases or "str" in bases or "int" in bases:
            return "enum"
        # Pydantic models / schemas
        if "BaseModel" in bases:
            return "model"
        # ORM models
        if "Base" in bases:
            return "orm"
        # Error classes
        if name.endswith("Error") or name.endswith("Exception"):
            return "error"
        # Request/response classes
        if any(suffix in name for suffix in ("Request", "Response", "Schema", "Payload")):
            return "schema"
        # Service classes
        if "Service" in name or "Coordinator" in name or "Distributor" in name or "Concentrator" in name:
            return "service"
        # Repository classes
        if "Repository" in name or "Store" in name or "Queue" in name:
            return "repository"
        # Domain entities
        return "entity"
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name.startswith("_") or node.name == "main":
            return None
        # Proxy route modules: all functions are proxy functions, regardless of name.
        # The name (get_delivery, create_policy, list_scenarios) describes the
        # proxied backend operation, not a different BFF concern.
        if is_proxy_route:
            return "proxy_route"
        # Factory/constructor functions
        if node.name.startswith("create_") or node.name.startswith("build_"):
            return "factory"
        # Service functions
        if node.name.startswith("get_") or node.name.startswith("apply_") or node.name.startswith("report_"):
            return "service"
        # Serializer/deserializer functions
        if "to_" in node.name or "from_" in node.name or "_to_" in node.name:
            return "serializer"
        return "function"
    return None


def check_srp(tree: ast.Module, path: Path, source: str | None = None) -> list[str]:
    """Check SRP compliance.

    A module violates SRP if it mixes unrelated concerns.  Allowed groupings:
    - Multiple enums together (types.py)
    - Multiple schemas together (schemas.py, contracts.py)
    - Multiple errors together (errors.py)
    - Multiple entities together (entities.py)
    - Multiple ORM models together (orm.py)
    - One service class + its helper functions
    - Proxy route modules: all route handlers proxy to ONE backend

    Violations occur when you mix e.g. entities + services + persistence.
    """
    violations: list[str] = []

    if source is None:
        source = path.read_text(encoding="utf-8")
    is_proxy = _is_proxy_route_module(source, tree)

    concerns: dict[str, list[str]] = {}
    for node in ast.iter_child_nodes(tree):
        category = _classify_node(node, is_proxy)
        if category is None:
            continue
        concerns.setdefault(category, []).append(node.name if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) else "?")

    # Count distinct concern types
    concern_types = set(concerns.keys())

    # Allowed single-concern modules (any number of items)
    single_concern_ok = {"enum", "error", "schema", "entity", "orm", "model", "proxy_route"}

    # Allowed two-concern combinations
    two_concern_ok = {
        frozenset({"enum", "entity"}),       # types.py + simple entities
        frozenset({"schema", "model"}),       # schemas + pydantic models
        frozenset({"enum", "model"}),         # enums + pydantic models (schemas.py pattern)
        frozenset({"entity", "model"}),       # entities + request schemas (registry pattern)
        frozenset({"service", "factory"}),    # service + create_* helpers
        frozenset({"service", "function"}),   # service + utility functions (engine.py pattern)
        frozenset({"repository", "function"}), # repository + factory functions
        frozenset({"serializer", "factory"}), # serialization helpers
        frozenset({"entity", "enum"}),        # entities with enums
        frozenset({"orm", "entity"}),         # ORM + domain entities
        frozenset({"entity", "function"}),    # one class + its convenience helper functions
        frozenset({"factory", "function"}),   # DID generation helpers
        frozenset({"model", "function"}),     # single request schema + route handler (config_reload pattern)
    }

    if len(concern_types) > 2:
        items = ", ".join(f"{k}: {', '.join(v)}" for k, v in concerns.items())
        violations.append(
            f"SRP violation: module mixes {len(concern_types)} unrelated concerns: {items}. "
            "Split into separate modules."
        )
    elif len(concern_types) == 2:
        if concern_types not in two_concern_ok:
            items = ", ".join(f"{k}: {', '.join(v)}" for k, v in concerns.items())
            violations.append(
                f"SRP violation: module mixes unrelated concerns: {items}. "
                "Split into separate modules."
            )

    return violations


def validate_module(path: Path) -> list[str]:
    """Validate a single Python module against all rules."""
    violations: list[str] = []

    # Rule 1: Line count
    line_count = count_lines(path)
    if line_count >= MAX_LINES:
        violations.append(
            f"LOC violation: {path} has {line_count} lines (limit: {MAX_LINES}). "
            f"Split into smaller modules."
        )

    # Rule 2: SRP
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        srp_violations = check_srp(tree, path, source)
        violations.extend(srp_violations)
    except SyntaxError as e:
        violations.append(f"Syntax error in {path}: {e}")

    return violations


def main() -> int:
    """Entry point."""
    paths: list[Path] = []
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            p = Path(arg)
            if p.is_file():
                paths.append(p)
            elif p.is_dir():
                paths.extend(p.rglob("*.py"))
            else:
                print(f"Warning: {arg} not found", file=sys.stderr)
    else:
        # Default: scan packages/ (DDD) or legacy layout directories
        if DEFAULT_PACKAGES.exists():
            paths = list(DEFAULT_PACKAGES.rglob("*.py"))
        else:
            for scan_dir in DEFAULT_SCAN_DIRS:
                d = Path(scan_dir)
                if d.is_dir():
                    paths.extend(d.rglob("*.py"))

    # Filter
    paths = [
        p for p in paths
        if p.is_file()
        and p.suffix == ".py"
        and not any(skip in p.parts for skip in SKIP_DIRS)
    ]

    all_violations: dict[Path, list[str]] = {}
    for path in sorted(paths):
        violations = validate_module(path)
        if violations:
            all_violations[path] = violations

    # Report
    total = 0
    for path, violations in all_violations.items():
        print(f"\n{path}:")
        for v in violations:
            print(f"  - {v}")
            total += 1

    if total:
        print(f"\nFAILED: {total} violation(s) across {len(all_violations)} module(s).")
        return 1
    else:
        print(f"OK: {len(paths)} module(s) validated, 0 violations.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
