from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

TESTS_DIR = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
DQ_UTILS_SRC = os.path.join(REPO_ROOT, "dq-utils", "src")

sys.path.insert(0, DQ_UTILS_SRC)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, ENGINE_DIR)

from scripts.seed_delivery_objects import ICEBERG_CATALOG_NAME
from scripts.seed_delivery_objects import DEFAULT_DELTA_PACKAGE
from scripts.seed_delivery_objects import DEFAULT_HADOOP_AWS_PACKAGE
from scripts.seed_delivery_objects import DEFAULT_SHARED_SPARK_PACKAGES
from scripts.seed_delivery_objects import DeliveryPlan
from scripts.seed_delivery_objects import delivery_format_warning
from scripts.seed_delivery_objects import _seed_plans
from scripts.seed_delivery_objects import _spark_runtime_settings
from scripts.seed_delivery_objects import normalize_identifier
from dq_utils.spark_jars import configure_spark_builder_with_local_jars


class _StubSparkBuilder:
    def __init__(self) -> None:
        self.configs: dict[str, str] = {}

    def config(self, key: str, value: str):
        self.configs[key] = value
        return self


class _StubSession:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


class SeedDeliveryRuntimeSettingsTests(unittest.TestCase):
    def test_normalize_identifier_strips_special_characters(self) -> None:
        self.assertEqual(normalize_identifier("delivery-12/abc"), "delivery_12_abc")

    def test_runtime_settings_for_avro_do_not_add_configs(self) -> None:
        configs = _spark_runtime_settings(delivery_format="avro")

        self.assertEqual(configs, {})

    def test_delta_runtime_settings_add_delta_extension_and_catalog(self) -> None:
        configs = _spark_runtime_settings(delivery_format="delta")

        self.assertEqual(configs["spark.sql.extensions"], "io.delta.sql.DeltaSparkSessionExtension")
        self.assertEqual(configs["spark.sql.catalog.spark_catalog"], "org.apache.spark.sql.delta.catalog.DeltaCatalog")

    def test_json_and_csv_runtime_settings_do_not_add_configs(self) -> None:
        json_configs = _spark_runtime_settings(delivery_format="json")
        csv_configs = _spark_runtime_settings(delivery_format="csv")

        self.assertEqual(json_configs, {})
        self.assertEqual(csv_configs, {})

    def test_unsupported_delivery_format_returns_warning(self) -> None:
        self.assertEqual(
            delivery_format_warning("hudi"),
            "Unsupported file format: hudi. The delivery note states a format this runtime cannot seed.",
        )

    def test_iceberg_runtime_settings_require_warehouse_and_configure_catalog(self) -> None:
        warehouse = Path("/tmp/seed-warehouse")
        configs = _spark_runtime_settings(delivery_format="iceberg", iceberg_warehouse=warehouse)

        self.assertEqual(configs["spark.sql.extensions"], "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        self.assertEqual(configs[f"spark.sql.catalog.{ICEBERG_CATALOG_NAME}"], "org.apache.iceberg.spark.SparkCatalog")
        self.assertEqual(configs[f"spark.sql.catalog.{ICEBERG_CATALOG_NAME}.type"], "hadoop")
        self.assertEqual(configs[f"spark.sql.catalog.{ICEBERG_CATALOG_NAME}.warehouse"], str(warehouse))
        self.assertTrue(configs[f"spark.sql.catalog.{ICEBERG_CATALOG_NAME}.warehouse"].endswith("seed-warehouse"))

    def test_iceberg_runtime_settings_without_warehouse_fail_fast(self) -> None:
        with self.assertRaises(SystemExit):
            _spark_runtime_settings(delivery_format="iceberg")

    def test_default_shared_spark_packages_include_s3a_support(self) -> None:
        self.assertIn(DEFAULT_HADOOP_AWS_PACKAGE, DEFAULT_SHARED_SPARK_PACKAGES)

    def test_default_delta_package_uses_published_coordinate(self) -> None:
        self.assertEqual(DEFAULT_DELTA_PACKAGE, "io.delta:delta-spark_2.13:4.1.0")

    def test_configure_spark_builder_with_local_jars_uses_baked_jar_dir(self) -> None:
        with TemporaryDirectory() as jar_dir:
            jar_dir_path = Path(jar_dir)
            first_jar = jar_dir_path / "alpha.jar"
            second_jar = jar_dir_path / "beta.jar"
            first_jar.write_text("alpha", encoding="utf-8")
            second_jar.write_text("beta", encoding="utf-8")

            previous = os.environ.get("DQ_SPARK_JAR_DIR")
            try:
                os.environ["DQ_SPARK_JAR_DIR"] = jar_dir
                builder = _StubSparkBuilder()

                result = configure_spark_builder_with_local_jars(builder)

                self.assertIs(result, builder)
                self.assertEqual(builder.configs["spark.jars"], f"{first_jar},{second_jar}")
            finally:
                if previous is None:
                    os.environ.pop("DQ_SPARK_JAR_DIR", None)
                else:
                    os.environ["DQ_SPARK_JAR_DIR"] = previous

    def test_configure_spark_builder_with_local_jars_rejects_duplicate_direct_artifact_versions(self) -> None:
        with TemporaryDirectory() as jar_dir:
            jar_dir_path = Path(jar_dir)
            (jar_dir_path / "io.delta_delta-spark_2.13-4.0.0.jar").write_text("old", encoding="utf-8")
            (jar_dir_path / "io.delta_delta-spark_2.13-4.1.0.jar").write_text("new", encoding="utf-8")

            previous = os.environ.get("DQ_SPARK_JAR_DIR")
            try:
                os.environ["DQ_SPARK_JAR_DIR"] = jar_dir
                builder = _StubSparkBuilder()

                with self.assertRaises(SystemExit):
                    configure_spark_builder_with_local_jars(builder)
            finally:
                if previous is None:
                    os.environ.pop("DQ_SPARK_JAR_DIR", None)
                else:
                    os.environ["DQ_SPARK_JAR_DIR"] = previous

    def test_seed_plans_reuses_shared_sessions_per_non_iceberg_format(self) -> None:
        csv_session = _StubSession()
        parquet_session = _StubSession()
        csv_bundle = (csv_session, "csv_functions")
        parquet_bundle = (parquet_session, "parquet_functions")
        plans = [
            DeliveryPlan(
                delivery_id="del-1",
                workspace="retail-banking",
                layer="standardized",
                delivery_location="analytics/Customer/v1/LOAD_DTS=20260220T083000000Z",
                delivery_timestamp="2026-02-20T08:30:00Z",
                physical_output_uri="s3a://retail-banking/standardized/analytics/Customer/v1/LOAD_DTS=20260220T083000000Z",
                data_object_id="do-1",
                data_object_version_id="dov-1",
                data_object_name="Customer",
                delivery_format="csv",
                record_count=10,
                file_count=2,
                attributes=[{"name": "customer_id", "type": "string"}],
                note={},
            ),
            DeliveryPlan(
                delivery_id="del-2",
                workspace="retail-banking",
                layer="standardized",
                delivery_location="analytics/Customer/v2/LOAD_DTS=20260221T083000000Z",
                delivery_timestamp="2026-02-21T08:30:00Z",
                physical_output_uri="s3a://retail-banking/standardized/analytics/Customer/v2/LOAD_DTS=20260221T083000000Z",
                data_object_id="do-1",
                data_object_version_id="dov-2",
                data_object_name="Customer",
                delivery_format="csv",
                record_count=12,
                file_count=2,
                attributes=[{"name": "customer_id", "type": "string"}],
                note={},
            ),
            DeliveryPlan(
                delivery_id="del-3",
                workspace="retail-banking",
                layer="standardized",
                delivery_location="analytics/Customer/v3/LOAD_DTS=20260222T083000000Z",
                delivery_timestamp="2026-02-22T08:30:00Z",
                physical_output_uri="s3a://retail-banking/standardized/analytics/Customer/v3/LOAD_DTS=20260222T083000000Z",
                data_object_id="do-1",
                data_object_version_id="dov-3",
                data_object_name="Customer",
                delivery_format="parquet",
                record_count=14,
                file_count=2,
                attributes=[{"name": "customer_id", "type": "string"}],
                note={},
            ),
        ]

        with patch("scripts.seed_delivery_objects._spark_session", side_effect=[csv_bundle, parquet_bundle]) as spark_session, patch(
            "scripts.seed_delivery_objects._seed_plan",
            side_effect=[
                {"delivery_id": "del-1", "physical_output_uri": "uri-1", "record_count": 10, "file_count": 2},
                {"delivery_id": "del-2", "physical_output_uri": "uri-2", "record_count": 12, "file_count": 2},
                {"delivery_id": "del-3", "physical_output_uri": "uri-3", "record_count": 14, "file_count": 2},
            ],
        ) as seed_plan:
            summaries = _seed_plans(plans, bucket_override=None)

        self.assertEqual([summary["delivery_id"] for summary in summaries], ["del-1", "del-2", "del-3"])
        self.assertEqual(spark_session.call_count, 2)
        self.assertEqual(seed_plan.call_args_list[0].kwargs["spark_bundle"], csv_bundle)
        self.assertEqual(seed_plan.call_args_list[1].kwargs["spark_bundle"], csv_bundle)
        self.assertEqual(seed_plan.call_args_list[2].kwargs["spark_bundle"], parquet_bundle)
        self.assertEqual(csv_session.stop_calls, 1)
        self.assertEqual(parquet_session.stop_calls, 1)


if __name__ == "__main__":
    unittest.main()