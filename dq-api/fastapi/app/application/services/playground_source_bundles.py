from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Sequence


@dataclass(frozen=True)
class PlaygroundSourceBundleSpec:
    bundle_id: str
    title: str
    source_url: str
    license_name: str
    license_url: str | None = None
    description: str = ""


@dataclass(frozen=True)
class PlaygroundSourceBundleRecord:
    bundle_id: str
    object_key: str
    content_sha256: str
    status: str
    stored_at: str


PLAYGROUND_SOURCE_BUNDLES: tuple[PlaygroundSourceBundleSpec, ...] = (
    PlaygroundSourceBundleSpec(
        bundle_id="ons-national-statistics",
        title="Office for National Statistics",
        source_url="https://www.ons.gov.uk/",
        license_name="Open Government Licence v3.0",
        license_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        description="UK population, inflation, GDP, and labour-market series.",
    ),
    PlaygroundSourceBundleSpec(
        bundle_id="abs-national-statistics",
        title="Australian Bureau of Statistics",
        source_url="https://www.abs.gov.au/",
        license_name="Creative Commons Attribution 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        description="Population, CPI, GDP, earnings, unemployment, and regional datasets.",
    ),
    PlaygroundSourceBundleSpec(
        bundle_id="stats-nz-national-statistics",
        title="Stats NZ",
        source_url="https://www.stats.govt.nz/",
        license_name="Creative Commons Attribution 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        description="Population, GDP, CPI, unemployment, trade, and regional summaries.",
    ),
    PlaygroundSourceBundleSpec(
        bundle_id="ecb-finance-terminology",
        title="ECB Data Portal",
        source_url="https://data.ecb.europa.eu/",
        license_name="ECB free access and free reuse",
        description="Euro exchange rates, yield curves, money market reporting, investment funds, monetary financial institutions, and banking-supervision-related statistics.",
    ),
    PlaygroundSourceBundleSpec(
        bundle_id="boe-finance-terminology",
        title="Bank of England Database",
        source_url="https://www.bankofengland.co.uk/boeapps/database/",
        license_name="Open Government Licence v3.0",
        license_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        description="Exchange rates, yield curves, SONIA, money and credit, capital issuance, financial derivative positions, monetary financial institutions, and banking-sector regulatory capital.",
    ),
)


class PlaygroundSourceBundleIngestionError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _client_error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error")
        if isinstance(error, dict):
            code = error.get("Code")
            if code:
                return str(code)
    return None


def _derive_s3_ssl_enabled(endpoint: str) -> bool:
    explicit = _clean(os.getenv("DQ_S3_SSL_ENABLED"))
    if explicit:
        return explicit.lower() in {"1", "true", "yes", "y", "on"}
    return endpoint.lower().startswith("https://")


def _build_s3_client_from_env() -> Any:
    try:
        import boto3
    except Exception as exc:  # pragma: no cover - environment dependent
        raise PlaygroundSourceBundleIngestionError(
            "Python package 'boto3' is required for playground source bundle ingestion",
            status_code=503,
        ) from exc

    endpoint = _clean(os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL"))
    access_key = _clean(os.getenv("DQ_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID"))
    secret_key = _clean(os.getenv("DQ_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY"))
    region = _clean(os.getenv("DQ_S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")) or "us-east-1"

    if not endpoint:
        raise PlaygroundSourceBundleIngestionError(
            "DQ_S3_ENDPOINT/AWS_ENDPOINT_URL is required for playground source bundle ingestion",
            status_code=503,
        )
    if not (access_key and secret_key):
        raise PlaygroundSourceBundleIngestionError(
            "DQ_S3_ACCESS_KEY/DQ_S3_SECRET_KEY (or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY) are required for playground source bundle ingestion",
            status_code=503,
        )

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        verify=_derive_s3_ssl_enabled(endpoint),
    )


class PlaygroundSourceBundleIngestionService:
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._bucket = _clean(bucket)
        self._prefix = _clean(prefix).strip("/")
        self._client_factory = client_factory or _build_s3_client_from_env
        self._client = self._client_factory()
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self) -> None:
        if not self._bucket:
            raise PlaygroundSourceBundleIngestionError("playground source bundle ingestion requires a bucket name")

        try:
            self._client.head_bucket(Bucket=self._bucket)
            return
        except Exception as exc:
            error_code = _client_error_code(exc)
            if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                raise

        create_kwargs: dict[str, Any] = {"Bucket": self._bucket}
        try:
            self._client.create_bucket(**create_kwargs)
        except Exception as exc:
            error_code = _client_error_code(exc)
            if error_code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                raise

    def _object_key_for(self, spec: PlaygroundSourceBundleSpec) -> str:
        source_hash = hashlib.sha256(spec.source_url.encode("utf-8")).hexdigest()
        key_parts = [
            self._prefix or "playground-source-bundles",
            spec.bundle_id,
            f"source-{source_hash}.json",
        ]
        return "/".join(part for part in key_parts if part)

    def _build_record(self, spec: PlaygroundSourceBundleSpec, *, object_key: str, content_hash: str, status: str) -> PlaygroundSourceBundleRecord:
        return PlaygroundSourceBundleRecord(
            bundle_id=spec.bundle_id,
            object_key=object_key,
            content_sha256=content_hash,
            status=status,
            stored_at=datetime.now(UTC).isoformat(),
        )

    def _build_payload(self, spec: PlaygroundSourceBundleSpec, *, object_key: str) -> dict[str, Any]:
        return {
            "bundleId": spec.bundle_id,
            "title": spec.title,
            "sourceUrl": spec.source_url,
            "license": spec.license_name,
            "licenseUrl": spec.license_url,
            "description": spec.description,
            "objectKey": object_key,
            "storedAt": datetime.now(UTC).isoformat(),
            "storageKind": "playground_source_bundle",
        }

    def ingest_bundle(self, spec: PlaygroundSourceBundleSpec) -> PlaygroundSourceBundleRecord:
        object_key = self._object_key_for(spec)
        payload = self._build_payload(spec, object_key=object_key)
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        content_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        try:
            self._client.head_object(Bucket=self._bucket, Key=object_key)
            return self._build_record(spec, object_key=object_key, content_hash=content_hash, status="skipped")
        except Exception as exc:
            error_code = _client_error_code(exc)
            if error_code not in {"404", "NoSuchKey", "NotFound"}:
                raise

        self._client.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=canonical_json.encode("utf-8"),
            ContentType="application/json",
            Metadata={
                "bundle_id": spec.bundle_id,
                "source_url": spec.source_url,
                "license": spec.license_name,
                "license_url": spec.license_url or "",
                "storage_kind": "playground_source_bundle",
                "content_sha256": content_hash,
            },
        )
        return self._build_record(spec, object_key=object_key, content_hash=content_hash, status="stored")

    def ingest_bundles(self, specs: Sequence[PlaygroundSourceBundleSpec]) -> list[PlaygroundSourceBundleRecord]:
        return [self.ingest_bundle(spec) for spec in specs]


def build_playground_source_bundle_ingestion_service(
    *,
    bucket: str | None = None,
    prefix: str | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> PlaygroundSourceBundleIngestionService:
    resolved_bucket = _clean(bucket or os.getenv("DQ_PLAYGROUND_SOURCE_BUNDLE_BUCKET") or "dq-playground-source-bundles")
    resolved_prefix = _clean(prefix or os.getenv("DQ_PLAYGROUND_SOURCE_BUNDLE_PREFIX") or "playground-source-bundles")
    return PlaygroundSourceBundleIngestionService(
        bucket=resolved_bucket,
        prefix=resolved_prefix,
        client_factory=client_factory,
    )


def ingest_default_playground_source_bundles(
    *,
    bucket: str | None = None,
    prefix: str | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> list[PlaygroundSourceBundleRecord]:
    service = build_playground_source_bundle_ingestion_service(
        bucket=bucket,
        prefix=prefix,
        client_factory=client_factory,
    )
    return service.ingest_bundles(PLAYGROUND_SOURCE_BUNDLES)
