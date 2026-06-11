from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryAccessGrantEntity
from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryExchangeSnapshotEntity
from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryExternalPartyEntity
from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryGoverningScopeEntity
from app.domain.interfaces.v1.federated_metadata_registry_repository import FederatedMetadataRegistryRepository
from app.infrastructure.orm.models import FederatedMetadataRegistryAccessGrantRow
from app.infrastructure.orm.models import FederatedMetadataRegistryExternalPartyRow
from app.infrastructure.orm.models import FederatedMetadataRegistryExchangeSnapshotRow
from app.infrastructure.orm.session import session_scope


def _external_party_entity_from_row(row: FederatedMetadataRegistryExternalPartyRow) -> FederatedMetadataRegistryExternalPartyEntity:
    return FederatedMetadataRegistryExternalPartyEntity(
        id=str(row.id or ""),
        workspace_id=str(row.workspace_id or "").strip() or None,
        tenant_id=str(row.tenant_id or "").strip() or None,
        display_name=str(row.display_name or "").strip() or None,
        governing_scope=FederatedMetadataRegistryGoverningScopeEntity.model_validate(row.governing_scope_json or {}),
        approval_status=str(row.approval_status or "pending").strip() or "pending",
        approved_at=row.approved_at.isoformat() if row.approved_at is not None else None,
        approved_by=str(row.approved_by or "").strip() or None,
        approval_notes=str(row.approval_notes or "").strip() or None,
        registered_at=row.registered_at.isoformat(),
        registered_by=str(row.registered_by or "").strip() or None,
        correlation_id=str(row.correlation_id or "").strip() or None,
    )


def _access_grant_entity_from_row(row: FederatedMetadataRegistryAccessGrantRow) -> FederatedMetadataRegistryAccessGrantEntity:
    return FederatedMetadataRegistryAccessGrantEntity(
        id=str(row.id or ""),
        external_party_id=str(row.external_party_id or ""),
        target_kind=str(row.target_kind or ""),
        target_id=str(row.target_id or ""),
        subscribed=bool(row.subscribed),
        can_push=bool(row.can_push),
        can_pull=bool(row.can_pull),
        notes=str(row.notes or "").strip() or None,
        granted_at=row.granted_at.isoformat(),
        granted_by=str(row.granted_by or "").strip() or None,
        correlation_id=str(row.correlation_id or "").strip() or None,
    )


def _snapshot_entity_from_row(row: FederatedMetadataRegistryExchangeSnapshotRow) -> FederatedMetadataRegistryExchangeSnapshotEntity:
    return FederatedMetadataRegistryExchangeSnapshotEntity(
        id=str(row.id or ""),
        package_id=str(row.package_id or ""),
        package_kind=str(row.package_kind or "federated_metadata_package"),
        exchange_kind=str(row.exchange_kind or "push"),
        workspace_id=str(row.workspace_id or ""),
        data_product_id=str(row.data_product_id or "").strip() or None,
        captured_at=row.captured_at.isoformat(),
        captured_by=str(row.captured_by or "").strip() or None,
        correlation_id=str(row.correlation_id or "").strip() or None,
        accepted=bool(row.accepted),
        validation_error=str(row.validation_error or "").strip() or None,
        manifest=dict(row.manifest_json or {}),
        package=dict(row.package_json or {}),
    )


class PostgresFederatedMetadataRegistryRepository(FederatedMetadataRegistryRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def record_federated_metadata_registry_external_party(
        self,
        party: FederatedMetadataRegistryExternalPartyEntity,
    ) -> FederatedMetadataRegistryExternalPartyEntity:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(FederatedMetadataRegistryExternalPartyRow).where(FederatedMetadataRegistryExternalPartyRow.id == str(party.id).strip())
            ).scalar_one_or_none()
            if row is None:
                row = FederatedMetadataRegistryExternalPartyRow(id=str(party.id).strip())
                session.add(row)

            row.workspace_id = str(party.workspace_id or "").strip() or None
            row.tenant_id = str(party.tenant_id or "").strip() or None
            row.display_name = str(party.display_name or "").strip() or None
            row.governing_scope_json = party.governing_scope.model_dump(mode="python", by_alias=False, exclude_none=False)
            row.approval_status = str(party.approval_status or "pending").strip() or "pending"
            row.approved_at = _parse_iso_datetime(party.approved_at) if str(party.approved_at or "").strip() else None
            row.approved_by = str(party.approved_by or "").strip() or None
            row.approval_notes = str(party.approval_notes or "").strip() or None
            row.registered_at = _parse_iso_datetime(party.registered_at)
            row.registered_by = str(party.registered_by or "").strip() or None
            row.correlation_id = str(party.correlation_id or "").strip() or None
            session.commit()
            return _external_party_entity_from_row(row)

    def list_federated_metadata_registry_external_parties(
        self,
        *,
        party_id: str | None = None,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
        approval_status: str | None = None,
        limit: int = 20,
    ) -> Sequence[FederatedMetadataRegistryExternalPartyEntity]:
        safe_limit = max(1, min(int(limit), 100))
        with session_scope(self.database_url) as session:
            stmt = select(FederatedMetadataRegistryExternalPartyRow)
            if party_id is not None:
                stmt = stmt.where(FederatedMetadataRegistryExternalPartyRow.id == str(party_id))
            if workspace_id is not None:
                stmt = stmt.where(FederatedMetadataRegistryExternalPartyRow.workspace_id == str(workspace_id))
            if tenant_id is not None:
                stmt = stmt.where(FederatedMetadataRegistryExternalPartyRow.tenant_id == str(tenant_id))
            if approval_status is not None:
                stmt = stmt.where(FederatedMetadataRegistryExternalPartyRow.approval_status == str(approval_status))
            rows = session.execute(
                stmt.order_by(
                    FederatedMetadataRegistryExternalPartyRow.registered_at.desc(),
                    FederatedMetadataRegistryExternalPartyRow.id.desc(),
                ).limit(safe_limit)
            ).scalars().all()
            return [_external_party_entity_from_row(row) for row in rows]

    def record_federated_metadata_registry_access_grant(
        self,
        grant: FederatedMetadataRegistryAccessGrantEntity,
    ) -> FederatedMetadataRegistryAccessGrantEntity:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(FederatedMetadataRegistryAccessGrantRow).where(FederatedMetadataRegistryAccessGrantRow.id == str(grant.id).strip())
            ).scalar_one_or_none()
            if row is None:
                row = FederatedMetadataRegistryAccessGrantRow(id=str(grant.id).strip())
                session.add(row)

            row.external_party_id = str(grant.external_party_id or "").strip()
            row.target_kind = str(grant.target_kind or "").strip()
            row.target_id = str(grant.target_id or "").strip()
            row.subscribed = bool(grant.subscribed)
            row.can_push = bool(grant.can_push)
            row.can_pull = bool(grant.can_pull)
            row.notes = str(grant.notes or "").strip() or None
            row.granted_at = _parse_iso_datetime(grant.granted_at)
            row.granted_by = str(grant.granted_by or "").strip() or None
            row.correlation_id = str(grant.correlation_id or "").strip() or None
            session.commit()
            return _access_grant_entity_from_row(row)

    def list_federated_metadata_registry_access_grants(
        self,
        *,
        party_id: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        limit: int = 20,
    ) -> Sequence[FederatedMetadataRegistryAccessGrantEntity]:
        safe_limit = max(1, min(int(limit), 100))
        with session_scope(self.database_url) as session:
            stmt = select(FederatedMetadataRegistryAccessGrantRow)
            if party_id is not None:
                stmt = stmt.where(FederatedMetadataRegistryAccessGrantRow.external_party_id == str(party_id))
            if target_kind is not None:
                stmt = stmt.where(FederatedMetadataRegistryAccessGrantRow.target_kind == str(target_kind))
            if target_id is not None:
                stmt = stmt.where(FederatedMetadataRegistryAccessGrantRow.target_id == str(target_id))
            rows = session.execute(
                stmt.order_by(
                    FederatedMetadataRegistryAccessGrantRow.granted_at.desc(),
                    FederatedMetadataRegistryAccessGrantRow.id.desc(),
                ).limit(safe_limit)
            ).scalars().all()
            return [_access_grant_entity_from_row(row) for row in rows]

    def record_federated_metadata_registry_exchange_snapshot(
        self,
        snapshot: FederatedMetadataRegistryExchangeSnapshotEntity,
    ) -> FederatedMetadataRegistryExchangeSnapshotEntity:
        with session_scope(self.database_url) as session:
            row = FederatedMetadataRegistryExchangeSnapshotRow(
                id=str(snapshot.id).strip(),
                package_id=str(snapshot.package_id).strip(),
                package_kind=str(snapshot.package_kind or "federated_metadata_package").strip() or "federated_metadata_package",
                exchange_kind=str(snapshot.exchange_kind).strip(),
                workspace_id=str(snapshot.workspace_id).strip(),
                data_product_id=str(snapshot.data_product_id or "").strip() or None,
                captured_at=_parse_iso_datetime(snapshot.captured_at),
                captured_by=str(snapshot.captured_by or "").strip() or None,
                correlation_id=str(snapshot.correlation_id or "").strip() or None,
                accepted=bool(snapshot.accepted),
                validation_error=str(snapshot.validation_error or "").strip() or None,
                package_json=dict(snapshot.package or {}),
                manifest_json=dict(snapshot.manifest or {}),
            )
            session.add(row)
            session.commit()
            return _snapshot_entity_from_row(row)

    def list_federated_metadata_registry_exchange_snapshots(
        self,
        *,
        workspace_id: str | None = None,
        data_product_id: str | None = None,
        limit: int = 20,
    ) -> Sequence[FederatedMetadataRegistryExchangeSnapshotEntity]:
        safe_limit = max(1, min(int(limit), 100))
        with session_scope(self.database_url) as session:
            stmt = select(FederatedMetadataRegistryExchangeSnapshotRow)
            if workspace_id is not None:
                stmt = stmt.where(FederatedMetadataRegistryExchangeSnapshotRow.workspace_id == str(workspace_id))
            if data_product_id is not None:
                stmt = stmt.where(FederatedMetadataRegistryExchangeSnapshotRow.data_product_id == str(data_product_id))
            rows = session.execute(
                stmt.order_by(
                    FederatedMetadataRegistryExchangeSnapshotRow.captured_at.desc(),
                    FederatedMetadataRegistryExchangeSnapshotRow.id.desc(),
                ).limit(safe_limit)
            ).scalars().all()
            return [_snapshot_entity_from_row(row) for row in rows]


def _parse_iso_datetime(value: str | None):
    payload = str(value or "").strip()
    if not payload:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(payload.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)