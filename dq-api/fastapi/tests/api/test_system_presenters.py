from __future__ import annotations

from datetime import UTC
from datetime import datetime
from types import SimpleNamespace

from app.api.presenters.system import build_suggestions_metrics_payload
from app.api.presenters.system import build_system_build_date
from app.api.presenters.system import build_system_info_payload
from app.api.presenters.system import serialize_system_entity
from app.domain.entities import SuggestionsMetricsSummaryEntity


def test_system_presenters_build_payloads() -> None:
    metrics = SuggestionsMetricsSummaryEntity(total=3, successful=2, failed=1, successRate=0.67, operations=[])
    assert serialize_system_entity(metrics)["total"] == 3
    assert build_suggestions_metrics_payload(metrics)["success"] is True
    assert build_suggestions_metrics_payload(metrics)["successful"] == 2

    assert build_system_build_date("2026-03-15T00:00:00Z") == "2026-03-15T00:00:00Z"
    fallback = build_system_build_date("", now=datetime(2026, 3, 20, 10, 30, tzinfo=UTC))
    assert fallback == "2026-03-20T10:30:00Z"

    payload = build_system_info_payload(
        db_info=SimpleNamespace(db_schema_version=None, db_schema_updated="today", db_git_commit="abc123"),
        app_config=SimpleNamespace(deploymentVerificationDate="2026-03-15", deploymentVerifiedBy="ops"),
        version_catalog={"apps": {"api": "1.2.3", "ui": "4.5.6"}, "components": {}},
        build_date="2026-03-15T00:00:00Z",
    )
    assert payload == {
        "api": {"version": "1.2.3", "buildDate": "2026-03-15T00:00:00Z"},
        "database": {
            "schemaVersion": "unknown",
            "schemaUpdated": "today",
            "schemaGitCommit": "abc123",
        },
        "deployment": {
            "deploymentVerificationDate": "2026-03-15",
            "deploymentVerifiedBy": "ops",
        },
        "versions": {"apps": {"api": "1.2.3", "ui": "4.5.6"}, "components": {}},
    }
