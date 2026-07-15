from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4


class InMemoryCompilerArtifactsMixin:

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
        history = self._compiler_artifacts_by_version.setdefault(rule_version_id, [])
        for row in history:
            row["isActive"] = False

        next_revision = max((int(row.get("compilerRevision", 0)) for row in history), default=0) + 1
        created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        artifact_id = f"rca-{uuid4().hex[:12]}"

        row = {
            "id": artifact_id,
            "ruleVersionId": rule_version_id,
            "compilerVersion": compiler_version,
            "compilerRevision": next_revision,
            "artifactKey": artifact_key,
            "artifactPayload": deepcopy(artifact_payload),
            "diagnosticsPayload": deepcopy(diagnostics_payload),
            "compileStatus": compile_status,
            "sourceFingerprint": source_fingerprint,
            "isActive": True,
            "createdAt": created_at,
        }
        history.append(row)
        history.sort(key=lambda item: int(item.get("compilerRevision", 0)), reverse=True)
        return deepcopy(row)

    async def get_active_compiler_artifact(self, rule_version_id: str) -> dict | None:
        history = self._compiler_artifacts_by_version.get(rule_version_id, [])
        for row in history:
            if bool(row.get("isActive")):
                return deepcopy(row)
        return None

    async def list_compiler_artifacts(self, rule_version_id: str) -> list[dict]:
        history = self._compiler_artifacts_by_version.get(rule_version_id, [])
        return [deepcopy(row) for row in history]
