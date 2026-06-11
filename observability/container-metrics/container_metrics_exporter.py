#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import sys
import time
from typing import Dict, Iterable

import docker
from docker.errors import DockerException
from prometheus_client import CollectorRegistry, start_http_server
from prometheus_client.core import GaugeMetricFamily

LOGGER = logging.getLogger("container-metrics-exporter")

COMPOSE_GROUPS = {
    "postgres_instances": {"db", "kong-db", "openmetadata-db"},
    "dq_engine": {"dq-engine", "dq-engine-gx-worker", "dq-engine-test-data-worker"},
    "dq_llm": {"dq-llm"},
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
