"""Tests for spark_expectations_execution_adapter."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from spark_expectations_execution_adapter import _write_quarantine_artifact


class TestWriteQuarantineArtifact:
    def test_https_s3_uses_repo_ca_bundle(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        bundle = tmp_path / "internal-ca-bundle.pem"
        bundle.write_text("dummy-ca", encoding="utf-8")
        monkeypatch.setenv("DQ_S3_ENDPOINT", "https://aistor:9000")
        monkeypatch.setenv("DQ_S3_CA_BUNDLE", str(bundle))

        captured: dict[str, object] = {}

        class FakeClient:
            def upload_file(self, temp_path: str, bucket: str, key: str) -> None:
                captured["upload_file"] = (temp_path, bucket, key)

        fake_boto3 = SimpleNamespace(client=lambda *args, **kwargs: captured.update({"verify": kwargs.get("verify")}) or FakeClient())
        monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

        result = _write_quarantine_artifact(
            [{"id": 1}],
            quarantine_uri="s3a://bucket/out.json",
            execution_metadata={"rule_id": "r1"},
        )

        assert result is not None
        assert result["storage_kind"] == "s3"
        assert captured["verify"] == str(bundle)
        assert captured["upload_file"][1:] == ("bucket", "out.json")
