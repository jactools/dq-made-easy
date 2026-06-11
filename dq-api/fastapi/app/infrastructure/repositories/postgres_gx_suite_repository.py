from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from sqlalchemy import and_, select, tuple_

from app.domain.entities import build_gx_artifact_envelope_entity
from app.domain.entities import build_gx_suite_status_history_entities
from app.domain.entities import GxArtifactEnvelopeEntity
from app.domain.entities import GxSuiteStatusHistoryEntity
from app.domain.interfaces.v1.gx_suite_repository import GxSuiteRepository
from app.infrastructure.orm.models import GxSuiteExecutionTargetMapRow
from app.infrastructure.orm.models import GxSuiteRegistryRow
from app.infrastructure.orm.models import GxSuiteRuleMapRow
from app.infrastructure.orm.models import GxSuiteStatusHistoryRow
from app.infrastructure.orm.session import session_scope


class PostgresGxSuiteRepository(GxSuiteRepository):
    """Postgres-backed GX suite retrieval repository."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def save_suite(
        self,
        *,
        envelope: GxArtifactEnvelopeEntity,
        status: str = "active",
        expected_existing_hash: str | None = None,
        saved_by: str | None = None,
        source_pipeline: str | None = None,
    ) -> GxArtifactEnvelopeEntity:
        envelope = build_gx_artifact_envelope_entity(envelope).model_dump(mode="python", by_alias=False, exclude_none=False)
        hashable_envelope = dict(envelope)
        hashable_envelope["savedBy"] = saved_by
        hashable_envelope["sourcePipeline"] = source_pipeline
        suite_id = str(envelope.get("suiteId") or "").strip()
        suite_version = int(envelope.get("suiteVersion") or 0)

        assignment_scope = envelope.get("assignmentScope") or {}
        if not isinstance(assignment_scope, dict):
            assignment_scope = {}

        compiled_from = envelope.get("compiledFrom") or {}
        if not isinstance(compiled_from, dict):
            compiled_from = {}

        resolved_scope = envelope.get("resolvedExecutionScope") or {}
        if not isinstance(resolved_scope, dict):
            resolved_scope = {}

        generated_at_raw = str(compiled_from.get("generatedAt") or "").strip()
        try:
            generated_at = datetime.fromisoformat(generated_at_raw.replace("Z", "+00:00"))
        except ValueError:
            generated_at = datetime.now(timezone.utc)

        target_ids = [
            str(item).strip()
            for item in (resolved_scope.get("dataObjectVersionIds") or [])
            if str(item).strip()
        ]
        rule_ids = [
            str(item).strip()
            for item in (compiled_from.get("ruleIds") or [])
            if str(item).strip()
        ]

        with session_scope(self.database_url) as session:
            row = session.execute(
                select(GxSuiteRegistryRow)
                .where(GxSuiteRegistryRow.suite_id == suite_id)
                .where(GxSuiteRegistryRow.suite_version == suite_version)
                .limit(1)
            ).scalar_one_or_none()

            if row is None:
                row = GxSuiteRegistryRow(
                    id=f"gx-reg-{uuid4().hex}",
                    suite_id=suite_id,
                    suite_version=suite_version,
                    artifact_version=str(envelope.get("artifactVersion") or "v1"),
                    status=status,
                    data_object_id=assignment_scope.get("dataObjectId"),
                    dataset_id=assignment_scope.get("datasetId"),
                    data_product_id=assignment_scope.get("dataProductId"),
                    gx_suite_json=envelope,
                    compiler_version=str(compiled_from.get("compilerVersion") or "unknown"),
                    generated_at=generated_at,
                    saved_by=saved_by,
                    source_pipeline=source_pipeline,
                )
                session.add(row)
                session.flush()
                session.add(GxSuiteStatusHistoryRow(
                    id=f"gx-hist-{uuid4().hex}",
                    suite_id=suite_id,
                    suite_version=suite_version,
                    from_status=None,
                    to_status=status,
                    changed_by=saved_by,
                    reason=None,
                ))
            else:
                key = [(suite_id, suite_version)]
                target_map = self._load_execution_targets(session, key)
                rule_map = self._load_rule_ids(session, key)
                existing_hash = self._hash_payload(
                    self._build_envelope(
                        row,
                        data_object_version_ids=target_map.get((suite_id, suite_version), []),
                        rule_ids=rule_map.get((suite_id, suite_version), []),
                    )
                )
                incoming_hash = self._hash_payload(hashable_envelope)
                if existing_hash != incoming_hash and expected_existing_hash != existing_hash:
                    raise ValueError("GX suite overwrite conflict: expected hash does not match current artifact")

                old_status = str(row.status or "")
                row.artifact_version = str(envelope.get("artifactVersion") or row.artifact_version or "v1")
                row.status = status
                row.data_object_id = assignment_scope.get("dataObjectId")
                row.dataset_id = assignment_scope.get("datasetId")
                row.data_product_id = assignment_scope.get("dataProductId")
                row.gx_suite_json = envelope
                row.compiler_version = str(compiled_from.get("compilerVersion") or row.compiler_version or "unknown")
                row.generated_at = generated_at
                row.saved_by = saved_by
                row.source_pipeline = source_pipeline
                if old_status != status:
                    session.add(GxSuiteStatusHistoryRow(
                        id=f"gx-hist-{uuid4().hex}",
                        suite_id=suite_id,
                        suite_version=suite_version,
                        from_status=old_status or None,
                        to_status=status,
                        changed_by=saved_by,
                        reason=None,
                    ))

            existing_targets = session.execute(
                select(GxSuiteExecutionTargetMapRow)
                .where(GxSuiteExecutionTargetMapRow.suite_id == suite_id)
                .where(GxSuiteExecutionTargetMapRow.suite_version == suite_version)
            ).scalars().all()
            for map_row in existing_targets:
                session.delete(map_row)

            existing_rules = session.execute(
                select(GxSuiteRuleMapRow)
                .where(GxSuiteRuleMapRow.suite_id == suite_id)
                .where(GxSuiteRuleMapRow.suite_version == suite_version)
            ).scalars().all()
            for map_row in existing_rules:
                session.delete(map_row)

            # Ensure unique constraints won't conflict when replacing map rows.
            session.flush()

            for target_id in dict.fromkeys(target_ids):
                session.add(
                    GxSuiteExecutionTargetMapRow(
                        id=f"gx-target-{uuid4().hex}",
                        suite_id=suite_id,
                        suite_version=suite_version,
                        data_object_version_id=target_id,
                    )
                )

            for rule_id in dict.fromkeys(rule_ids):
                session.add(
                    GxSuiteRuleMapRow(
                        id=f"gx-rule-{uuid4().hex}",
                        suite_id=suite_id,
                        suite_version=suite_version,
                        rule_id=rule_id,
                    )
                )

            session.commit()

            key = [(suite_id, suite_version)]
            target_map = self._load_execution_targets(session, key)
            rule_map = self._load_rule_ids(session, key)

        result = self._build_envelope(
            row,
            data_object_version_ids=target_map.get((suite_id, suite_version), []),
            rule_ids=rule_map.get((suite_id, suite_version), []),
        )
        result["artifactHash"] = self._hash_payload(result)
        return build_gx_artifact_envelope_entity(result)

    async def list_suites(
        self,
        *,
        data_object_id: str | None = None,
        data_object_version_id: str | None = None,
        dataset_id: str | None = None,
        data_product_id: str | None = None,
        status: str = "active",
        latest_only: bool = True,
    ) -> list[GxArtifactEnvelopeEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(GxSuiteRegistryRow).where(GxSuiteRegistryRow.status == status)

            if data_object_id:
                stmt = stmt.where(GxSuiteRegistryRow.data_object_id == data_object_id)
            elif dataset_id:
                stmt = stmt.where(GxSuiteRegistryRow.dataset_id == dataset_id)
            elif data_product_id:
                stmt = stmt.where(GxSuiteRegistryRow.data_product_id == data_product_id)
            elif data_object_version_id:
                stmt = (
                    stmt.join(
                        GxSuiteExecutionTargetMapRow,
                        and_(
                            GxSuiteExecutionTargetMapRow.suite_id == GxSuiteRegistryRow.suite_id,
                            GxSuiteExecutionTargetMapRow.suite_version == GxSuiteRegistryRow.suite_version,
                        ),
                    )
                    .where(GxSuiteExecutionTargetMapRow.data_object_version_id == data_object_version_id)
                )

            rows = session.execute(
                stmt.order_by(GxSuiteRegistryRow.suite_id.asc(), GxSuiteRegistryRow.suite_version.desc())
            ).scalars().all()

            selected_rows = rows
            if latest_only:
                latest_by_suite: dict[str, GxSuiteRegistryRow] = {}
                for row in rows:
                    if row.suite_id not in latest_by_suite:
                        latest_by_suite[row.suite_id] = row
                selected_rows = list(latest_by_suite.values())

            keys = [(row.suite_id, int(row.suite_version)) for row in selected_rows]
            target_map = self._load_execution_targets(session, keys)
            rule_map = self._load_rule_ids(session, keys)

        return [
            build_gx_artifact_envelope_entity(
                self._build_envelope(
                    row,
                    data_object_version_ids=target_map.get((row.suite_id, int(row.suite_version)), []),
                    rule_ids=rule_map.get((row.suite_id, int(row.suite_version)), []),
                )
            )
            for row in selected_rows
        ]

    async def list_suites_for_rule(
        self,
        *,
        rule_id: str,
        status: str = "active",
        latest_only: bool = True,
    ) -> list[GxArtifactEnvelopeEntity]:
        normalized_rule_id = str(rule_id or "").strip()
        if not normalized_rule_id:
            return []

        with session_scope(self.database_url) as session:
            stmt = (
                select(GxSuiteRegistryRow)
                .join(
                    GxSuiteRuleMapRow,
                    and_(
                        GxSuiteRuleMapRow.suite_id == GxSuiteRegistryRow.suite_id,
                        GxSuiteRuleMapRow.suite_version == GxSuiteRegistryRow.suite_version,
                    ),
                )
                .where(GxSuiteRegistryRow.status == status)
                .where(GxSuiteRuleMapRow.rule_id == normalized_rule_id)
                .order_by(GxSuiteRegistryRow.suite_id.asc(), GxSuiteRegistryRow.suite_version.desc())
            )

            rows = session.execute(stmt).scalars().all()

            selected_rows = rows
            if latest_only:
                latest_by_suite: dict[str, GxSuiteRegistryRow] = {}
                for row in rows:
                    if row.suite_id not in latest_by_suite:
                        latest_by_suite[row.suite_id] = row
                selected_rows = list(latest_by_suite.values())

            keys = [(row.suite_id, int(row.suite_version)) for row in selected_rows]
            target_map = self._load_execution_targets(session, keys)
            rule_map = self._load_rule_ids(session, keys)

        return [
            build_gx_artifact_envelope_entity(
                self._build_envelope(
                    row,
                    data_object_version_ids=target_map.get((row.suite_id, int(row.suite_version)), []),
                    rule_ids=rule_map.get((row.suite_id, int(row.suite_version)), []),
                )
            )
            for row in selected_rows
        ]

    async def get_suite_by_id(
        self,
        *,
        suite_id: str,
        suite_version: int | None = None,
        status: str = "active",
    ) -> GxArtifactEnvelopeEntity | None:
        with session_scope(self.database_url) as session:
            stmt = select(GxSuiteRegistryRow).where(
                GxSuiteRegistryRow.suite_id == suite_id,
                GxSuiteRegistryRow.status == status,
            )

            if suite_version is not None:
                stmt = stmt.where(GxSuiteRegistryRow.suite_version == suite_version)
            else:
                stmt = stmt.order_by(GxSuiteRegistryRow.suite_version.desc())

            row = session.execute(stmt.limit(1)).scalar_one_or_none()
            if row is None:
                return None

            key = [(row.suite_id, int(row.suite_version))]
            target_map = self._load_execution_targets(session, key)
            rule_map = self._load_rule_ids(session, key)

        return build_gx_artifact_envelope_entity(
            self._build_envelope(
                row,
                data_object_version_ids=target_map.get((row.suite_id, int(row.suite_version)), []),
                rule_ids=rule_map.get((row.suite_id, int(row.suite_version)), []),
            )
        )

    async def patch_suite_status(
        self,
        *,
        suite_id: str,
        new_status: str,
        suite_version: int | None = None,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> GxArtifactEnvelopeEntity | None:
        with session_scope(self.database_url) as session:
            stmt = select(GxSuiteRegistryRow).where(GxSuiteRegistryRow.suite_id == suite_id)

            if suite_version is not None:
                stmt = stmt.where(GxSuiteRegistryRow.suite_version == suite_version)
            else:
                stmt = stmt.order_by(GxSuiteRegistryRow.suite_version.desc())

            row = session.execute(stmt.limit(1)).scalar_one_or_none()
            if row is None:
                return None

            old_status = str(row.status or "")
            row.status = new_status
            session.add(GxSuiteStatusHistoryRow(
                id=f"gx-hist-{uuid4().hex}",
                suite_id=row.suite_id,
                suite_version=int(row.suite_version),
                from_status=old_status or None,
                to_status=new_status,
                changed_by=changed_by,
                reason=reason,
            ))
            session.commit()

            key = [(row.suite_id, int(row.suite_version))]
            target_map = self._load_execution_targets(session, key)
            rule_map = self._load_rule_ids(session, key)

        return build_gx_artifact_envelope_entity(
            self._build_envelope(
                row,
                data_object_version_ids=target_map.get((row.suite_id, int(row.suite_version)), []),
                rule_ids=rule_map.get((row.suite_id, int(row.suite_version)), []),
            )
        )

    async def list_suite_status_history(
        self,
        *,
        suite_id: str,
        suite_version: int | None = None,
    ) -> list[GxSuiteStatusHistoryEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(GxSuiteStatusHistoryRow).where(GxSuiteStatusHistoryRow.suite_id == suite_id)
            if suite_version is not None:
                stmt = stmt.where(GxSuiteStatusHistoryRow.suite_version == suite_version)
            stmt = stmt.order_by(GxSuiteStatusHistoryRow.changed_at.asc())
            rows = session.execute(stmt).scalars().all()

        result = []
        for r in rows:
            changed_at = r.changed_at
            if isinstance(changed_at, datetime):
                changed_at_str = changed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            else:
                changed_at_str = str(changed_at or "")
            result.append({
                "suiteId": r.suite_id,
                "suiteVersion": int(r.suite_version),
                "fromStatus": r.from_status,
                "toStatus": r.to_status,
                "changedBy": r.changed_by,
                "changedAt": changed_at_str,
                "reason": r.reason,
            })
        return build_gx_suite_status_history_entities(result)

    @staticmethod
    def _load_execution_targets(session, keys: list[tuple[str, int]]) -> dict[tuple[str, int], list[str]]:
        if not keys:
            return {}

        rows = session.execute(
            select(GxSuiteExecutionTargetMapRow).where(
                tuple_(
                    GxSuiteExecutionTargetMapRow.suite_id,
                    GxSuiteExecutionTargetMapRow.suite_version,
                ).in_(keys)
            )
        ).scalars().all()

        target_map: dict[tuple[str, int], list[str]] = defaultdict(list)
        for row in rows:
            target_map[(row.suite_id, int(row.suite_version))].append(row.data_object_version_id)
        return dict(target_map)

    @staticmethod
    def _load_rule_ids(session, keys: list[tuple[str, int]]) -> dict[tuple[str, int], list[str]]:
        if not keys:
            return {}

        rows = session.execute(
            select(GxSuiteRuleMapRow).where(
                tuple_(
                    GxSuiteRuleMapRow.suite_id,
                    GxSuiteRuleMapRow.suite_version,
                ).in_(keys)
            )
        ).scalars().all()

        rule_map: dict[tuple[str, int], list[str]] = defaultdict(list)
        for row in rows:
            rule_map[(row.suite_id, int(row.suite_version))].append(row.rule_id)
        return dict(rule_map)

    @staticmethod
    def _build_envelope(
        row: GxSuiteRegistryRow,
        *,
        data_object_version_ids: list[str],
        rule_ids: list[str],
    ) -> dict:
        raw_payload = row.gx_suite_json if isinstance(row.gx_suite_json, dict) else {}

        raw_assignment = raw_payload.get("assignmentScope") if isinstance(raw_payload, dict) else {}
        if not isinstance(raw_assignment, dict):
            raw_assignment = {}

        raw_resolved_scope = raw_payload.get("resolvedExecutionScope") if isinstance(raw_payload, dict) else {}
        if not isinstance(raw_resolved_scope, dict):
            raw_resolved_scope = {}

        raw_compiled_from = raw_payload.get("compiledFrom") if isinstance(raw_payload, dict) else {}
        if not isinstance(raw_compiled_from, dict):
            raw_compiled_from = {}

        raw_execution_hints = raw_payload.get("executionHints") if isinstance(raw_payload, dict) else {}
        if not isinstance(raw_execution_hints, dict):
            raw_execution_hints = {}

        raw_execution_contract = raw_payload.get("executionContract") if isinstance(raw_payload, dict) else {}
        if not isinstance(raw_execution_contract, dict):
            raw_execution_contract = {}

        gx_suite_payload = raw_payload.get("gxSuite") if isinstance(raw_payload.get("gxSuite"), dict) else raw_payload

        merged_version_ids = data_object_version_ids or list(
            raw_resolved_scope.get("dataObjectVersionIds") or []
        )
        merged_rule_ids = rule_ids or list(raw_compiled_from.get("ruleIds") or [])

        generated_at = row.generated_at
        if isinstance(generated_at, datetime):
            generated_at_utc = generated_at.astimezone(timezone.utc)
            generated_at_text = generated_at_utc.isoformat().replace("+00:00", "Z")
        else:
            generated_at_text = str(generated_at or "")

        primary_key_fields = raw_execution_hints.get("primaryKeyFields")
        if not isinstance(primary_key_fields, list):
            primary_key_fields = []

        business_key_fields = raw_execution_hints.get("businessKeyFields")
        if not isinstance(business_key_fields, list):
            business_key_fields = []

        normalized_execution_hints = dict(raw_execution_hints)
        normalized_execution_hints["recommendedEngine"] = "pyspark"
        normalized_execution_hints["primaryKeyFields"] = primary_key_fields
        normalized_execution_hints["businessKeyFields"] = business_key_fields

        return {
            "suiteId": row.suite_id,
            "suiteVersion": int(row.suite_version),
            "artifactVersion": str(row.artifact_version or "v1"),
            "assignmentScope": {
                "dataObjectId": row.data_object_id or raw_assignment.get("dataObjectId"),
                "datasetId": row.dataset_id or raw_assignment.get("datasetId"),
                "dataProductId": row.data_product_id or raw_assignment.get("dataProductId"),
            },
            "resolvedExecutionScope": {
                "dataObjectVersionIds": merged_version_ids,
            },
            "gxSuite": gx_suite_payload,
            "compiledFrom": {
                "ruleIds": merged_rule_ids,
                "compilerVersion": str(row.compiler_version),
                "generatedAt": generated_at_text,
            },
            "executionHints": normalized_execution_hints,
            "executionContract": raw_execution_contract or None,
            "savedBy": getattr(row, "saved_by", None),
            "sourcePipeline": getattr(row, "source_pipeline", None),
        }

    @staticmethod
    def _hash_payload(payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
