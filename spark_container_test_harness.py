from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Iterable


def _is_running_in_container() -> bool:
    if os.getenv("container"):
        return True
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return True
    if not os.path.exists("/proc/1/cgroup"):
        return False
    with open("/proc/1/cgroup", encoding="utf-8") as handle:
        content = handle.read()
    return any(token in content for token in ("docker", "containerd", "kubepods", "podman", "libpod"))


def _extract_pytest_targets(test_targets: Iterable[str]) -> list[str]:
    normalized_targets: list[str] = []
    for target in test_targets:
        if not target:
            continue
        value = str(target).strip()
        if not value:
            continue
        if value.startswith("-"):
            continue
        normalized_targets.append(value)
    return normalized_targets


def should_route_spark_tests_to_container(
    test_targets: Iterable[str],
    *,
    running_in_container: bool | None = None,
    docker_available: bool | None = None,
) -> bool:
    if docker_available is None:
        docker_available = shutil.which("docker") is not None

    if not docker_available:
        return False

    normalized_targets = _extract_pytest_targets(test_targets)
    if not normalized_targets:
        return False

    return any(_is_spark_target(target) for target in normalized_targets)


def _is_spark_target(target: str) -> bool:
    normalized_target = str(target).strip().lower()
    if not normalized_target:
        return False
    if normalized_target.startswith("-"):
        return False

    candidate = normalized_target
    if "::" in candidate:
        candidate = candidate.split("::", 1)[0]

    if not candidate.endswith(".py"):
        return False

    return "spark" in candidate and (
        candidate.startswith("dq-engine/")
        or candidate.startswith("tests/")
        or candidate.startswith("./dq-engine/")
        or candidate.startswith("./tests/")
    )


def build_container_test_command(test_targets: Iterable[str]) -> list[str]:
    normalized_targets = _extract_pytest_targets(test_targets)
    if not normalized_targets:
        return []

    script_path = os.path.join(os.path.dirname(__file__), "scripts", "run_spark_expectations_container_tests.sh")
    return [script_path, *normalized_targets]


def execute_spark_pytest_via_container(test_targets: Iterable[str]) -> int:
    command = build_container_test_command(test_targets)
    if not command:
        return 0
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    targets = sys.argv[1:]
    if not targets:
        targets = ["dq-engine/tests/test_spark_expectations_adapter.py"]
    exit(execute_spark_pytest_via_container(targets))
