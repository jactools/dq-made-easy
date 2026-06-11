from __future__ import annotations

import types
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.application.services.delivery_storage import S3DeliveryStorageService


@pytest.fixture
def minimal_s3_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DQ_S3_ENDPOINT", "http://aistor.local:9000")
    monkeypatch.setenv("DQ_S3_ACCESS_KEY", "access")
    monkeypatch.setenv("DQ_S3_SECRET_KEY", "secret")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("DQ_S3_SSL_ENABLED", raising=False)


def _service_with_client(client: object) -> S3DeliveryStorageService:
    service = S3DeliveryStorageService.__new__(S3DeliveryStorageService)
    service._client = client
    return service


def test_parse_s3a_uri_accepts_s3_and_s3a_variants() -> None:
    assert S3DeliveryStorageService._parse_s3a_uri("s3://bucket/path/to/folder") == ("bucket", "path/to/folder")
    assert S3DeliveryStorageService._parse_s3a_uri("s3a://bucket") == ("bucket", "")


def test_parse_s3a_uri_rejects_non_s3_scheme() -> None:
    with pytest.raises(HTTPException) as error:
        S3DeliveryStorageService._parse_s3a_uri("file:///tmp/path")

    assert error.value.status_code == 422
    assert error.value.detail["error"] == "invalid_delivery_location"


def test_parse_s3a_uri_requires_bucket_name() -> None:
    with pytest.raises(HTTPException) as error:
        S3DeliveryStorageService._parse_s3a_uri("s3a://")

    assert error.value.status_code == 422
    assert error.value.detail["message"] == "delivery_location must include a bucket name"


def test_build_s3_client_requires_endpoint(monkeypatch: pytest.MonkeyPatch, minimal_s3_env: None) -> None:
    monkeypatch.delenv("DQ_S3_ENDPOINT", raising=False)
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)

    with pytest.raises(HTTPException) as error:
        S3DeliveryStorageService._build_s3_client()

    assert error.value.status_code == 503
    assert error.value.detail["error"] == "s3_not_configured"


def test_build_s3_client_requires_credentials(monkeypatch: pytest.MonkeyPatch, minimal_s3_env: None) -> None:
    monkeypatch.delenv("DQ_S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("DQ_S3_SECRET_KEY", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)

    with pytest.raises(HTTPException) as error:
        S3DeliveryStorageService._build_s3_client()

    assert error.value.status_code == 503
    assert error.value.detail["error"] == "s3_not_configured"


def test_build_s3_client_uses_env_and_enables_ssl_for_https_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    minimal_s3_env: None,
) -> None:
    monkeypatch.setenv("DQ_S3_ENDPOINT", "https://secure-aistor.local:9000")
    fake_client = object()
    boto3_stub = types.SimpleNamespace(client=Mock(return_value=fake_client))
    monkeypatch.setattr("builtins.__import__", __import__)
    monkeypatch.setitem(__import__("sys").modules, "boto3", boto3_stub)

    built = S3DeliveryStorageService._build_s3_client()

    assert built is fake_client
    boto3_stub.client.assert_called_once()
    call_kwargs = boto3_stub.client.call_args.kwargs
    assert call_kwargs["endpoint_url"] == "https://secure-aistor.local:9000"
    assert call_kwargs["verify"] is True


def test_list_object_names_uses_prefix_and_strips_directory_prefix() -> None:
    paginator = Mock()
    paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "path/to/folder/part-0001.parquet"},
                {"Key": "path/to/folder/part-0002.parquet"},
                {"Key": ""},
            ]
        }
    ]
    client = Mock()
    client.get_paginator.return_value = paginator
    service = _service_with_client(client)

    names = service._list_object_names("s3a://bucket/path/to/folder")

    client.get_paginator.assert_called_once_with("list_objects_v2")
    paginator.paginate.assert_called_once_with(Bucket="bucket", Prefix="path/to/folder/")
    assert names == ["part-0001.parquet", "part-0002.parquet"]


def test_list_object_names_maps_storage_errors_to_fail_fast_http_exception() -> None:
    paginator = Mock()
    paginator.paginate.side_effect = RuntimeError("backend down")
    client = Mock()
    client.get_paginator.return_value = paginator
    service = _service_with_client(client)

    with pytest.raises(HTTPException) as error:
        service._list_object_names("s3a://bucket/path")

    assert error.value.status_code == 503
    assert error.value.detail["error"] == "delivery_inventory_check_failed"


def test_inspect_reports_storage_existence_and_object_count() -> None:
    service = _service_with_client(client=Mock())
    service._list_object_names = Mock(return_value=["a.parquet", "b.parquet"])  # type: ignore[method-assign]

    result = service.inspect("s3a://bucket/path")

    assert result == {
        "storage_exists": True,
        "storage_object_count": 2,
        "file_names": ["a.parquet", "b.parquet"],
    }