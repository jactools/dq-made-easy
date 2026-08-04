"""Tests for the local CSV-to-Parquet staging adapter.

classification: unit
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import stage_local_csv_to_s3_parquet as staging


pytestmark = pytest.mark.unit


class TestBuildDqCsvToParquetRunner:
    def test_runner_passes_selected_transform_to_shared_stage(self) -> None:
        config = SimpleNamespace(
            input_csv=Path("/tmp/input.csv"),
            output_uri="s3://bucket/prefix/",
        )
        result = MagicMock()

        with patch.object(staging, "stage_csv_to_parquet", return_value=result) as mock_stage:
            runner = staging.build_dq_csv_to_parquet_runner("customer_contact_high_invalid_email")
            returned = runner(config)

        assert returned is result
        mock_stage.assert_called_once_with(
            input_csv=Path("/tmp/input.csv"),
            transform="customer_contact_high_invalid_email",
            output_uri="s3://bucket/prefix/",
        )


class TestMain:
    def test_main_registers_consumer_runner_and_delegates_to_cli(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_args = SimpleNamespace(
            workspace_id="ws-1",
            case_id="case-1",
            role="left",
            version_id="ver-1",
            input_csv="/tmp/input.csv",
            transform="customer_contact_high_invalid_email",
            engine_type="dq_spark",
            output_uri="",
        )
        monkeypatch.setattr(staging, "parse_args", lambda: fake_args)

        expected_result = MagicMock()
        expected_result.as_dict.return_value = {
            "output_uri": "s3://dq-landing-zone-ws-1/gx/join-pairs/local-csv-staging/case_id=case-1/role=left/version_id=ver-1/format=parquet",
            "output_format": "parquet",
            "row_count": 2,
            "file_count": 1,
            "bytes_uploaded": 0,
        }

        with patch.object(staging, "register_csv_to_parquet_runner") as mock_register, patch.object(
            staging, "execute_csv_parquet_job", return_value=expected_result
        ) as mock_execute, patch.object(staging, "resolve_endpoint", return_value="https://minio:9000"), patch.object(
            staging, "resolve_access_key", return_value="admin"
        ), patch.object(staging, "resolve_secret_key", return_value="password"), patch.object(
            staging, "resolve_region", return_value=None
        ), patch.object(staging, "resolve_ssl_enabled", return_value=True):
            exit_code = staging.main()

        assert exit_code == 0
        mock_register.assert_called_once()
        assert mock_register.call_args.args[0] == "dq_spark"
        assert callable(mock_register.call_args.args[1])
        mock_execute.assert_called_once()
        config = mock_execute.call_args.args[0]
        assert config.engine_type == "dq_spark"
        assert config.input_csv == Path("/tmp/input.csv").resolve()
