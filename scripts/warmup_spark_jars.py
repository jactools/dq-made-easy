#!/usr/bin/env python3
"""Warm up Spark jars by resolving packages via PySpark/Ivy and copying jars into a shared volume.

Usage: python scripts/warmup_spark_jars.py --ivy-dir /home/appuser/.ivy2 --jar-dir /home/appuser/.dq-spark-jars
"""
import argparse
import glob
import os
import shutil
import sys
from xml.sax.saxutils import escape

from pyspark.sql import SparkSession

DEFAULT_SPARK_PACKAGES = (
    "org.apache.spark:spark-avro_2.13:4.1.1,"
    "org.apache.hadoop:hadoop-aws:3.4.2,"
    "io.delta:delta-spark_2.13:4.1.0,"
    "org.apache.iceberg:iceberg-spark-runtime-4.0_2.13:1.10.1"
)


def _artifact_names(packages: str) -> list[str]:
    names: list[str] = []
    for raw_package in packages.split(","):
        parts = raw_package.strip().split(":")
        if len(parts) >= 2 and parts[1].strip():
            names.append(parts[1].strip())
    return names


def _artifact_versions(packages: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    for raw_package in packages.split(","):
        parts = [part.strip() for part in raw_package.strip().split(":")]
        if len(parts) >= 3 and parts[1] and parts[2]:
            versions[parts[1]] = parts[2]
    delta_version = versions.get("delta-spark_2.13")
    if delta_version:
        versions["delta-storage"] = delta_version
    return versions


def _jar_matches_artifact(jar_name: str, artifact_name: str) -> bool:
    return jar_name.startswith(f"{artifact_name}-") or f"_{artifact_name}-" in jar_name


def prune_stale_direct_artifacts(dest_dir: str, packages: str) -> int:
    artifact_versions = _artifact_versions(packages)
    if not artifact_versions or not os.path.isdir(dest_dir):
        return 0

    removed = 0
    for jar in glob.glob(os.path.join(dest_dir, "*.jar")):
        jar_name = os.path.basename(jar)
        for artifact_name, version in artifact_versions.items():
            if not _jar_matches_artifact(jar_name, artifact_name):
                continue
            if jar_name.endswith(f"{artifact_name}-{version}.jar"):
                break
            os.remove(jar)
            removed += 1
            print(f"removed stale Spark jar {jar_name}")
            break
    return removed


def _resolved_required_artifacts(ivy_dir: str, packages: str) -> bool:
    candidate_patterns = [
        os.path.join(ivy_dir, "jars", "*.jar"),
        os.path.join(ivy_dir, "cache", "**", "*.jar"),
    ]
    jar_names: set[str] = set()
    for pattern in candidate_patterns:
        jar_names.update(os.path.basename(path) for path in glob.glob(pattern, recursive=True))
    if not jar_names:
        return False

    for artifact_name in _artifact_names(packages):
        prefix = f"{artifact_name}-"
        if not any(name.startswith(prefix) for name in jar_names):
            return False
    return True


def _parse_env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return default


def _truthy_env(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _split_repositories(raw_repositories: str) -> list[str]:
    repositories: list[str] = []
    for raw_entry in raw_repositories.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        if not entry.endswith("/"):
            entry = f"{entry}/"
        repositories.append(entry)
    return repositories


def _write_ivy_settings(ivy_settings_path: str, repositories: list[str]) -> None:
    if not repositories:
        raise ValueError("at least one repository URL is required")

    resolver_entries: list[str] = []
    for index, repository in enumerate(repositories, start=1):
        resolver_entries.append(
            f'      <ibiblio name="dq-repo-{index}" root="{escape(repository)}" '
            'm2compatible="true" usepoms="true" />'
        )

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<ivysettings>",
        '  <settings defaultResolver="dq-chain" />',
        "  <resolvers>",
        '    <chain name="dq-chain" returnFirst="true">',
        *resolver_entries,
        "    </chain>",
        "  </resolvers>",
        "</ivysettings>",
        "",
    ]
    with open(ivy_settings_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(xml_lines))


def copy_jars(src_dirs, dest_dir, max_mb: int = 200, include_large: bool = False):
    os.makedirs(dest_dir, exist_ok=True)
    count = 0
    for d in src_dirs:
        if not os.path.isdir(d):
            continue
        for jar in glob.glob(os.path.join(d, "**", "*.jar"), recursive=True):
            try:
                size_mb = os.path.getsize(jar) / (1024 * 1024)
                if size_mb > max_mb and not include_large:
                    print(f"skipping large jar {jar} ({size_mb:.1f} MB)")
                    continue
                dst = os.path.join(dest_dir, os.path.basename(jar))
                if not os.path.exists(dst):
                    shutil.copy2(jar, dst)
                    count += 1
            except Exception:
                print(f"warning: failed to copy {jar}")
    return count


def main():
    parser = argparse.ArgumentParser(description="Warm up Spark jars via Ivy resolution")
    parser.add_argument("--ivy-dir", default="/home/appuser/.ivy2", help="Ivy cache directory")
    parser.add_argument("--jar-dir", default="/home/appuser/.dq-spark-jars", help="Destination jar directory")
    parser.add_argument(
        "--packages",
        default=DEFAULT_SPARK_PACKAGES,
        help="Comma-separated Maven packages to resolve",
    )

    default_max_mb = _parse_env_int("DQ_SPARK_MAX_JAR_SIZE_MB", 200)
    include_default = _truthy_env("DQ_SPARK_INCLUDE_LARGE_JARS", False)
    parser.add_argument("--max-jar-size-mb", type=int, default=default_max_mb, help="Maximum jar size to copy (MB)")
    parser.add_argument(
        "--include-large-jars",
        action="store_true",
        default=include_default,
        help="Include jars larger than --max-jar-size-mb",
    )
    args = parser.parse_args()

    ivy_dir = os.path.abspath(args.ivy_dir)
    jar_dir = os.path.abspath(args.jar_dir)
    packages = args.packages
    max_mb = args.max_jar_size_mb
    include_large = args.include_large_jars

    print("ivy_dir:", ivy_dir)
    print("jar_dir:", jar_dir)
    print("packages:", packages)
    print(f"max_jar_size_mb: {max_mb}, include_large_jars: {include_large}")

    os.makedirs(ivy_dir, exist_ok=True)
    os.makedirs(jar_dir, exist_ok=True)
    pruned = prune_stale_direct_artifacts(jar_dir, packages)
    if pruned:
        print(f"Pruned {pruned} stale direct Spark package jar(s) from {jar_dir}")

    builder = SparkSession.builder.master("local[*]").appName("dq-warmup-container")
    builder = builder.config("spark.jars.ivy", ivy_dir).config("spark.jars.packages", packages)

    maven_repos = os.environ.get("MAVEN_REPOSITORIES")
    if maven_repos:
        print("using MAVEN_REPOSITORIES=", maven_repos)
        repositories = _split_repositories(maven_repos)
        ivy_settings_path = os.path.join(ivy_dir, "dq-ivysettings.xml")
        _write_ivy_settings(ivy_settings_path, repositories)
        print("using ivy settings:", ivy_settings_path)
        builder = builder.config("spark.jars.ivySettings", ivy_settings_path)
        builder = builder.config("spark.jars.repositories", maven_repos)

    try:
        spark = builder.getOrCreate()
        try:
            print("triggering Spark to resolve packages...")
            print("count:", spark.range(1).count())
        finally:
            spark.stop()
    except Exception as e:
        if _resolved_required_artifacts(ivy_dir, packages):
            print(
                "warning: Spark exited after resolving the requested artifacts; continuing with the warmed Ivy cache",
                file=sys.stderr,
            )
            print("resolution exception:", e, file=sys.stderr)
        else:
            print("Error while resolving packages:", e, file=sys.stderr)
            sys.exit(1)

    candidates = [
        os.path.join(ivy_dir, "jars"),
        os.path.join(ivy_dir, "cache"),
    ]

    copied = copy_jars(candidates, jar_dir, max_mb=max_mb, include_large=include_large)
    pruned = prune_stale_direct_artifacts(jar_dir, packages)
    if pruned:
        print(f"Pruned {pruned} stale direct Spark package jar(s) from {jar_dir} after copy")
    print(f"Copied {copied} jars into {jar_dir}")


if __name__ == "__main__":
    main()
