from __future__ import annotations

from typing import Any

import pytest

from app.application.services.gx_execution_source_adapter import GxExecutionSourceAdapterError
from app.application.services.gx_execution_source_adapter import PysparkExecutionSourceAdapter
from app.domain.entities import GxArtifactEnvelopeEntity


def _suite(*, execution_shape: str, output_location: str | None = None) -> GxArtifactEnvelopeEntity:
    payload: dict[str, Any] = {
        "suiteId": "suite-1",
        "suiteVersion": 1,
        "artifactVersion": "v1",
        "assignmentScope": {"dataObjectId": "do-1", "datasetId": None, "dataProductId": None},
        "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
        "gxSuite": {"expectation_suite_name": "suite_1", "expectations": [], "meta": {}},
        "compiledFrom": {
            "ruleIds": ["rule-1"],
            "compilerVersion": "dq-compiler-7.3",
            "generatedAt": "2026-04-18T00:00:00Z",
        },
        "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": ["order_id"]},
        "executionContract": {
            "engineTarget": "pyspark",
            "executionShape": execution_shape,
            "traceability": {
                "ruleId": "rule-1",
                "ruleVersionId": "rule-version-1",
                "gxSuiteId": "suite-1",
                "gxSuiteVersion": 1,
                "dataObjectVersionId": "dov-1",
            },
        },
    }
    if execution_shape == "join_pair":
        payload["executionContract"]["sourceMaterialization"] = {
            "landingZoneArtifactId": "lz-1",
            "landingZoneVersionId": "dov-1",
            "outputLocation": output_location or "s3://dq/joined/1",
            "joinType": "inner",
            "joinKeys": ["customer_id"],
            "leftSource": {
                "dataObjectId": "do-left",
                "dataObjectVersionId": "dov-left",
                "datasetId": "ds-left",
                "dataProductId": None,
            },
            "rightSource": {
                "dataObjectId": "do-right",
                "dataObjectVersionId": "dov-right",
                "datasetId": "ds-right",
                "dataProductId": None,
            },
        }
    return GxArtifactEnvelopeEntity.model_validate(payload)


def test_pyspark_execution_source_adapter_loads_single_object_source() -> None:
    adapter = PysparkExecutionSourceAdapter(source_loader=lambda _spark_session, source_ref: {"source_ref": source_ref})
    suite = _suite(execution_shape="single_object")

    asset_ref = adapter.resolve_asset(
        spark_session=object(),
        suite=suite,
        data_object_version_id="dov-1",
        correlation_id="corr-1",
    )
    handle = adapter.load_dataframe(spark_session=object(), asset_ref=asset_ref)
    handle = adapter.materialize_primary_key(handle, ["order_id"])
    handle = adapter.emit_validation_target(handle, {"suite_id": "suite-1", "correlation_id": "corr-1"})

    assert asset_ref["source_ref"] == "dov-1"
    assert handle["source_ref"] == "dov-1"
    assert handle["primary_key_fields"] == ["order_id"]
    assert handle["gx_context"]["suite_id"] == "suite-1"


def test_pyspark_execution_source_adapter_loads_join_pair_source() -> None:
    adapter = PysparkExecutionSourceAdapter(
        materialized_source_loader=lambda _spark_session, source_ref: {"source_ref": source_ref}
    )
    suite = _suite(execution_shape="join_pair", output_location="s3://dq/joined/2")

    asset_ref = adapter.resolve_asset(
        spark_session=object(),
        suite=suite,
        data_object_version_id="dov-2",
        correlation_id="corr-2",
    )
    handle = adapter.load_dataframe(spark_session=object(), asset_ref=asset_ref)

    assert adapter.supports_execution_shape("join_pair")
    assert asset_ref["source_ref"] == "s3://dq/joined/2"
    assert handle["source_ref"] == "s3://dq/joined/2"


def test_pyspark_execution_source_adapter_supports_streaming_and_micro_batch_execution_shapes() -> None:
    adapter = PysparkExecutionSourceAdapter(source_loader=lambda _spark_session, source_ref: {"source_ref": source_ref})

    for execution_shape in ("streaming", "micro_batch"):
        suite = _suite(execution_shape=execution_shape)

        asset_ref = adapter.resolve_asset(
            spark_session=object(),
            suite=suite,
            data_object_version_id="dov-stream",
            correlation_id="corr-stream",
        )
        handle = adapter.load_dataframe(spark_session=object(), asset_ref=asset_ref)

        assert adapter.supports_execution_shape(execution_shape)
        assert asset_ref["source_ref"] == "dov-stream"
        assert asset_ref["execution_shape"] == execution_shape
        assert handle["source_ref"] == "dov-stream"


def test_pyspark_execution_source_adapter_fails_fast_without_required_loader() -> None:
    adapter = PysparkExecutionSourceAdapter()
    suite = _suite(execution_shape="single_object")

    assert not adapter.supports_execution_shape("single_object")

    asset_ref = adapter.resolve_asset(
        spark_session=object(),
        suite=suite,
        data_object_version_id="dov-3",
        correlation_id="corr-3",
    )

    with pytest.raises(GxExecutionSourceAdapterError) as error:
        adapter.load_dataframe(spark_session=object(), asset_ref=asset_ref)

    assert "source_loader" in str(error.value)