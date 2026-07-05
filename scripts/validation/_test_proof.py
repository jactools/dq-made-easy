"""Reusable test-proof and evidence writer for validation scripts.

All ``scripts/validation/*.py`` should use this module instead of rolling their own
proof/evidence writing logic.  It enforces the test-proof v1 JSON schema, derives
the app version from ``VERSION_MANIFEST.json``, and writes evidence directories
into the canonical ``test-results/evidence/<app_version>/<proof_type>/`` layout.

Example
-------
>>> from scripts.validation._test_proof import write_proof, write_evidence_files
>>> evidence_dir = write_evidence_files(
...     app_version="api",
...     proof_type="engine",
...     feature="kafka-violations-pipeline",
...     files={"run_payload.json": run_payload, "kafka_info.json": kafka_info},
... )
>>> write_proof(
...     app_version="api",
...     proof_type="engine",
...     feature="kafka-violations-pipeline",
...     summary="Pipeline executed end-to-end",
...     status="passed",
...     test_count=8,
...     assertions=["Run triggered", "Violations produced"],
...     raw_evidence_directory=evidence_dir,
...     command="bash scripts/validation/validate_kafka_violations_pipeline.sh",
... )
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Resolve root directory
# ---------------------------------------------------------------------------

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # scripts/.. = repo root

# ---------------------------------------------------------------------------
# App version resolution
# ---------------------------------------------------------------------------


def _resolve_app_version(app_key: str = "api") -> str:
    """Read the canonical app version from VERSION_MANIFEST.json.

    Falls back to ``os.environ["APP_VERSION"]`` then ``"0.11.5"``.
    """
    manifest_path = _ROOT_DIR / "VERSION_MANIFEST.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            version = manifest.get("apps", {}).get(app_key)
            if version and isinstance(version, str):
                return version
        except Exception:
            pass

    import os

    env_version = os.environ.get("APP_VERSION")
    if env_version and isinstance(env_version, str) and env_version.strip():
        return env_version.strip()

    return "0.11.5"


# ---------------------------------------------------------------------------
# Evidence directory helper
# ---------------------------------------------------------------------------


def write_evidence_files(
    *,
    app_version: str,
    proof_type: str,
    feature: str,
    files: dict[str, Any] | None = None,
) -> tuple[Path, str]:
    """Create an evidence directory and optionally write files into it.

    Returns ``(absolute_path, relative_path_from_repo_root)``.
    """
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    evidence_id = f"{ts}-{feature}"
    abs_dir = _ROOT_DIR / "test-results" / "evidence" / app_version / proof_type / evidence_id
    abs_dir.mkdir(parents=True, exist_ok=True)

    if files:
        for filename, content in files.items():
            target = abs_dir / filename
            if isinstance(content, str):
                target.write_text(content)
            elif isinstance(content, (dict, list)):
                target.write_text(json.dumps(content, indent=2, default=str))
            else:
                target.write_bytes(content)

    rel_path = str(abs_dir.relative_to(_ROOT_DIR))
    return abs_dir, rel_path


# ---------------------------------------------------------------------------
# Test-proof writer
# ---------------------------------------------------------------------------

# Proof files must live exactly under:
#   test-results/test-proof/<app_version>/<proof_type>/<proof_id>.json
# The build gate (validate_test_proof.sh) enforces this flat two-level layout.


def write_proof(
    *,
    app_version: str,
    proof_type: str,
    feature: str,
    summary: str,
    status: str,
    test_count: int,
    assertions: list[str],
    raw_evidence_directory: str,
    command: str = "",
    proof_id: str = "",
    test_files: list[str] | None = None,
    proof_data: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> Path:
    """Write a test-proof JSON artifact conforming to the v1 schema.

    The artifact is written to::

        test-results/test-proof/<app_version>/<proof_type>/<proof_id>.json

    Parameters
    ----------
    app_version:
        Application version key (e.g. ``"api"``, ``"ui"``, ``"0.11.5"``).
        Keys like ``"api"`` are resolved via ``VERSION_MANIFEST.json``.
    proof_type:
        One of ``ui``, ``ui-api``, ``api``, ``engine``, ``database``, ``ai``, ``command``.
        This becomes the immediate sub-directory name under ``<app_version>``.
    feature:
        Feature slug (kebab-case), e.g. ``"kafka-violations-pipeline"``.
    summary:
        Human-readable summary of what the test validated.
    status:
        One of ``passed``, ``failed``, ``blocked``, ``skipped``.
    test_count:
        Number of individual tests/assertions run (>= 1).
    assertions:
        List of assertion descriptions (>= 1).
    raw_evidence_directory:
        Relative path to the evidence directory (from repo root).
    command:
        Shell command that was run.  Auto-generated from ``sys.argv`` if not given.
    proof_id:
        Unique proof identifier.  Auto-generated from ``feature`` + timestamp if not given.
    test_files:
        List of test file paths.  Derived from ``__file__`` if not given.
    proof_data:
        Arbitrary structured proof data.
    diagnostics:
        Arbitrary structured diagnostics.

    Returns
    -------
    Path
        Absolute path to the written ``.json`` file.
    """
    if not proof_id:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        proof_id = f"{feature}-{ts}"

    if not command:
        command = " ".join(sys.argv)

    if test_files is None:
        test_files = [str(Path(sys.argv[0]).resolve().relative_to(_ROOT_DIR))]

    # Resolve the app_version to the canonical version string
    if app_version in ("api", "ui", "engine", "database", "ai", "command"):
        resolved_version = _resolve_app_version(app_key=app_version)
    else:
        resolved_version = app_version

    proof: dict[str, Any] = {
        "app_version": resolved_version,
        "proof_id": proof_id,
        "proof_type": proof_type,
        "feature": feature,
        "summary": summary,
        "status": status,
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "command": command,
        "raw_evidence_directory": raw_evidence_directory,
        "test_files": [str(f) for f in test_files if str(f).strip()],
        "test_file_count": len(test_files),
        "test_count": test_count,
        "assertions": [str(a) for a in assertions if str(a).strip()],
    }

    if proof_data:
        proof["proof_data"] = proof_data
    if diagnostics:
        proof["diagnostics"] = diagnostics

    # Flat layout: test-results/test-proof/<app_version>/<proof_type>/<proof_id>.json
    proof_dir = (
        _ROOT_DIR / "test-results" / "test-proof" / resolved_version / proof_type
    )
    proof_dir.mkdir(parents=True, exist_ok=True)
    proof_path = proof_dir / f"{proof_id}.json"
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")

    return proof_path
