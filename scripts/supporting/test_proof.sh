#!/usr/bin/env bash

TEST_PROOF_SUPPORT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_PROOF_ROOT_DIR="$(cd "$TEST_PROOF_SUPPORT_DIR/../.." && pwd)"
TEST_PROOF_PYTHON_BIN="$TEST_PROOF_ROOT_DIR/venv/bin/python"

record_validation_test_proof() {
  local script_path="$1"
  local selected_group="$2"
  local exit_code="$3"
  local command_text="$4"

  if [[ ! -x "$TEST_PROOF_PYTHON_BIN" ]]; then
    echo "Missing repository Python interpreter: $TEST_PROOF_PYTHON_BIN" >&2
    return 1
  fi

  TEST_PROOF_REPO_ROOT="$TEST_PROOF_ROOT_DIR" \
  TEST_PROOF_SCRIPT_PATH="$script_path" \
  TEST_PROOF_SELECTED_GROUP="$selected_group" \
  TEST_PROOF_EXIT_CODE="$exit_code" \
  TEST_PROOF_COMMAND_TEXT="$command_text" \
  "$TEST_PROOF_PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

repo_root = Path(os.environ["TEST_PROOF_REPO_ROOT"])
script_path = Path(os.environ["TEST_PROOF_SCRIPT_PATH"])
selected_group = os.environ["TEST_PROOF_SELECTED_GROUP"].strip().lower()
exit_code = int(os.environ["TEST_PROOF_EXIT_CODE"])
command_text = os.environ["TEST_PROOF_COMMAND_TEXT"].strip()

manifest_path = repo_root / "VERSION_MANIFEST.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
app_version = (manifest.get("apps", {}).get("ui") or manifest.get("apps", {}).get("api") or "").strip()
if not app_version:
    raise SystemExit(f"Missing app version in {manifest_path.relative_to(repo_root)}")

header_lines = script_path.read_text(encoding="utf-8").splitlines()[:160]
script_groups: list[str] = []
purpose = ""
capturing_bullets = False
assertions: list[str] = []

for line in header_lines:
    stripped = line.strip()
    group_match = re.match(r"^#\s*validate:\s*groups?=\s*(.+)$", stripped, flags=re.IGNORECASE)
    if group_match:
        script_groups = [item.strip().lower() for item in group_match.group(1).replace(",", " ").split() if item.strip()]
        continue

    if stripped.startswith("# Purpose:") and not purpose:
        purpose = stripped.split(":", 1)[1].strip()
        continue

    if stripped.startswith("# What it does:"):
        capturing_bullets = True
        continue

    if capturing_bullets:
        if stripped.startswith("# - "):
            assertions.append(stripped[4:].strip())
            continue
        if stripped.startswith("#"):
            continue
        if not stripped:
            continue
        capturing_bullets = False

tracked_groups = ["api", "regression", "ui", "engine", "profiling"]
proof_type = ""
if selected_group == "all":
    for group in script_groups:
        if group in tracked_groups:
            proof_type = group
            break
elif selected_group in tracked_groups and selected_group in script_groups:
    proof_type = selected_group

if not proof_type:
    raise SystemExit(0)

script_stem = script_path.stem
feature = re.sub(r"[_-]+", " ", script_stem.replace("validate_", "")).strip()
feature = feature.title() if feature else script_stem
summary = purpose or feature
if not assertions:
    assertions = [summary]

proof_root = repo_root / "test-results" / "test-proof" / app_version / proof_type
evidence_root = repo_root / "test-results" / "evidence" / app_version / "test-proof" / proof_type / script_stem
proof_root.mkdir(parents=True, exist_ok=True)
evidence_root.mkdir(parents=True, exist_ok=True)

raw_evidence_relative = evidence_root.relative_to(repo_root).as_posix()
script_relative = script_path.relative_to(repo_root).as_posix()
proof_path = proof_root / f"{script_stem}.json"
executed_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
status = "passed" if exit_code == 0 else "failed"

proof = {
    "app_version": app_version,
    "proof_id": f"{app_version}-{proof_type}-{script_stem}",
    "proof_type": proof_type,
    "feature": feature,
    "summary": summary,
    "status": status,
    "executed_at_utc": executed_at_utc,
    "command": command_text,
    "raw_evidence_directory": raw_evidence_relative,
    "test_files": [script_relative],
    "test_file_count": 1,
    "test_count": max(1, len(assertions)),
    "assertions": assertions,
    "proof_data": {
        "app_version": app_version,
        "validation_group": selected_group,
        "validation_groups": script_groups,
        "validation_script": script_relative,
        "validation_command": command_text,
        "validation_exit_code": exit_code,
        "script_purpose": purpose,
        "script_assertions": assertions,
        "raw_evidence_directory": raw_evidence_relative,
    },
}

evidence_payload = {
    "app_version": app_version,
    "script": script_relative,
    "selected_group": selected_group,
    "validation_groups": script_groups,
    "command": command_text,
    "status": status,
    "exit_code": exit_code,
    "summary": summary,
    "assertions": assertions,
    "executed_at_utc": executed_at_utc,
}

(evidence_root / "command.txt").write_text(command_text + "\n", encoding="utf-8")
(evidence_root / "status.txt").write_text(f"{status}\n", encoding="utf-8")
(evidence_root / "metadata.json").write_text(json.dumps(evidence_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
(evidence_root / "summary.txt").write_text(summary + "\n", encoding="utf-8")
proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(proof_path.relative_to(repo_root).as_posix())
PY
}