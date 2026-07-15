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


class CounterMetricFamily:
    def __init__(self, *args, **kwargs):
        self.metrics = []

    def add_metric(self, labels, value):
        self.metrics.append((tuple(labels), value))


class GaugeMetricFamily:
    def __init__(self, *args, **kwargs):
        self.metrics = []

    def add_metric(self, labels, value):
        self.metrics.append((tuple(labels), value))


docker_errors_module.DockerException = DockerException
docker_module.errors = docker_errors_module
original_modules = {
    "docker": sys.modules.get("docker"),
    "docker.errors": sys.modules.get("docker.errors"),
}

try:
    sys.modules["docker"] = docker_module
    sys.modules["docker.errors"] = docker_errors_module
    prometheus_client_module = types.ModuleType("prometheus_client")
    prometheus_client_core_module = types.ModuleType("prometheus_client.core")
    prometheus_client_module.CollectorRegistry = type("CollectorRegistry", (), {"register": lambda self, collector: None})
    prometheus_client_module.start_http_server = lambda *args, **kwargs: None
    prometheus_client_core_module.CounterMetricFamily = CounterMetricFamily
    prometheus_client_core_module.GaugeMetricFamily = GaugeMetricFamily
    prometheus_client_module.core = prometheus_client_core_module
    original_prometheus_client = sys.modules.get("prometheus_client")
    original_prometheus_client_core = sys.modules.get("prometheus_client.core")
    sys.modules["prometheus_client"] = prometheus_client_module
    sys.modules["prometheus_client.core"] = prometheus_client_core_module
    spec.loader.exec_module(container_metrics_exporter)
finally:
    for module_name, module_value in original_modules.items():
        if module_value is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = module_value
    if original_prometheus_client is None:
        sys.modules.pop("prometheus_client", None)
    else:
        sys.modules["prometheus_client"] = original_prometheus_client
    if original_prometheus_client_core is None:
        sys.modules.pop("prometheus_client.core", None)
    else:
        sys.modules["prometheus_client.core"] = original_prometheus_client_core


class FakeContainer:
    def __init__(self, service: str, project: str = "dq-rulebuilder", status: str = "running", name: str | None = None, stats: dict | None = None):
        self.labels = {
            "com.docker.compose.project": project,
            "com.docker.compose.service": service,
        }
        self.status = status
        self.name = name or f"{project}-{service}-1"
        self._stats = stats or {
            "cpu_stats": {"cpu_usage": {"total_usage": 2_500_000_000}},
            "memory_stats": {"usage": 1_500_000_000, "stats": {"inactive_file": 250_000_000, "cache": 100_000_000}},
        }

    def stats(self, stream: bool = False):
        return self._stats


def test_build_counts_includes_renamed_engine_and_llm_services():
    counts = container_metrics_exporter.build_counts(
        [
            FakeContainer("dq-made-easy-engine"),
            FakeContainer("dq-made-easy-llm"),
            FakeContainer("frontend"),
            FakeContainer("dq-made-easy-llm", status="exited"),
            FakeContainer("dq-made-easy-engine", project="other-project"),
        ],
        "dq-rulebuilder",
    )

    assert counts["dq_llm"] == 1
    assert counts["frontend"] == 1
    assert counts["dq_engine"] == 1


def test_build_resource_metrics_includes_container_cpu_and_memory():
    cpu_metric, memory_metric = container_metrics_exporter.build_resource_metrics(
        [
            FakeContainer("dq-made-easy-engine", name="dq-made-easy-engine-1"),
            FakeContainer("dq-made-easy-llm", status="exited"),
            FakeContainer("dq-made-easy-engine", project="other-project"),
        ],
        "dq-rulebuilder",
    )

    assert cpu_metric.metrics == [(('dq-rulebuilder', 'dq-made-easy-engine', 'dq-made-easy-engine-1'), 2.5)]
    assert memory_metric.metrics == [(('dq-rulebuilder', 'dq-made-easy-engine', 'dq-made-easy-engine-1'), 1_150_000_000.0)]
