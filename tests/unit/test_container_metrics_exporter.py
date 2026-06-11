from __future__ import annotations

import importlib.util
import types
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "observability"
    / "container-metrics"
    / "container_metrics_exporter.py"
)

spec = importlib.util.spec_from_file_location("container_metrics_exporter", MODULE_PATH)
assert spec is not None and spec.loader is not None
container_metrics_exporter = importlib.util.module_from_spec(spec)

docker_module = types.ModuleType("docker")
docker_errors_module = types.ModuleType("docker.errors")


class DockerException(Exception):
    pass


docker_errors_module.DockerException = DockerException
docker_module.errors = docker_errors_module
original_modules = {
    "docker": sys.modules.get("docker"),
    "docker.errors": sys.modules.get("docker.errors"),
}

try:
    sys.modules["docker"] = docker_module
    sys.modules["docker.errors"] = docker_errors_module
    spec.loader.exec_module(container_metrics_exporter)
finally:
    for module_name, module_value in original_modules.items():
        if module_value is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = module_value


class FakeContainer:
    def __init__(self, service: str, project: str = "dq-rulebuilder", status: str = "running"):
        self.labels = {
            "com.docker.compose.project": project,
            "com.docker.compose.service": service,
        }
        self.status = status


def test_build_counts_includes_dq_llm():
    counts = container_metrics_exporter.build_counts(
        [
            FakeContainer("dq-llm"),
            FakeContainer("frontend"),
            FakeContainer("dq-llm", status="exited"),
            FakeContainer("dq-llm", project="other-project"),
        ]
    )

    assert counts["dq_llm"] == 1
    assert counts["frontend"] == 1
    assert counts["dq_engine"] == 0
