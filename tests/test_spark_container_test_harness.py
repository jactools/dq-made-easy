from __future__ import annotations

from spark_container_test_harness import should_route_spark_tests_to_container


def test_should_route_spark_tests_to_container_for_spark_targets() -> None:
    assert should_route_spark_tests_to_container(
        ["dq-engine/tests/test_spark_expectations_adapter.py"],
        running_in_container=False,
        docker_available=True,
    )


def test_should_not_route_non_spark_targets() -> None:
    assert not should_route_spark_tests_to_container(
        ["tests/test_api_health.py"],
        running_in_container=False,
        docker_available=True,
    )


def test_should_route_spark_node_ids_to_container() -> None:
    assert should_route_spark_tests_to_container(
        ["dq-engine/tests/test_spark_expectations_adapter.py::test_execute_spark_expectations_rule_emits_execution_metadata"],
        running_in_container=False,
        docker_available=True,
    )


def test_should_route_when_already_in_container() -> None:
    assert should_route_spark_tests_to_container(
        ["dq-engine/tests/test_spark_expectations_adapter.py"],
        running_in_container=True,
        docker_available=True,
    )
