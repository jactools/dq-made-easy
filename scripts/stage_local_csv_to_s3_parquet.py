#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from boto3 import client as boto3_client
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DQ_UTILS_SRC = ROOT_DIR.parent / "dq-utils" / "src"
if DQ_UTILS_SRC.is_dir() and str(DQ_UTILS_SRC) not in sys.path:
    sys.path.insert(0, str(DQ_UTILS_SRC))

from dq_utils.spark_runtime import build_spark_session_builder


DEFAULT_BUCKET_PREFIX = "dq-landing-zone-"


def clean(value: str | None) -> str:
    return str(value or "").strip()


def truthy(value: str) -> bool:
    return clean(value).lower() in {"1", "true", "yes", "y", "on"}


def normalize_bucket_segment(raw_value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]", "-", clean(raw_value).lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        raise SystemExit("workspace_id resolved to an invalid bucket suffix")
    return normalized


def resolve_bucket_prefix() -> str:
    raw_prefix = clean(os.getenv("DQ_GX_JOIN_PAIR_LANDING_ZONE_BUCKET_PREFIX") or DEFAULT_BUCKET_PREFIX).lower()
    normalized = re.sub(r"[^a-z0-9-]", "-", raw_prefix)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        raise SystemExit("DQ_GX_JOIN_PAIR_LANDING_ZONE_BUCKET_PREFIX resolved to an invalid bucket prefix")
    return normalized


def build_output_uri(*, workspace_id: str, case_id: str, role: str, version_id: str) -> str:
    bucket_name = f"{resolve_bucket_prefix()}-{normalize_bucket_segment(workspace_id)}"
    key_prefix = (
        "gx/join-pairs/local-csv-staging"
        f"/case_id={clean(case_id)}"
        f"/role={clean(role)}"
        f"/version_id={clean(version_id)}"
        "/format=parquet"
    )
    return f"s3://{bucket_name}/{key_prefix}"


def parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise SystemExit(f"Expected an s3:// URI, got: {uri}")
    key_prefix = parsed.path.lstrip("/")
    if not key_prefix:
        raise SystemExit(f"S3 URI must include a key prefix: {uri}")
    return parsed.netloc, key_prefix


def resolve_endpoint() -> str:
    endpoint = clean(os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL"))
    if not endpoint:
        raise SystemExit("DQ_S3_ENDPOINT/AWS_ENDPOINT_URL is required for S3-compatible storage upload")
    return endpoint


def resolve_access_key() -> str:
    access_key = clean(os.getenv("DQ_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID"))
    if not access_key:
        raise SystemExit("DQ_S3_ACCESS_KEY/AWS_ACCESS_KEY_ID is required for S3-compatible storage upload")
    return access_key


def resolve_secret_key() -> str:
    secret_key = clean(os.getenv("DQ_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY"))
    if not secret_key:
        raise SystemExit("DQ_S3_SECRET_KEY/AWS_SECRET_ACCESS_KEY is required for S3-compatible storage upload")
    return secret_key


def resolve_region() -> str | None:
    region = clean(os.getenv("DQ_S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"))
    return region or None


def resolve_ssl_enabled() -> bool:
    raw = clean(os.getenv("DQ_S3_SSL_ENABLED"))
    if raw:
        return truthy(raw)
    return resolve_endpoint().lower().startswith("https://")


def make_s3_client():
    return boto3_client(
        "s3",
        endpoint_url=resolve_endpoint(),
        aws_access_key_id=resolve_access_key(),
        aws_secret_access_key=resolve_secret_key(),
        region_name=resolve_region(),
        verify=resolve_ssl_enabled(),
    )


def ensure_bucket(client, *, bucket: str) -> None:
    try:
        client.create_bucket(Bucket=bucket)
    except Exception as exc:
        try:
            client.head_bucket(Bucket=bucket)
            return
        except Exception:
            raise SystemExit(f"Unable to create or access bucket '{bucket}': {exc}") from exc


def clear_prefix(client, *, bucket: str, prefix: str) -> None:
    paginator = client.get_paginator("list_objects_v2")
    to_delete: list[dict[str, str]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents") or []:
            to_delete.append({"Key": item["Key"]})

    for offset in range(0, len(to_delete), 1000):
        client.delete_objects(Bucket=bucket, Delete={"Objects": to_delete[offset : offset + 1000], "Quiet": True})


def upload_directory(client, *, bucket: str, key_prefix: str, local_dir: Path) -> None:
    if not local_dir.is_dir():
        raise SystemExit(f"Expected parquet output directory to exist: {local_dir}")

    uploaded = 0
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith(".") or path.name.startswith("_") or path.name.endswith(".crc"):
            continue
        key = f"{key_prefix}/{path.relative_to(local_dir).as_posix()}"
        client.upload_file(str(path), bucket, key)
        uploaded += 1

    if uploaded < 1:
        raise SystemExit(f"No parquet files were produced under {local_dir}")


def build_spark_session() -> SparkSession:
    return build_spark_session_builder(
        SparkSession=SparkSession,
        app_name="stage_local_csv_to_s3_parquet",
        master="local[*]",
        session_timezone="UTC",
    ).getOrCreate()


def require_columns(dataframe, required_columns: list[str], *, transform: str) -> None:
    missing = [column for column in required_columns if column not in dataframe.columns]
    if missing:
        raise SystemExit(f"Transform '{transform}' is missing required columns: {', '.join(missing)}")


def transform_teller_machine_left_reconcile(dataframe):
    transform_name = "teller_machine_left_reconcile"
    required = [
        "transaction_id",
        "timestamp",
        "status",
        "eur_5",
        "eur_10",
        "eur_20",
        "eur_50",
        "eur_100",
        "eur_200",
        "total_amount",
    ]
    require_columns(dataframe, required, transform=transform_name)

    amount_expr = (
        F.coalesce(F.col("eur_5").cast("decimal(18,2)"), F.lit(0).cast("decimal(18,2)")) * F.lit(5).cast("decimal(18,2)")
        + F.coalesce(F.col("eur_10").cast("decimal(18,2)"), F.lit(0).cast("decimal(18,2)")) * F.lit(10).cast("decimal(18,2)")
        + F.coalesce(F.col("eur_20").cast("decimal(18,2)"), F.lit(0).cast("decimal(18,2)")) * F.lit(20).cast("decimal(18,2)")
        + F.coalesce(F.col("eur_50").cast("decimal(18,2)"), F.lit(0).cast("decimal(18,2)")) * F.lit(50).cast("decimal(18,2)")
        + F.coalesce(F.col("eur_100").cast("decimal(18,2)"), F.lit(0).cast("decimal(18,2)")) * F.lit(100).cast("decimal(18,2)")
        + F.coalesce(F.col("eur_200").cast("decimal(18,2)"), F.lit(0).cast("decimal(18,2)")) * F.lit(200).cast("decimal(18,2)")
    )
    expected_total = F.col("total_amount").cast("decimal(18,2)")

    mismatch_count = (
        dataframe.withColumn("derived_amount", amount_expr)
        .withColumn("expected_total", expected_total)
        .where(F.col("derived_amount") != F.col("expected_total"))
        .count()
    )
    if mismatch_count:
        raise SystemExit(
            "ATM cash movement CSV contains rows where denomination totals do not match total_amount"
        )

    return dataframe.select(
        F.col("transaction_id").cast("string").alias("transaction_id"),
        amount_expr.alias("amount"),
        F.lit("EUR").alias("currency"),
        F.lit("cash").alias("payment_method"),
        F.col("status").cast("string").alias("status"),
        F.to_timestamp("timestamp").alias("timestamp"),
    )


def transform_teller_machine_right_reconcile(dataframe):
    transform_name = "teller_machine_right_reconcile"
    required = ["transaction_id", "customer_id", "timestamp", "total_amount", "currency"]
    require_columns(dataframe, required, transform=transform_name)
    return dataframe.select(
        F.col("transaction_id").cast("string").alias("order_id"),
        F.col("customer_id").cast("string").alias("customer_id"),
        F.to_date(F.to_timestamp("timestamp")).alias("order_date"),
        F.col("total_amount").cast("decimal(18,2)").alias("total_amount"),
        F.lit("completed").alias("status"),
        F.col("currency").cast("string").alias("currency"),
    )


def transform_teller_machine_gx_suite(dataframe):
    transform_name = "teller_machine_gx_suite"
    required = ["transaction_id", "timestamp", "total_amount"]
    require_columns(dataframe, required, transform=transform_name)
    return dataframe.select(
        F.col("transaction_id").cast("string").alias("transaction_id"),
        F.col("total_amount").cast("decimal(18,2)").alias("amount"),
        F.to_timestamp("timestamp").alias("transaction_date"),
    )


TRANSFER_MATCH_VALIDATOR_DELIVERY_IDS = ("del-30", "del-33")


def _filter_transfer_match_delivery_ids(dataframe, *, id_column: str, transform: str):
    require_columns(dataframe, [id_column], transform=transform)
    filtered = dataframe.where(F.col(id_column).isin(*TRANSFER_MATCH_VALIDATOR_DELIVERY_IDS))
    matched_ids = {
        str(row[id_column]).strip()
        for row in filtered.select(id_column).distinct().collect()
        if str(row[id_column]).strip()
    }
    expected_ids = set(TRANSFER_MATCH_VALIDATOR_DELIVERY_IDS)
    if matched_ids != expected_ids:
        missing = sorted(expected_ids - matched_ids)
        raise SystemExit(
            f"Transform '{transform}' could not resolve the seeded delivery ids: {', '.join(missing)}"
        )
    return filtered


def transform_transfer_match_delivery_rows_left(dataframe):
    transform_name = "transfer_match_delivery_rows_left"
    required = ["id", "record_count", "attributes_count"]
    require_columns(dataframe, required, transform=transform_name)
    filtered = _filter_transfer_match_delivery_ids(dataframe, id_column="id", transform=transform_name)
    return filtered.select(
        F.col("id").cast("string").alias("transaction_id"),
        F.col("record_count").cast("bigint").alias("row_count"),
        F.col("attributes_count").cast("bigint").alias("hash_count"),
    )


def transform_transfer_match_delivery_rows_right(dataframe):
    transform_name = "transfer_match_delivery_rows_right"
    required = ["id", "record_count", "attributes_count"]
    require_columns(dataframe, required, transform=transform_name)
    filtered = _filter_transfer_match_delivery_ids(dataframe, id_column="id", transform=transform_name)
    return filtered.select(
        F.col("id").cast("string").alias("order_id"),
        F.col("record_count").cast("bigint").alias("row_count"),
        F.col("attributes_count").cast("bigint").alias("hash_count"),
    )


def transform_transfer_match_delivery_note_left(dataframe):
    transform_name = "transfer_match_delivery_note_left"
    required = ["data_delivery_id", "checksum", "file_count"]
    require_columns(dataframe, required, transform=transform_name)
    filtered = _filter_transfer_match_delivery_ids(dataframe, id_column="data_delivery_id", transform=transform_name)
    return filtered.select(
        F.col("data_delivery_id").cast("string").alias("transaction_id"),
        F.col("checksum").cast("string").alias("file_hash"),
        F.col("file_count").cast("bigint").alias("hash_count"),
    )


def transform_transfer_match_delivery_note_right(dataframe):
    transform_name = "transfer_match_delivery_note_right"
    required = ["data_delivery_id", "checksum", "file_count"]
    require_columns(dataframe, required, transform=transform_name)
    filtered = _filter_transfer_match_delivery_ids(dataframe, id_column="data_delivery_id", transform=transform_name)
    return filtered.select(
        F.col("data_delivery_id").cast("string").alias("order_id"),
        F.col("checksum").cast("string").alias("target_file_hash"),
        F.col("file_count").cast("bigint").alias("hash_count"),
    )


def transform_customer_contact_left_join_consistency(dataframe):
    transform_name = "customer_contact_left_join_consistency"
    required = ["customer_id", "email", "created_at"]
    require_columns(dataframe, required, transform=transform_name)
    return dataframe.select(
        F.col("customer_id").cast("string").alias("customer_id"),
        F.col("email").cast("string").alias("email"),
        F.to_timestamp("created_at").alias("created_at"),
    )


def transform_customer_contact_right_join_consistency(dataframe):
    transform_name = "customer_contact_right_join_consistency"
    required = ["customer_id", "email_address", "last_contacted"]
    require_columns(dataframe, required, transform=transform_name)
    return dataframe.select(
        F.col("customer_id").cast("string").alias("customer_id"),
        F.col("email_address").cast("string").alias("email_address"),
        F.to_timestamp("last_contacted").alias("last_contacted"),
    )


def transform_customer_contact_high_invalid_email(dataframe):
    transform_name = "customer_contact_high_invalid_email"
    required = ["customer_id_prefix", "email", "created_at", "repeat_count"]
    require_columns(dataframe, required, transform=transform_name)

    normalized = dataframe.select(
        F.col("customer_id_prefix").cast("string").alias("customer_id_prefix"),
        F.col("email").cast("string").alias("email"),
        F.to_timestamp("created_at").alias("created_at"),
        F.col("repeat_count").cast("int").alias("repeat_count"),
    )
    invalid_repeat_rows = normalized.where(F.col("repeat_count").isNull() | (F.col("repeat_count") <= 0)).count()
    if invalid_repeat_rows:
        raise SystemExit(f"Transform '{transform_name}' requires repeat_count to be a positive integer")

    expanded = normalized.select(
        F.col("customer_id_prefix"),
        F.col("email"),
        F.col("created_at"),
        F.explode(F.sequence(F.lit(1), F.col("repeat_count"))).alias("row_index"),
    )

    return expanded.select(
        F.concat(
            F.col("customer_id_prefix"),
            F.lit("-"),
            F.lpad(F.col("row_index").cast("string"), 3, "0"),
        ).alias("customer_id"),
        F.col("email").cast("string").alias("email"),
        F.col("created_at"),
    )


TRANSFORMS = {
    "teller_machine_left_reconcile": transform_teller_machine_left_reconcile,
    "teller_machine_right_reconcile": transform_teller_machine_right_reconcile,
    "teller_machine_gx_suite": transform_teller_machine_gx_suite,
    "transfer_match_delivery_rows_left": transform_transfer_match_delivery_rows_left,
    "transfer_match_delivery_rows_right": transform_transfer_match_delivery_rows_right,
    "transfer_match_delivery_note_left": transform_transfer_match_delivery_note_left,
    "transfer_match_delivery_note_right": transform_transfer_match_delivery_note_right,
    "customer_contact_left_join_consistency": transform_customer_contact_left_join_consistency,
    "customer_contact_right_join_consistency": transform_customer_contact_right_join_consistency,
    "customer_contact_high_invalid_email": transform_customer_contact_high_invalid_email,
}


def stage_csv_to_parquet(*, input_csv: Path, transform: str, output_uri: str) -> dict[str, str]:
    if not input_csv.is_file():
        raise SystemExit(f"Input CSV does not exist: {input_csv}")
    if input_csv.stat().st_size < 1:
        raise SystemExit(f"Input CSV is empty: {input_csv}")
    if transform not in TRANSFORMS:
        raise SystemExit(f"Unsupported transform: {transform}")

    spark = build_spark_session()
    working_dir = Path(tempfile.mkdtemp(prefix="dq-local-csv-stage-"))
    output_dir = working_dir / "parquet-output"
    try:
        dataframe = (
            spark.read.option("header", "true")
            .option("inferSchema", "true")
            .option("timestampFormat", "yyyy-MM-dd HH:mm:ss")
            .csv(str(input_csv))
        )
        if dataframe.rdd.isEmpty():
            raise SystemExit(f"Input CSV has no rows: {input_csv}")

        transformed = TRANSFORMS[transform](dataframe)
        if transformed.rdd.isEmpty():
            raise SystemExit(f"Transform '{transform}' produced no rows for {input_csv}")

        transformed.write.mode("overwrite").parquet(str(output_dir))

        bucket, key_prefix = parse_s3_uri(output_uri)
        client = make_s3_client()
        ensure_bucket(client, bucket=bucket)
        clear_prefix(client, bucket=bucket, prefix=key_prefix)
        upload_directory(client, bucket=bucket, key_prefix=key_prefix, local_dir=output_dir)
        return {"output_uri": output_uri, "output_format": "parquet"}
    finally:
        spark.stop()
        shutil.rmtree(working_dir, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a local CSV into a transformed parquet dataset and upload it to S3-compatible storage.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--version-id", required=True)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--transform", required=True)
    parser.add_argument("--output-uri", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_uri = clean(args.output_uri) or build_output_uri(
        workspace_id=args.workspace_id,
        case_id=args.case_id,
        role=args.role,
        version_id=args.version_id,
    )
    result = stage_csv_to_parquet(
        input_csv=Path(args.input_csv).resolve(),
        transform=args.transform,
        output_uri=output_uri,
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())