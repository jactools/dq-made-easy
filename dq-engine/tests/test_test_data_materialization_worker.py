"""Tests for test_data_materialization_worker."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_data_materialization_worker import WorkerConfig
from test_data_materialization_worker import _upload_directory_to_s3


class TestUploadDirectoryToS3:
    def test_https_s3_uses_repo_ca_bundle(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        bundle = tmp_path / "internal-ca-bundle.pem"
        bundle.write_text("dummy-ca", encoding="utf-8")
        monkeypatch.setenv("DQ_S3_CA_BUNDLE", str(bundle))

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "payload.json").write_text("{}", encoding="utf-8")

        captured: dict[str, object] = {}

        class FakeClient:
            def list_objects_v2(self, **kwargs):
                captured["list_objects_v2"] = kwargs
                return {"IsTruncated": False, "Contents": []}

            def delete_objects(self, **kwargs):
                captured["delete_objects"] = kwargs

            def upload_file(self, local_path: str, bucket: str, key: str) -> None:
                captured["upload_file"] = (local_path, bucket, key)

        fake_boto3 = SimpleNamespace(client=lambda *args, **kwargs: captured.update({"verify": kwargs.get("verify")}) or FakeClient())
        monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

        cfg = WorkerConfig(
            redis_url="redis://redis:6379/0",
            queue_key="dq-test-data:materialize",
            processing_queue_key="dq-test-data:materialize:processing",
            api_url="https://kong:8443",
            spark_master="local[*]",
            spark_ui_port=4040,
            output_prefix="s3a://dq-test-data",
            s3_endpoint="https://aistor:9000",
            s3_access_key="access",
            s3_secret_key="secret",
            s3_region="us-east-1",
            s3_path_style_access=True,
            s3_ssl_enabled=None,
            max_rows_per_request=10,
            poll_timeout_seconds=5,
        )

        _upload_directory_to_s3(cfg, local_dir=source_dir, bucket="bucket", key_prefix="prefix")

        assert captured["verify"] == str(bundle)
        assert captured["upload_file"][1:] == ("bucket", "prefix/payload.json")
