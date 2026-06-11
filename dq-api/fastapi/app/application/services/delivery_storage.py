from __future__ import annotations

import os
from typing import Any, Protocol

from fastapi import HTTPException


class DeliveryStorageService(Protocol):
    def inspect(self, delivery_location: str) -> dict[str, Any]:
        ...


class S3DeliveryStorageService:
    def __init__(self) -> None:
        self._client = self._build_s3_client()

    @staticmethod
    def _parse_s3a_uri(uri: str) -> tuple[str, str]:
        raw = str(uri or "").strip()
        if raw.startswith("s3://"):
            raw = "s3a://" + raw[len("s3://") :]
        if not raw.startswith("s3a://"):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_delivery_location",
                    "message": "delivery_location must use s3:// or s3a://",
                    "delivery_location": uri,
                },
            )
        remainder = raw[len("s3a://") :]
        if not remainder:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_delivery_location",
                    "message": "delivery_location must include a bucket name",
                    "delivery_location": uri,
                },
            )
        if "/" not in remainder:
            return remainder, ""
        bucket, prefix = remainder.split("/", 1)
        return bucket, prefix

    @staticmethod
    def _build_s3_client() -> Any:
        try:
            import boto3
        except Exception as exc:  # pragma: no cover
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "dependency_missing",
                    "message": "Python package 'boto3' is required for delivery inventory checks",
                    "dependency": "boto3",
                },
            ) from exc

        endpoint = str(os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL") or "").strip()
        access_key = str(os.getenv("DQ_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
        secret_key = str(os.getenv("DQ_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
        region = str(os.getenv("DQ_S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "").strip() or "us-east-1"
        if not endpoint:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "s3_not_configured",
                    "message": "DQ_S3_ENDPOINT/AWS_ENDPOINT_URL is required for delivery inventory checks",
                },
            )
        if not (access_key and secret_key):
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "s3_not_configured",
                    "message": "DQ_S3_ACCESS_KEY/DQ_S3_SECRET_KEY (or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY) is required for delivery inventory checks",
                },
            )

        endpoint_lower = endpoint.lower()
        ssl_enabled = str(os.getenv("DQ_S3_SSL_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}
        if not ssl_enabled and endpoint_lower.startswith("https://"):
            ssl_enabled = True

        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            verify=ssl_enabled,
        )

    def _list_object_names(self, delivery_location: str) -> list[str]:
        bucket, prefix = self._parse_s3a_uri(delivery_location)
        normalized_prefix = str(prefix or "").lstrip("/")
        if normalized_prefix and not normalized_prefix.endswith("/"):
            normalized_prefix = f"{normalized_prefix}/"

        try:
            paginator = self._client.get_paginator("list_objects_v2")
            object_names: list[str] = []
            for page in paginator.paginate(Bucket=bucket, Prefix=normalized_prefix):
                for entry in page.get("Contents") or []:
                    key = str(entry.get("Key") or "").strip()
                    if not key:
                        continue
                    if normalized_prefix and key.startswith(normalized_prefix):
                        object_names.append(key[len(normalized_prefix) :])
                    else:
                        object_names.append(key)
            return object_names
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "delivery_inventory_check_failed",
                    "message": "Unable to check delivery location on S3-compatible storage",
                    "delivery_location": delivery_location,
                },
            ) from exc

    def inspect(self, delivery_location: str) -> dict[str, Any]:
        object_names = self._list_object_names(delivery_location)
        return {
            "storage_exists": bool(object_names),
            "storage_object_count": len(object_names),
            "file_names": object_names,
        }
