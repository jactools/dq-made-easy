#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable

import docker
from docker.errors import DockerException
from prometheus_client import CollectorRegistry, start_http_server
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

LOGGER = logging.getLogger("container-metrics-exporter")

COMPOSE_GROUPS = {
    "postgres_instances": {"db", "kong-db", "openmetadata-db"},
    "dq_engine": {"dq-engine", "dq-made-easy-engine", "dq-engine-gx-worker", "dq-engine-test-data-worker"},
    "dq_llm": {"dq-llm", "dq-made-easy-llm"},
    "frontend": {"frontend"},
    "zammad_support": {
        "zammad-postgresql",
        "zammad-redis",
        "zammad-memcached",
        "zammad-init",
        "zammad-railsserver",
        "zammad-scheduler",
        "zammad-websocket",
        "zammad-nginx",
    },
}


def build_counts(containers: Iterable[object], project_name: str) -> Dict[str, int]:
    counts = {group_name: 0 for group_name in COMPOSE_GROUPS}

    for container in containers:
        labels = getattr(container, "labels", {}) or {}
        project = labels.get("com.docker.compose.project")
        service = labels.get("com.docker.compose.service")

        if project != project_name:
            continue

        if service is None:
            continue

        for group_name, service_names in COMPOSE_GROUPS.items():
            if service in service_names and getattr(container, "status", "") == "running":
                counts[group_name] += 1

    return counts


def build_service_counts(containers: Iterable[object], project_name: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for container in containers:
        labels = getattr(container, "labels", {}) or {}
        project = labels.get("com.docker.compose.project")
        service = labels.get("com.docker.compose.service")

        if project != project_name:
            continue

        if service is None:
            continue

        counts.setdefault(service, 0)
        if getattr(container, "status", "") == "running":
            counts[service] += 1

    return counts


def _container_name(container: object) -> str:
    name = getattr(container, "name", "") or ""
    if name:
        return name.lstrip("/")
    labels = getattr(container, "labels", {}) or {}
    return str(labels.get("com.docker.compose.service") or getattr(container, "id", "unknown"))


def _container_resource_samples(container: object) -> tuple[float, float]:
    stats = container.stats(stream=False)
    cpu_stats = stats.get("cpu_stats") or {}
    cpu_usage = cpu_stats.get("cpu_usage") or {}
    total_usage = float(cpu_usage.get("total_usage") or 0.0)

    memory_stats = stats.get("memory_stats") or {}
    memory_usage = float(memory_stats.get("usage") or 0.0)
    memory_details = memory_stats.get("stats") or {}
    inactive_file = float(memory_details.get("inactive_file") or 0.0)
    cache = float(memory_details.get("cache") or 0.0)
    working_set = max(memory_usage - inactive_file - cache, 0.0)

    return total_usage / 1_000_000_000.0, working_set


def _build_resource_metric_sample(container_info: tuple[str, str, object]) -> tuple[str, str, str, float, float] | None:
    project, service, container = container_info

    try:
        cpu_seconds, memory_working_set = _container_resource_samples(container)
    except DockerException:
        LOGGER.warning("failed to inspect resource stats for container %s", _container_name(container), exc_info=True)
        return None

    return project, service, _container_name(container), cpu_seconds, memory_working_set


def build_resource_metrics(containers: Iterable[object], project_name: str) -> tuple[CounterMetricFamily, GaugeMetricFamily]:
    cpu_metric = CounterMetricFamily(
        "dq_container_cpu_usage_seconds_total",
        "Cumulative CPU time used by running containers.",
        labels=["project", "service", "container"],
    )
    memory_metric = GaugeMetricFamily(
        "dq_container_memory_working_set_bytes",
        "Memory working set bytes used by running containers.",
        labels=["project", "service", "container"],
    )

    target_containers: list[tuple[str, str, object]] = []

    for container in containers:
        labels = getattr(container, "labels", {}) or {}
        project = labels.get("com.docker.compose.project")
        service = labels.get("com.docker.compose.service")

        if project != project_name or service is None or getattr(container, "status", "") != "running":
            continue

        target_containers.append((project, service, container))

    if not target_containers:
        return cpu_metric, memory_metric

    max_workers = min(8, len(target_containers))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for sample in executor.map(_build_resource_metric_sample, target_containers):
            if sample is None:
                continue

            project, service, container_name, cpu_seconds, memory_working_set = sample
            cpu_metric.add_metric([project, service, container_name], cpu_seconds)
            memory_metric.add_metric([project, service, container_name], memory_working_set)

    return cpu_metric, memory_metric


def resolve_project_name() -> str:
    project_name = str(os.environ.get("COMPOSE_PROJECT") or "").strip()
    if not project_name:
        raise RuntimeError("COMPOSE_PROJECT must match the Docker Compose project label")
    return project_name


class ComposeContainerCollector:
    def __init__(self) -> None:
        self.client = docker.from_env()
        self.project_name = resolve_project_name()

    def collect(self):
        try:
            containers = self.client.containers.list(all=True, filters={"label": f"com.docker.compose.project={self.project_name}"})
            counts = build_counts(containers, self.project_name)
            service_counts = build_service_counts(containers, self.project_name)
            cpu_metric, memory_metric = build_resource_metrics(containers, self.project_name)
        except DockerException:
            LOGGER.exception("failed to inspect docker containers")
            os._exit(1)

        metric = GaugeMetricFamily(
            "dq_compose_service_group_running",
            "Running containers for a named compose service group.",
            labels=["group"],
        )
        for group_name, count in counts.items():
            metric.add_metric([group_name], count)
        yield metric

        service_metric = GaugeMetricFamily(
            "dq_compose_service_running",
            "Running containers for each Docker Compose service.",
            labels=["service"],
        )
        for service_name, count in sorted(service_counts.items()):
            service_metric.add_metric([service_name], count)
        yield service_metric

        yield cpu_metric
        yield memory_metric


def main() -> int:
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level_name, logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    port = int(os.environ.get("PORT", "8000"))
    registry = CollectorRegistry()
    registry.register(ComposeContainerCollector())

    LOGGER.info("starting metrics exporter on port %s", port)
    start_http_server(port, registry=registry)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
