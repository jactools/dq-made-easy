from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.domain.entities.base import EntityModel


def serialize_system_entity(entity: EntityModel) -> dict[str, Any]:
    if isinstance(entity, Mapping):
        return dict(entity)
    return entity.model_dump(mode="json")


def build_system_build_date(build_date: str | None, *, now: datetime | None = None) -> str:
    normalized_build_date = str(build_date or "").strip()
    if normalized_build_date:
        return normalized_build_date
    current = now or datetime.now(timezone.utc)
    return current.isoformat().replace("+00:00", "Z")


def build_system_info_payload(
    *,
    db_info: Any,
    app_config: Any,
    version_catalog: dict[str, Any],
    build_date: str,
) -> dict[str, Any]:
    return {
        "api": {
            "version": version_catalog["apps"]["api"],
            "buildDate": build_date,
        },
        "database": {
            "schemaVersion": getattr(db_info, "db_schema_version", None) or "unknown",
            "schemaUpdated": getattr(db_info, "db_schema_updated", None),
            "schemaGitCommit": getattr(db_info, "db_git_commit", None),
        },
        "deployment": {
            "deploymentVerificationDate": getattr(app_config, "deploymentVerificationDate", None),
            "deploymentVerifiedBy": getattr(app_config, "deploymentVerifiedBy", None),
        },
        "versions": version_catalog,
    }


def build_suggestions_metrics_payload(metrics_summary: EntityModel) -> dict[str, Any]:
    return {
        "success": True,
        **serialize_system_entity(metrics_summary),
    }