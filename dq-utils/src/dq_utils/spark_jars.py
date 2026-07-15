from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any


DEFAULT_SPARK_JAR_DIR = Path.home() / ".dq-spark-jars"
DIRECT_SPARK_PACKAGE_ARTIFACTS = (
    "spark-avro_2.13",
    "hadoop-aws",
    "delta-spark_2.13",
    "delta-storage",
    "iceberg-spark-runtime-4.0_2.13",
)

REQUIRED_LARGE_SPARK_JARS = (
    "software.amazon.awssdk_bundle",
    "software.amazon.awssdk_",
    "aws-java-sdk",
)


def _artifact_versions(jar_paths: list[Path], artifact_name: str) -> dict[str, list[str]]:
    versions: dict[str, list[str]] = {}
    pattern = re.compile(rf"(?:^|_){re.escape(artifact_name)}-(?P<version>[^/]+)\.jar$")
    for path in jar_paths:
        match = pattern.search(path.name)
        if match is None:
            continue
        versions.setdefault(match.group("version"), []).append(path.name)
    return versions


def _reject_duplicate_direct_artifacts(jar_paths: list[Path]) -> None:
    conflicts: list[str] = []
    for artifact_name in DIRECT_SPARK_PACKAGE_ARTIFACTS:
        versions = _artifact_versions(jar_paths, artifact_name)
        if len(versions) < 2:
            continue
        version_list = ", ".join(f"{version} ({', '.join(names)})" for version, names in sorted(versions.items()))
        conflicts.append(f"{artifact_name}: {version_list}")

    if conflicts:
        raise SystemExit(
            "Conflicting Spark package jar versions found in the shared Spark jar directory: "
            + "; ".join(conflicts)
            + ". Re-run dq-engine-warmup or clear the spark-jars volume so only the canonical package versions remain."
        )


def spark_jar_paths() -> list[Path]:
    jar_dir = Path(os.getenv("DQ_SPARK_JAR_DIR") or DEFAULT_SPARK_JAR_DIR)
    if not jar_dir.is_dir():
        raise SystemExit(
            f"Spark jar directory not found: {jar_dir}. The dq-engine image must bake the required Spark jars during the build phase."
        )

    all_jars = sorted(path for path in jar_dir.glob("*.jar") if path.is_file())
    if not all_jars:
        raise SystemExit(
            f"No Spark jars were found in {jar_dir}. The dq-engine image must copy the build-time Spark cache into that directory."
        )

    max_mb_env = os.getenv("DQ_SPARK_MAX_JAR_SIZE_MB")
    try:
        max_mb = int(max_mb_env) if max_mb_env else 200
    except Exception:
        max_mb = 200

    include_large = os.getenv("DQ_SPARK_INCLUDE_LARGE_JARS", "").strip().lower() in ("1", "true", "yes")

    filtered: list[Path] = []
    excluded: list[tuple[str, float]] = []
    for p in all_jars:
        try:
            size_mb = p.stat().st_size / (1024 * 1024)
        except Exception:
            size_mb = 0.0

        keep_large = include_large or any(
            p.name.startswith(prefix) or p.name.endswith(prefix) or prefix in p.name
            for prefix in REQUIRED_LARGE_SPARK_JARS
        )
        if size_mb > max_mb and not keep_large:
            excluded.append((p.name, size_mb))
            continue
        filtered.append(p)

    if not filtered:
        raise SystemExit(
            f"No Spark jars remain after applying size filter (max {max_mb}MB)."
            " Set DQ_SPARK_INCLUDE_LARGE_JARS=1 to include large jars or increase DQ_SPARK_MAX_JAR_SIZE_MB."
        )

    _reject_duplicate_direct_artifacts(filtered)

    if excluded:
        names = ", ".join(name for name, _ in excluded[:10])
        print(
            f"warning: excluded {len(excluded)} large jar(s) >{max_mb}MB: {names}{'...' if len(excluded)>10 else ''}"
        )

    return filtered


def configure_spark_builder_with_local_jars(builder: Any) -> Any:
    jar_paths = spark_jar_paths()
    jar_list = ",".join(str(path) for path in jar_paths)
    classpath = os.pathsep.join(str(path) for path in jar_paths)

    submit_args = os.environ.get("PYSPARK_SUBMIT_ARGS", "pyspark-shell")
    submit_tokens = shlex.split(submit_args)
    if "spark.driver.extraClassPath=" not in submit_args or "spark.executor.extraClassPath=" not in submit_args:
        jar_submit_args = [
            "--jars",
            jar_list,
            "--conf",
            f"spark.driver.extraClassPath={classpath}",
            "--conf",
            f"spark.executor.extraClassPath={classpath}",
        ]
        os.environ["PYSPARK_SUBMIT_ARGS"] = " ".join(jar_submit_args + submit_tokens)

    return (
        builder.config("spark.jars", jar_list)
        .config("spark.driver.extraClassPath", classpath)
        .config("spark.executor.extraClassPath", classpath)
    )