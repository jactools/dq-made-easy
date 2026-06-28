from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


TESTS_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
DQ_UTILS_SRC = os.path.join(REPO_ROOT, "dq-utils", "src")

if DQ_UTILS_SRC not in sys.path:
    sys.path.insert(0, DQ_UTILS_SRC)

from dq_utils.spark_runtime import build_spark_session_builder
from dq_utils.spark_runtime import resolve_spark_ui_port
from dq_utils.spark_jars import configure_spark_builder_with_local_jars


class _BuilderStub:
    def __init__(self) -> None:
        self.app_name: str | None = None
        self.master_value: str | None = None
        self.config_values: dict[str, str] = {}

    def appName(self, value: str) -> "_BuilderStub":
        self.app_name = value
        return self

    def master(self, value: str) -> "_BuilderStub":
        self.master_value = value
        return self

    def config(self, key: str, value: str) -> "_BuilderStub":
        self.config_values[str(key)] = str(value)
        return self


class _JarBuilderStub(_BuilderStub):
    pass


class _SparkSessionStub:
    builder = _BuilderStub()


class SparkRuntimeTests(unittest.TestCase):
    def test_resolve_spark_ui_port_defaults_to_4044(self) -> None:
        previous = os.environ.get("DQ_SPARK_UI_PORT")
        try:
            os.environ.pop("DQ_SPARK_UI_PORT", None)
            self.assertEqual(resolve_spark_ui_port(), 4044)
        finally:
            if previous is None:
                os.environ.pop("DQ_SPARK_UI_PORT", None)
            else:
                os.environ["DQ_SPARK_UI_PORT"] = previous

    def test_resolve_spark_ui_port_rejects_non_positive_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive integer"):
            resolve_spark_ui_port("0")

    def test_build_spark_session_builder_sets_master_ui_port_and_timezone(self) -> None:
        _SparkSessionStub.builder = _BuilderStub()

        builder = build_spark_session_builder(
            SparkSession=_SparkSessionStub,
            app_name="test-app",
            master="local[2]",
            spark_ui_port=4046,
            session_timezone="UTC",
        )

        self.assertIs(builder, _SparkSessionStub.builder)
        self.assertEqual(builder.app_name, "test-app")
        self.assertEqual(builder.master_value, "local[2]")
        self.assertEqual(builder.config_values["spark.ui.port"], "4046")
        self.assertEqual(builder.config_values["spark.sql.session.timeZone"], "UTC")

    def test_configure_spark_builder_with_local_jars_sets_pyspark_submit_args(self) -> None:
        previous_submit_args = os.environ.get("PYSPARK_SUBMIT_ARGS")
        previous_jar_dir = os.environ.get("DQ_SPARK_JAR_DIR")
        temp_dir = Path(REPO_ROOT) / "tmp" / "spark-jar-test"
        temp_dir.mkdir(parents=True, exist_ok=True)
        jar_path = temp_dir / "sample.jar"
        jar_path.write_bytes(b"jar")

        try:
            os.environ["DQ_SPARK_JAR_DIR"] = str(temp_dir)
            os.environ.pop("PYSPARK_SUBMIT_ARGS", None)

            builder = _JarBuilderStub()
            configure_spark_builder_with_local_jars(builder)

            submit_args = os.environ["PYSPARK_SUBMIT_ARGS"]
            self.assertIn("--jars", submit_args)
            self.assertIn(str(jar_path), submit_args)
            self.assertIn("spark.driver.extraClassPath", submit_args)
            self.assertIn("spark.executor.extraClassPath", submit_args)
            self.assertEqual(builder.config_values["spark.jars"], str(jar_path))
        finally:
            if previous_submit_args is None:
                os.environ.pop("PYSPARK_SUBMIT_ARGS", None)
            else:
                os.environ["PYSPARK_SUBMIT_ARGS"] = previous_submit_args

            if previous_jar_dir is None:
                os.environ.pop("DQ_SPARK_JAR_DIR", None)
            else:
                os.environ["DQ_SPARK_JAR_DIR"] = previous_jar_dir

            if jar_path.exists():
                jar_path.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()