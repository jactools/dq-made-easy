#!/usr/bin/env python3
"""Warm up Spark jars by resolving packages via PySpark/Ivy and copying jars into a shared volume.

Usage:
    python scripts/warmup_spark_jars.py --ivy-dir /home/appuser/.ivy2 --jar-dir /home/appuser/.dq-spark-jars
    python scripts/warmup_spark_jars.py --cache-dir /repo/tmp/spark-jars  # host-side cache
"""
import argparse
import glob
import hashlib
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

# Marker file stored alongside cached jars to track package version
_SPARK_JARS_VERSION_FILE = ".spark-jars-version"


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


def _package_version_key(packages: str) -> str:
    """Compute a stable hash for the package string so we can detect changes."""
    return hashlib.sha256(packages.encode("utf-8")).hexdigest()[:16]


def _cache_is_fresh(cache_dir: str, packages: str) -> bool:
    """Return True if cached jars exist and match the current package string."""
    version_file = os.path.join(cache_dir, _SPARK_JARS_VERSION_FILE)
    if not os.path.isfile(version_file):
        return False
    try:
        stored_key = open(version_file, "r", encoding="utf-8").read().strip()
    except OSError:
        return False
    expected_key = _package_version_key(packages)
    if stored_key != expected_key:
        print(
            f"Spark jar cache version mismatch ({stored_key} != {expected_key}); "
            f"packages changed, re-resolving..."
        )
        return False
    # Verify at least one jar is present
    jars = glob.glob(os.path.join(cache_dir, "*.jar"))
    if not jars:
        print("Spark jar cache exists but contains no jars; re-resolving...")
        return False
    return True


def _write_cache_version(cache_dir: str, packages: str) -> None:
    """Write the package version marker into the cache directory."""
    version_file = os.path.join(cache_dir, _SPARK_JARS_VERSION_FILE)
    with open(version_file, "w", encoding="utf-8") as handle:
        handle.write(_package_version_key(packages))


def main():
    parser = argparse.ArgumentParser(description="Warm up Spark jars via Ivy resolution")
    parser.add_argument("--ivy-dir", default="/home/appuser/.ivy2", help="Ivy cache directory")
    parser.add_argument("--jar-dir", default="/home/appuser/.dq-spark-jars", help="Destination jar directory")
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Host-side cache directory. If jars are cached for the current "
        "package string, skips Ivy resolution and copies cached jars to --jar-dir.",
    )
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
    cache_dir = os.path.abspath(args.cache_dir) if args.cache_dir else None

    print("ivy_dir:", ivy_dir)
    print("jar_dir:", jar_dir)
    print("packages:", packages)
    print(f"max_jar_size_mb: {max_mb}, include_large_jars: {include_large}")
    if cache_dir:
        print("cache_dir:", cache_dir)

    # --- Fast path: serve from host-side cache ---
    if cache_dir and _cache_is_fresh(cache_dir, packages):
        print(f"Using cached Spark jars from {cache_dir}")
        os.makedirs(jar_dir, exist_ok=True)
        copied = copy_jars([cache_dir], jar_dir, max_mb=max_mb, include_large=include_large)
        print(f"Copied {copied} cached jars into {jar_dir}")
        sys.exit(0)

    # --- Slow path: resolve via Ivy ---
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

    # Populate host-side cache so subsequent builds skip Ivy resolution
    if cache_dir:
        print(f"Populating Spark jar cache at {cache_dir}")
        # Clear stale jars from cache before writing
        _prune_cache_dir(cache_dir)
        cache_copied = copy_jars(candidates, cache_dir, max_mb=max_mb, include_large=include_large)
        _write_cache_version(cache_dir, packages)
        print(f"Cached {cache_copied} jars into {cache_dir}")


def _prune_cache_dir(cache_dir: str) -> None:
    """Remove old jars from the cache before repopulating."""
    os.makedirs(cache_dir, exist_ok=True)
    for entry in glob.glob(os.path.join(cache_dir, "*.jar")):
        os.remove(entry)
    # Also remove stale version marker so it gets rewritten
    version_file = os.path.join(cache_dir, _SPARK_JARS_VERSION_FILE)
    if os.path.isfile(version_file):
        os.remove(version_file)


if __name__ == "__main__":
    main()
