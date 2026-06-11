from __future__ import annotations

import json
from typing import Any

from app.application.services.playground_source_bundles import PLAYGROUND_SOURCE_BUNDLES
from app.application.services.playground_source_bundles import PlaygroundSourceBundleIngestionService
from app.application.services.playground_source_bundles import PlaygroundSourceBundleSpec


class _FakeBucketMissingError(Exception):
    def __init__(self) -> None:
        super().__init__("NoSuchBucket")
        self.response = {"Error": {"Code": "NoSuchBucket"}}


class _FakeObjectMissingError(Exception):
    def __init__(self) -> None:
        super().__init__("NoSuchKey")
        self.response = {"Error": {"Code": "NoSuchKey"}}


class _FakeS3Client:
    def __init__(self) -> None:
        self.head_bucket_calls: list[dict[str, Any]] = []
        self.create_bucket_calls: list[dict[str, Any]] = []
        self.head_object_calls: list[dict[str, Any]] = []
        self.put_object_calls: list[dict[str, Any]] = []
        self.objects: dict[str, dict[str, Any]] = {}

    def head_bucket(self, **kwargs: Any) -> None:
        self.head_bucket_calls.append(kwargs)
        raise _FakeBucketMissingError()

    def create_bucket(self, **kwargs: Any) -> None:
        self.create_bucket_calls.append(kwargs)

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        self.head_object_calls.append(kwargs)
        key = str(kwargs.get("Key") or "")
        if key not in self.objects:
            raise _FakeObjectMissingError()
        return self.objects[key]

    def put_object(self, **kwargs: Any) -> None:
        self.put_object_calls.append(kwargs)
        self.objects[str(kwargs["Key"])] = kwargs


def _build_service(fake_client: _FakeS3Client) -> PlaygroundSourceBundleIngestionService:
    return PlaygroundSourceBundleIngestionService(
        bucket="dq-playground-source-bundles",
        prefix="playground-source-bundles",
        client_factory=lambda: fake_client,
    )


def test_ingest_bundle_stores_metadata_once() -> None:
    fake_client = _FakeS3Client()
    service = _build_service(fake_client)

    spec = PlaygroundSourceBundleSpec(
        bundle_id="demo-bundle",
        title="Demo Bundle",
        source_url="https://example.com/demo",
        license_name="Demo License",
        license_url="https://example.com/license",
        description="Demo bundle for tests",
    )

    first = service.ingest_bundle(spec)
    second = service.ingest_bundle(spec)

    assert first.status == "stored"
    assert second.status == "skipped"
    assert len(fake_client.create_bucket_calls) == 1
    assert len(fake_client.put_object_calls) == 1
    put_call = fake_client.put_object_calls[0]
    assert put_call["Bucket"] == "dq-playground-source-bundles"
    assert put_call["ContentType"] == "application/json"
    assert put_call["Metadata"]["bundle_id"] == "demo-bundle"
    assert put_call["Metadata"]["source_url"] == "https://example.com/demo"
    assert put_call["Metadata"]["license"] == "Demo License"
    assert put_call["Metadata"]["license_url"] == "https://example.com/license"
    assert put_call["Metadata"]["storage_kind"] == "playground_source_bundle"
    payload = json.loads(put_call["Body"].decode("utf-8"))
    assert payload["bundleId"] == "demo-bundle"
    assert payload["sourceUrl"] == "https://example.com/demo"
    assert payload["license"] == "Demo License"


def test_default_manifest_contains_expected_bundles() -> None:
    bundle_ids = [spec.bundle_id for spec in PLAYGROUND_SOURCE_BUNDLES]
    assert bundle_ids == [
        "ons-national-statistics",
        "abs-national-statistics",
        "stats-nz-national-statistics",
        "ecb-finance-terminology",
        "boe-finance-terminology",
    ]
