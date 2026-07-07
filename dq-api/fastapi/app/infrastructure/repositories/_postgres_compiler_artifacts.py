from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.infrastructure.orm.models import RuleVersionCompilerArtifactRow
from app.infrastructure.orm.models import RuleVersionRow
from app.infrastructure.orm.session import session_scope


class CompilerArtifactsMixin:

    async def upsert_active_compiler_artifact(
        self,
        *,
        rule_version_id: str,
        compiler_version: str,
        artifact_key: str,
        artifact_payload: dict,
        diagnostics_payload: list[dict],
        compile_status: str,
        source_fingerprint: str,
    ) -> dict:
        now = datetime.now(UTC)
        artifact_id = f"rca-{uuid4().hex}"

        with session_scope(self.database_url) as session:
            version_row = session.execute(
                select(RuleVersionRow)
                .where(RuleVersionRow.id == rule_version_id)
                .limit(1)
            ).scalar_one_or_none()
            if version_row is None:
                raise LookupError(f"Rule version '{rule_version_id}' not found")

            existing_rows = session.execute(
                select(RuleVersionCompilerArtifactRow)
                .where(RuleVersionCompilerArtifactRow.rule_version_id == rule_version_id)
                .order_by(RuleVersionCompilerArtifactRow.compiler_revision.desc())
            ).scalars().all()

            for row in existing_rows:
                row.is_active = False

            next_revision = (max((int(row.compiler_revision or 0) for row in existing_rows), default=0)) + 1

            new_row = RuleVersionCompilerArtifactRow(
                id=artifact_id,
                rule_version_id=rule_version_id,
                compiler_version=compiler_version,
                compiler_revision=next_revision,
                artifact_key=artifact_key,
                artifact_payload=artifact_payload,
                diagnostics_payload={"items": diagnostics_payload},
                compile_status=compile_status,
                source_fingerprint=source_fingerprint,
                is_active=True,
                created_at=now,
            )
            session.add(new_row)
            session.commit()

        return self._serialize_compiler_artifact_row(new_row)

    async def get_active_compiler_artifact(self, rule_version_id: str) -> dict | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(RuleVersionCompilerArtifactRow)
                .where(RuleVersionCompilerArtifactRow.rule_version_id == rule_version_id)
                .where(RuleVersionCompilerArtifactRow.is_active.is_(True))
                .order_by(RuleVersionCompilerArtifactRow.compiler_revision.desc())
                .limit(1)
            ).scalar_one_or_none()

        if row is None:
            return None
        return self._serialize_compiler_artifact_row(row)

    async def list_compiler_artifacts(self, rule_version_id: str) -> list[dict]:
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(RuleVersionCompilerArtifactRow)
                .where(RuleVersionCompilerArtifactRow.rule_version_id == rule_version_id)
                .order_by(RuleVersionCompilerArtifactRow.compiler_revision.desc())
            ).scalars().all()

        return [self._serialize_compiler_artifact_row(row) for row in rows]
