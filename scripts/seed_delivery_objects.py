#!/usr/bin/env python3
"""Generate and upload seed delivery objects to AIStor.

The script reads the delivery and delivery-note seed CSVs, resolves the
    matching data object version schema, generates deterministic delivery-format
    output for each note-backed delivery, and uploads the files to the configured
    S3 bucket.
By default the bucket/container comes from the data object workspace, the
delivery layer becomes the top-level folder, and the remaining path uses the
data object name instead of the technical data object id.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from boto3 import client as boto3_client


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DQ_UTILS_SRC = ROOT_DIR / "dq-utils" / "src"
if DQ_UTILS_SRC.is_dir() and str(DQ_UTILS_SRC) not in sys.path:
    sys.path.insert(0, str(DQ_UTILS_SRC))

from dq_utils.spark_jars import configure_spark_builder_with_local_jars
from dq_utils.spark_runtime import build_spark_session_builder

DEFAULT_DELIVERIES_CSV = ROOT_DIR / "dq-db" / "mock-data" / "data-deliveries.csv"
DEFAULT_NOTES_CSV = ROOT_DIR / "dq-db" / "mock-data" / "data-delivery-notes.csv"
DEFAULT_OBJECTS_CSV = ROOT_DIR / "dq-db" / "mock-data" / "data-objects.csv"
DEFAULT_VERSIONS_CSV = ROOT_DIR / "dq-db" / "mock-data" / "data-object-versions.csv"
DEFAULT_ATTRIBUTES_CSV = ROOT_DIR / "dq-db" / "mock-data" / "attributes-catalog.csv"
DEFAULT_DELTA_PACKAGE = "io.delta:delta-spark_2.13:4.1.0"
DEFAULT_AVRO_PACKAGE = "org.apache.spark:spark-avro_2.13:4.1.1"
DEFAULT_HADOOP_AWS_PACKAGE = "org.apache.hadoop:hadoop-aws:3.4.2"
DEFAULT_ICEBERG_PACKAGE = "org.apache.iceberg:iceberg-spark-runtime-4.0_2.13:1.10.1"
DEFAULT_SHARED_SPARK_PACKAGES = (
    DEFAULT_AVRO_PACKAGE,
    DEFAULT_HADOOP_AWS_PACKAGE,
)
ICEBERG_CATALOG_NAME = "seed_catalog"
ICEBERG_NAMESPACE = "seed"
SUPPORTED_SEED_DELIVERY_FORMATS = {"parquet", "csv", "json", "avro", "delta", "iceberg"}


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Required CSV not found: {path}")


def load_csv_rows(path: Path, *, key_field: str | None = None) -> list[dict[str, str]] | dict[str, dict[str, str]]:
    require_file(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [{clean(key): clean(value) for key, value in row.items()} for row in reader]

    if not rows:
        raise SystemExit(f"CSV does not contain any rows: {path}")

    if key_field is None:
        return rows

    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        key = clean(row.get(key_field))
        if not key:
            raise SystemExit(f"CSV row is missing required key '{key_field}': {row}")
        if key in indexed:
            raise SystemExit(f"Duplicate value for '{key_field}' in {path}: {key}")
        indexed[key] = row
    return indexed


def load_object_indexes(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    rows = load_csv_rows(path)
    by_id: dict[str, dict[str, str]] = {}
    by_name: dict[str, dict[str, str]] = {}

    for row in rows:
        object_id = clean(row.get("id"))
        object_name = clean(row.get("name"))
        if not object_id:
            raise SystemExit(f"Data object row is missing id: {row}")
        if not object_name:
            raise SystemExit(f"Data object row is missing name: {row}")
        if object_id in by_id:
            raise SystemExit(f"Duplicate data object id in {path}: {object_id}")
        if object_name in by_name:
            raise SystemExit(f"Duplicate data object name in {path}: {object_name}")
        by_id[object_id] = row
        by_name[object_name] = row

    return by_id, by_name


def truthy(value: object | None) -> bool:
    if value is None:
        return False
    return clean(value).lower() in {"1", "true", "yes", "on"}


def parse_int(value: object | None, *, field_name: str, min_value: int = 1) -> int:
    try:
        parsed = int(clean(value))
    except Exception as exc:
        raise SystemExit(f"Invalid integer value for {field_name}: {value!r}") from exc
    if parsed < min_value:
        raise SystemExit(f"{field_name} must be >= {min_value}: {parsed}")
    return parsed


def normalize_s3_uri(uri: str) -> str:
    raw = clean(uri)
    if raw.startswith("s3://"):
        return "s3a://" + raw[len("s3://") :]
    return raw


def parse_s3a_uri(uri: str) -> tuple[str, str]:
    raw = normalize_s3_uri(uri)
    if not raw.startswith("s3a://"):
        raise SystemExit(f"Unsupported S3 URI: {uri!r}")
    remainder = raw[len("s3a://") :]
    if "/" not in remainder:
        return remainder, ""
    bucket, key_prefix = remainder.split("/", 1)
    return bucket, key_prefix


def split_delivery_path(path: str) -> list[str]:
    raw = clean(path)
    if not raw:
        return []
    if raw.startswith("s3a://") or raw.startswith("s3://"):
        raw = normalize_s3_uri(raw)
        if raw.startswith("s3a://"):
            raw = raw[len("s3a://") :]
    raw = raw.replace(":", "/")
    return [segment for segment in raw.split("/") if segment]


def logical_delivery_location(*, delivery_location: str, layer: str, data_object_id: str, data_object_name: str) -> str:
    segments = split_delivery_path(delivery_location)
    if not segments:
        raise SystemExit("delivery_location must not be empty")

    layer_name = clean(layer)
    if layer_name and segments[0] == layer_name:
        segments = segments[1:]

    if not segments:
        raise SystemExit(f"delivery_location does not include a path beyond layer '{layer_name}'")

    normalized_segments = [data_object_name if segment == data_object_id else segment for segment in segments]
    return "/".join(normalized_segments)


def to_utc_timestamp(value: str) -> datetime:
    raw = clean(value)
    if not raw:
        return datetime(2026, 1, 1, tzinfo=UTC)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def make_physical_output_uri(*, bucket: str, layer: str, logical_location: str) -> str:
    output_bucket = clean(bucket)
    if not output_bucket:
        raise SystemExit("bucket/container must not be empty")

    layer_name = clean(layer)
    if not layer_name:
        raise SystemExit("layer must not be empty")

    return f"s3a://{output_bucket}/{layer_name}/{logical_location}"


def normalize_identifier(value: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z_]+", "_", clean(value)).strip("_")
    return cleaned or "seed"


def delivery_format_warning(delivery_format: str) -> str | None:
    normalized = clean(delivery_format).lower()
    if not normalized or normalized in SUPPORTED_SEED_DELIVERY_FORMATS:
        return None
    return f"Unsupported file format: {normalized}. The delivery note states a format this runtime cannot seed."


def _spark_runtime_settings(*, delivery_format: str, iceberg_warehouse: Path | None = None) -> dict[str, str]:
    seed_format = clean(delivery_format).lower()
    configs: dict[str, str] = {}

    if seed_format == "parquet":
        return configs

    if seed_format == "csv":
        return configs

    if seed_format == "json":
        return configs

    if seed_format == "avro":
        return configs

    if seed_format == "delta":
        configs["spark.sql.extensions"] = "io.delta.sql.DeltaSparkSessionExtension"
        configs["spark.sql.catalog.spark_catalog"] = "org.apache.spark.sql.delta.catalog.DeltaCatalog"
        return configs

    if seed_format == "iceberg":
        if iceberg_warehouse is None:
            raise SystemExit("Iceberg seeding requires a warehouse directory")
        configs["spark.sql.extensions"] = "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"
        configs[f"spark.sql.catalog.{ICEBERG_CATALOG_NAME}"] = "org.apache.iceberg.spark.SparkCatalog"
        configs[f"spark.sql.catalog.{ICEBERG_CATALOG_NAME}.type"] = "hadoop"
        configs[f"spark.sql.catalog.{ICEBERG_CATALOG_NAME}.warehouse"] = str(iceberg_warehouse)
        return configs

    if seed_format == "hudi":
        raise SystemExit(
            "Unsupported delivery_format for seeding: 'hudi'. This runtime supports parquet, csv, json, avro, delta, and iceberg; Hudi requires a Spark 3.5-compatible runtime."
        )

    raise SystemExit(f"Unsupported delivery_format for seeding: {seed_format!r}")


@dataclass(frozen=True)
class DeliveryPlan:
    delivery_id: str
    workspace: str
    layer: str
    delivery_location: str
    delivery_timestamp: str
    physical_output_uri: str
    data_object_id: str
    data_object_version_id: str
    data_object_name: str
    delivery_format: str
    record_count: int
    file_count: int
    attributes: list[dict[str, str]]
    note: dict[str, str]


def build_plans(
    *,
    bucket_override: str | None,
    delivery_ids: set[str] | None,
    deliveries_csv: Path,
    notes_csv: Path,
    objects_csv: Path,
    versions_csv: Path,
    attributes_csv: Path,
) -> list[DeliveryPlan]:
    deliveries = load_csv_rows(deliveries_csv, key_field="id")
    notes = load_csv_rows(notes_csv, key_field="data_delivery_id")
    objects_by_id, objects_by_name = load_object_indexes(objects_csv)
    versions = load_csv_rows(versions_csv, key_field="id")
    attributes = load_csv_rows(attributes_csv)

    attributes_by_version: dict[str, list[dict[str, str]]] = {}
    for row in attributes:
        version_id = clean(row.get("version_id"))
        if not version_id:
            raise SystemExit(f"Attribute row is missing version_id: {row}")
        attributes_by_version.setdefault(version_id, []).append(row)

    selected_note_ids = sorted(notes)
    if delivery_ids:
        unknown = sorted(delivery_ids - set(notes))
        if unknown:
            raise SystemExit(f"Requested delivery id(s) not found in data-delivery-notes.csv: {', '.join(unknown)}")
        selected_note_ids = sorted(delivery_ids)

    plans: list[DeliveryPlan] = []
    for delivery_id in selected_note_ids:
        note = notes[delivery_id]
        delivery = deliveries.get(delivery_id)
        if delivery is None:
            raise SystemExit(f"Delivery note references a missing delivery row: {delivery_id}")

        delivery_format = clean(note.get("delivery_format")).lower()
        if not delivery_format:
            raise SystemExit(f"delivery_format is missing for {delivery_id}")

        data_object_key = clean(delivery.get("data_object_id"))
        data_object_row = objects_by_id.get(data_object_key) or objects_by_name.get(data_object_key)
        if data_object_row is None:
            raise SystemExit(f"Unknown data_object_id for delivery {delivery_id}: {data_object_key}")

        data_object_id = clean(data_object_row.get("id"))
        data_object_name = clean(data_object_row.get("name"))

        data_object_version_id = clean(delivery.get("data_object_version_id"))
        if not data_object_version_id:
            version_number = clean(delivery.get("version"))
            match = next(
                (
                    row
                    for row in versions.values()
                    if clean(row.get("data_object_id")) == data_object_id and clean(row.get("version")) == version_number
                ),
                None,
            )
            if match is None:
                raise SystemExit(f"Unable to resolve data_object_version_id for delivery {delivery_id}")
            data_object_version_id = clean(match.get("id"))

        workspace = clean(data_object_row.get("workspace"))
        if not workspace:
            raise SystemExit(f"Data object workspace is missing for delivery {delivery_id}: {data_object_id}")

        if not data_object_name:
            raise SystemExit(f"Data object name is missing for delivery {delivery_id}: {data_object_id}")

        delivery_layer = clean(delivery.get("layer")) or clean(note.get("layer"))
        note_layer = clean(note.get("layer"))
        if clean(delivery.get("layer")) and note_layer and clean(delivery.get("layer")) != note_layer:
            raise SystemExit(
                f"Layer mismatch for {delivery_id}: delivery rows use {clean(delivery.get('layer'))!r} but note rows use {note_layer!r}"
            )
        if not delivery_layer:
            raise SystemExit(f"Layer is missing for delivery {delivery_id}")

        version_attributes = attributes_by_version.get(data_object_version_id)
        if not version_attributes:
            raise SystemExit(
                f"No attributes found for data_object_version_id {data_object_version_id} (delivery {delivery_id})"
            )

        expected_attribute_count = parse_int(delivery.get("attributes_count"), field_name=f"attributes_count for {delivery_id}")
        if expected_attribute_count != len(version_attributes):
            raise SystemExit(
                f"Attribute count mismatch for {delivery_id}: delivery expects {expected_attribute_count}, "
                f"catalog defines {len(version_attributes)}"
            )

        record_count = parse_int(delivery.get("record_count"), field_name=f"record_count for {delivery_id}")
        file_count = parse_int(note.get("file_count"), field_name=f"file_count for {delivery_id}")
        logical_location = logical_delivery_location(
            delivery_location=clean(delivery.get("delivery_location")),
            layer=delivery_layer,
            data_object_id=data_object_id,
            data_object_name=data_object_name,
        )
        effective_bucket = clean(bucket_override) or workspace
        physical_output_uri = make_physical_output_uri(
            bucket=effective_bucket,
            layer=delivery_layer,
            logical_location=logical_location,
        )

        plans.append(
            DeliveryPlan(
                delivery_id=delivery_id,
                workspace=workspace,
                layer=delivery_layer,
                delivery_location=logical_location,
                delivery_timestamp=clean(delivery.get("timestamp")),
                physical_output_uri=physical_output_uri,
                data_object_id=data_object_id,
                data_object_version_id=data_object_version_id,
                data_object_name=data_object_name,
                delivery_format=delivery_format,
                record_count=record_count,
                file_count=file_count,
                attributes=version_attributes,
                note=note,
            )
        )

    if not plans:
        raise SystemExit("No delivery notes matched the requested input set")

    return plans


def _spark_session(*, delivery_format: str, iceberg_warehouse: Path | None = None):
    try:
        from pyspark.sql import SparkSession
        from pyspark.sql import functions as F
    except Exception as exc:  # pragma: no cover - depends on container image
        raise SystemExit(
            "Python package 'pyspark' is required to generate seeded delivery files. Run this script inside the dq-engine container image."
        ) from exc

    spark_configs = _spark_runtime_settings(delivery_format=delivery_format, iceberg_warehouse=iceberg_warehouse)

    builder = build_spark_session_builder(
        SparkSession=SparkSession,
        app_name="dq-made-easy-seed-deliveries",
        master=os.getenv("DQ_SPARK_MASTER") or "local[*]",
    )
    builder = configure_spark_builder_with_local_jars(builder)
    for key, value in spark_configs.items():
        builder = builder.config(key, value)

    session = builder.getOrCreate()
    session.conf.set("spark.sql.session.timeZone", "UTC")
    return session, F


def _column_expression(*, attribute: dict[str, str], seed_index, F, object_token: str, version_token: str, base_epoch: int):
    name = clean(attribute.get("name")).lower()
    attr_type = clean(attribute.get("type")).lower()
    attr_format = clean(attribute.get("format")).lower()

    row_number = seed_index + F.lit(1)
    row_number_str = row_number.cast("string")
    object_prefix = f"{object_token}-{version_token}"

    if attr_type == "boolean":
        return (seed_index % 2) == 0

    if attr_format == "email" or "email" in name:
        return F.concat(F.lit("user"), row_number_str, F.lit("@example.com"))

    if attr_format == "phone" or "phone" in name:
        return F.concat(F.lit("+1555"), F.lpad(row_number_str, 8, "0"))

    if attr_format == "uuid" or name.endswith("_id"):
        return F.concat(F.lit(object_prefix), F.lit("-"), F.lpad(row_number_str, 8, "0"))

    if attr_type == "date" or attr_format == "date" or "date" in name:
        return F.date_add(F.to_date(F.lit("2026-01-01")), seed_index.cast("int"))

    if attr_type in {"timestamp", "datetime"} or attr_format in {"date-time", "datetime"} or name.endswith("_at") or "time" in name:
        return F.to_timestamp(F.from_unixtime(F.lit(base_epoch) + seed_index.cast("long")))

    if attr_type == "decimal":
        return F.round((seed_index.cast("double") + F.lit(1.0)) * F.lit(1.11), 2)

    if attr_type in {"number", "integer", "int", "long", "float", "double", "bigint", "smallint"}:
        if name == "year":
            return F.lit(2026) - (seed_index % 5)
        if name == "month":
            return (seed_index % 12) + F.lit(1)
        if name == "day_of_month":
            return (seed_index % 28) + F.lit(1)
        if name == "quarter":
            return (seed_index % 4) + F.lit(1)
        if name == "week_of_year":
            return (seed_index % 52) + F.lit(1)
        if any(token in name for token in {"count", "quantity", "size", "amount", "total", "score"}):
            return (seed_index % 1000) + F.lit(1)
        return seed_index.cast("long") + F.lit(1)

    if name in {"status", "state"} or "status" in name:
        return F.when((seed_index % 2) == 0, F.lit("active")).otherwise(F.lit("inactive"))

    return F.concat(
        F.lit(object_prefix),
        F.lit("-"),
        F.lit(clean(attribute.get("name"))),
        F.lit("-"),
        row_number_str,
    )


def _ensure_bucket(client, *, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
        return
    except Exception:
        pass

    try:
        client.create_bucket(Bucket=bucket)
    except Exception as exc:
        try:
            client.head_bucket(Bucket=bucket)
            return
        except Exception:
            raise SystemExit(f"Unable to create or access bucket '{bucket}': {exc}") from exc


def _clear_prefix(client, *, bucket: str, prefix: str) -> None:
    paginator = client.get_paginator("list_objects_v2")
    to_delete: list[dict[str, str]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents") or []:
            to_delete.append({"Key": item["Key"]})

    if not to_delete:
        return

    for offset in range(0, len(to_delete), 1000):
        client.delete_objects(Bucket=bucket, Delete={"Objects": to_delete[offset : offset + 1000], "Quiet": True})


def _wipe_aistor(client) -> list[str]:
    buckets = [bucket.get("Name", "") for bucket in client.list_buckets().get("Buckets", [])]
    wiped_buckets: list[str] = []

    for bucket_name in sorted(bucket for bucket in buckets if bucket and not bucket.startswith(".")):
        _clear_prefix(client, bucket=bucket_name, prefix="")
        client.delete_bucket(Bucket=bucket_name)
        wiped_buckets.append(bucket_name)

    return wiped_buckets


def _make_s3_client():
    return boto3_client(
        "s3",
        endpoint_url=_resolve_endpoint(),
        aws_access_key_id=_resolve_access_key(),
        aws_secret_access_key=_resolve_secret_key(),
        region_name=_resolve_region(),
        verify=_resolve_ssl_enabled(),
    )


def _upload_delivery_directory(client, *, bucket: str, key_prefix: str, local_dir: Path) -> int:
    if not local_dir.is_dir():
        raise SystemExit(f"Seed output directory does not exist: {local_dir}")

    uploaded = 0
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith(".") or path.name.startswith("_"):
            continue
        if path.name.endswith(".crc"):
            continue
        relative_key = path.relative_to(local_dir).as_posix()
        key = f"{key_prefix}/{relative_key}" if key_prefix else relative_key
        client.upload_file(str(path), bucket, key)
        uploaded += 1

    if uploaded < 1:
        raise SystemExit(f"No delivery files were produced under {local_dir}")

    return uploaded


def _count_objects(client, *, bucket: str, prefix: str) -> int:
    paginator = client.get_paginator("list_objects_v2")
    total = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        total += len(page.get("Contents") or [])
    return total


def _resolve_endpoint() -> str:
    endpoint = clean(os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL"))
    if not endpoint:
        raise SystemExit("DQ_S3_ENDPOINT/AWS_ENDPOINT_URL is required for AIStor upload")
    return endpoint


def _resolve_access_key() -> str:
    access_key = clean(os.getenv("DQ_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID"))
    if not access_key:
        raise SystemExit("DQ_S3_ACCESS_KEY/AWS_ACCESS_KEY_ID is required for AIStor upload")
    return access_key


def _resolve_secret_key() -> str:
    secret_key = clean(os.getenv("DQ_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY"))
    if not secret_key:
        raise SystemExit("DQ_S3_SECRET_KEY/AWS_SECRET_ACCESS_KEY is required for AIStor upload")
    return secret_key


def _resolve_region() -> str | None:
    region = clean(os.getenv("DQ_S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"))
    return region or None


def _resolve_ssl_enabled() -> bool:
    raw = clean(os.getenv("DQ_S3_SSL_ENABLED"))
    if raw:
        return truthy(raw)
    return _resolve_endpoint().lower().startswith("https://")


def _write_delivery_output(*, session, dataframe, local_output: Path, delivery_format: str, target_file_count: int, delivery_id: str) -> None:
    seed_format = clean(delivery_format).lower()
    if seed_format == "parquet":
        dataframe.write.mode("overwrite").parquet(str(local_output))
        return
    if seed_format == "csv":
        dataframe.coalesce(target_file_count).write.mode("overwrite").option("header", "true").csv(str(local_output))
        return
    if seed_format == "json":
        dataframe.coalesce(target_file_count).write.mode("overwrite").json(str(local_output))
        return

    if seed_format == "avro":
        dataframe.coalesce(target_file_count).write.mode("overwrite").format("avro").save(str(local_output))
        return

    if seed_format == "delta":
        dataframe.coalesce(target_file_count).write.mode("overwrite").format("delta").save(str(local_output))
        return

    if seed_format == "iceberg":
        warehouse_dir = local_output / "iceberg-warehouse"
        warehouse_dir.mkdir(parents=True, exist_ok=True)
        namespace = f"{ICEBERG_NAMESPACE}_{normalize_identifier(delivery_id)}"
        table_name = f"delivery_{normalize_identifier(delivery_id)}_{uuid.uuid4().hex[:8]}"
        table_identifier = f"{ICEBERG_CATALOG_NAME}.{namespace}.{table_name}"
        session.sql(f"CREATE NAMESPACE IF NOT EXISTS {ICEBERG_CATALOG_NAME}.{namespace}")
        dataframe.coalesce(target_file_count).writeTo(table_identifier).create()
        return

    raise SystemExit(f"Unsupported delivery_format for seeding: {seed_format!r}")


def _seed_plan(
    plan: DeliveryPlan,
    *,
    bucket: str,
    spark_bundle: tuple[Any, Any] | None = None,
) -> dict[str, Any]:
    session = None
    F = None
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        delivery_format = clean(plan.delivery_format).lower()
        warning = delivery_format_warning(delivery_format)
        if warning is not None:
            print(f"! {plan.delivery_id}: {warning}")
            return {
                "delivery_id": plan.delivery_id,
                "record_count": plan.record_count,
                "file_count": 0,
                "physical_output_uri": plan.physical_output_uri,
                "workspace": plan.workspace,
                "layer": plan.layer,
                "delivery_location": plan.delivery_location,
                "delivery_format": plan.delivery_format,
                "warning": warning,
            }

        temp_dir = tempfile.TemporaryDirectory(prefix=f"dq-delivery-{plan.delivery_id}-")
        local_output = Path(temp_dir.name)
        if delivery_format == "iceberg":
            (local_output / "iceberg-warehouse").mkdir(parents=True, exist_ok=True)

        session, F = _spark_session(delivery_format=delivery_format, iceberg_warehouse=local_output / "iceberg-warehouse" if delivery_format == "iceberg" else None)
        client = _make_s3_client()

        output_uri = normalize_s3_uri(plan.physical_output_uri)
        target_bucket, key_prefix = parse_s3a_uri(output_uri)
        bucket = target_bucket or bucket

        if spark_bundle is None:
            session, F = _spark_session(
                delivery_format=delivery_format,
                iceberg_warehouse=local_output / "iceberg-warehouse" if delivery_format == "iceberg" else None,
            )
        else:
            session, F = spark_bundle

        _ensure_bucket(client, bucket=bucket)

        _clear_prefix(client, bucket=bucket, prefix=key_prefix)

        seed_index_frame = session.range(plan.record_count).withColumnRenamed("id", "seed_index")
        seed_index = F.col("seed_index")
        object_token = clean(plan.data_object_id).replace("-", "_") or "object"
        version_token = clean(plan.data_object_version_id).replace("-", "_") or "version"
        base_epoch = int(to_utc_timestamp(plan.delivery_timestamp).timestamp())

        selected_columns = []
        for attribute in plan.attributes:
            column_name = clean(attribute.get("name"))
            if not column_name:
                raise SystemExit(f"Attribute row is missing name for delivery {plan.delivery_id}: {attribute}")
            selected_columns.append(
                _column_expression(
                    attribute=attribute,
                    seed_index=seed_index,
                    F=F,
                    object_token=object_token,
                    version_token=version_token,
                    base_epoch=base_epoch,
                ).alias(column_name)
            )
        target_file_count = max(1, min(plan.file_count, plan.record_count))
        dataframe = seed_index_frame.select(*selected_columns).coalesce(target_file_count)

        _write_delivery_output(
            session=session,
            dataframe=dataframe,
            local_output=local_output,
            delivery_format=delivery_format,
            target_file_count=target_file_count,
            delivery_id=plan.delivery_id,
        )

        uploaded_files = _upload_delivery_directory(client, bucket=bucket, key_prefix=key_prefix, local_dir=local_output)
        object_count = _count_objects(client, bucket=bucket, prefix=key_prefix)
        if object_count != uploaded_files:
            raise SystemExit(
                f"Uploaded object count mismatch for {plan.delivery_id}: expected {uploaded_files}, found {object_count}"
            )

        return {
            "delivery_id": plan.delivery_id,
            "record_count": plan.record_count,
            "file_count": uploaded_files,
            "physical_output_uri": plan.physical_output_uri,
            "workspace": plan.workspace,
            "layer": plan.layer,
            "delivery_location": plan.delivery_location,
            "delivery_format": plan.delivery_format,
        }
    finally:
        if spark_bundle is None and session is not None:
            try:
                session.stop()
            except Exception:
                pass
        if temp_dir is not None:
            temp_dir.cleanup()


def _seed_plans(plans: list[DeliveryPlan], *, bucket_override: str | None) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any] | None] = [None] * len(plans)
    plans_by_format: dict[str, list[tuple[int, DeliveryPlan]]] = {}
    format_order: list[str] = []

    for index, plan in enumerate(plans):
        delivery_format = clean(plan.delivery_format).lower()
        if delivery_format not in plans_by_format:
            format_order.append(delivery_format)
            plans_by_format[delivery_format] = []
        plans_by_format[delivery_format].append((index, plan))

    for delivery_format in format_order:
        grouped_plans = plans_by_format[delivery_format]
        warning = delivery_format_warning(delivery_format)
        if delivery_format == "iceberg" or warning is not None:
            for index, plan in grouped_plans:
                summaries[index] = _seed_plan(plan, bucket=bucket_override or plan.workspace)
            continue

        spark_bundle = _spark_session(delivery_format=delivery_format)
        try:
            for index, plan in grouped_plans:
                summaries[index] = _seed_plan(
                    plan,
                    bucket=bucket_override or plan.workspace,
                    spark_bundle=spark_bundle,
                )
        finally:
            session, _functions = spark_bundle
            try:
                session.stop()
            except Exception:
                pass

    return [summary for summary in summaries if summary is not None]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bucket",
        default=clean(os.getenv("DQ_DELIVERY_OUTPUT_BUCKET")),
        help="Optional AIStor bucket/container override; defaults to the data object's workspace",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print the planned uploads without writing anything")
    parser.add_argument("--delivery-id", action="append", dest="delivery_ids", help="Restrict generation to one or more delivery ids")
    parser.add_argument("--deliveries-csv", type=Path, default=DEFAULT_DELIVERIES_CSV)
    parser.add_argument("--notes-csv", type=Path, default=DEFAULT_NOTES_CSV)
    parser.add_argument("--objects-csv", type=Path, default=DEFAULT_OBJECTS_CSV)
    parser.add_argument("--versions-csv", type=Path, default=DEFAULT_VERSIONS_CSV)
    parser.add_argument("--attributes-csv", type=Path, default=DEFAULT_ATTRIBUTES_CSV)
    parser.add_argument("--purge-bucket", action="store_true", help="Delete all objects in the target bucket(s) before seeding")
    parser.add_argument("--wipe-aistor", action="store_true", help="Delete all user buckets in AIStor and exit without seeding")
    args = parser.parse_args()

    if args.wipe_aistor:
        if args.dry_run:
            print("Dry run: AIStor wipe requested; no buckets will be deleted.")
            return 0

        client = _make_s3_client()
        wiped_buckets = _wipe_aistor(client)
        print(f"Wiped {len(wiped_buckets)} AIStor bucket(s)")
        for bucket_name in wiped_buckets:
            print(f"- {bucket_name}")
        return 0

    requested_delivery_ids = {clean(value) for value in (args.delivery_ids or []) if clean(value)} or None
    plans = build_plans(
        bucket_override=clean(args.bucket) or None,
        delivery_ids=requested_delivery_ids,
        deliveries_csv=args.deliveries_csv,
        notes_csv=args.notes_csv,
        objects_csv=args.objects_csv,
        versions_csv=args.versions_csv,
        attributes_csv=args.attributes_csv,
    )

    if args.dry_run:
        print(f"Planned {len(plans)} delivery object upload(s):")
        for plan in plans:
            print(
                f"- {plan.delivery_id}: {plan.physical_output_uri} "
                f"({plan.record_count} rows, {plan.file_count} file(s), {len(plan.attributes)} columns, {plan.delivery_format})"
            )
            warning = delivery_format_warning(plan.delivery_format)
            if warning is not None:
                print(f"  warning: {warning}")
        if args.purge_bucket:
            print("Dry run: target buckets would be purged before seeding.")
        return 0

    if args.purge_bucket:
        client = _make_s3_client()
        purged_buckets = sorted({parse_s3a_uri(normalize_s3_uri(plan.physical_output_uri))[0] for plan in plans})
        for bucket_name in purged_buckets:
            _clear_prefix(client, bucket=bucket_name, prefix="")
        print(f"Purged {len(purged_buckets)} target bucket(s) before seeding")

    bucket_override = clean(args.bucket) or None
    if bucket_override:
        print(f"Seeding {len(plans)} delivery object(s) into bucket override {bucket_override}...")
    else:
        print(f"Seeding {len(plans)} delivery object(s) into workspace-derived buckets...")
    for summary in _seed_plans(plans, bucket_override=bucket_override):
        print(
            f"- {summary['delivery_id']}: {summary['physical_output_uri']} "
            f"({summary['record_count']} rows, {summary['file_count']} file(s))"
        )
        if summary.get("warning"):
            print(f"  warning: {summary['warning']}")

    print(f"Completed {len(plans)} delivery object upload(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())