from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app.api.v1.schemas.gx_artifact_view import GxArtifactAssignmentScopeView
from app.core.otel_metrics import increment_gx_failure
from app.domain.entities.data_catalog import DataObjectCatalogEntity
from app.domain.entities.data_catalog import DataObjectVersionEntity
from app.domain.entities.data_catalog import DataProductEntity
from app.domain.entities.data_catalog import DataSetEntity
from app.domain.interfaces import DataCatalogRepository


class SourceDataResolutionError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class SourceDataResolver:
    def __init__(self, *, catalog_repository: DataCatalogRepository) -> None:
        self._catalog_repository = catalog_repository

    def _resolution_error(self, message: str, *, reason: str, status_code: int = 400) -> SourceDataResolutionError:
        increment_gx_failure(surface="source_data_resolver", operation="resolve_assignment_scope", reason=reason)
        return SourceDataResolutionError(message, status_code=status_code)

    async def resolve_assignment_scope(
        self,
        assignment_scope: GxArtifactAssignmentScopeView | Mapping[str, Any],
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._resolve_assignment_scope_sync, assignment_scope)

    def _resolve_assignment_scope_sync(
        self,
        assignment_scope: GxArtifactAssignmentScopeView | Mapping[str, Any],
    ) -> dict[str, Any]:
        scope = self._coerce_assignment_scope(assignment_scope)
        datasets_by_id = self._load_datasets_by_id()
        products_by_id = self._load_products_by_id()
        allowed_dataset_ids = self._resolve_allowed_dataset_ids(scope, datasets_by_id)
        candidate_rows = self._resolve_candidate_objects(scope, allowed_dataset_ids, datasets_by_id, products_by_id)

        if not candidate_rows:
            raise self._resolution_error(
                "SOURCE_DATA assignment scope does not resolve to any active dataObjectVersionId targets",
                reason="no_candidate_targets",
            )

        resolved_targets = [
            self._build_resolved_target(row, datasets_by_id)
            for row in self._sort_candidate_rows(candidate_rows, datasets_by_id)
        ]
        resolved_execution_scope = {
            "dataObjectVersionIds": list(dict.fromkeys(target["dataObjectVersionId"] for target in resolved_targets)),
        }

        if not resolved_execution_scope["dataObjectVersionIds"]:
            raise self._resolution_error(
                "SOURCE_DATA assignment scope does not resolve to any active dataObjectVersionId targets",
                reason="no_resolved_execution_targets",
            )

        return {
            "assignmentScope": scope.model_dump(),
            "resolvedExecutionScope": resolved_execution_scope,
            "resolvedTargets": resolved_targets,
        }

    def _coerce_assignment_scope(
        self,
        assignment_scope: GxArtifactAssignmentScopeView | Mapping[str, Any],
    ) -> GxArtifactAssignmentScopeView:
        if isinstance(assignment_scope, GxArtifactAssignmentScopeView):
            return assignment_scope

        try:
            return GxArtifactAssignmentScopeView.model_validate(dict(assignment_scope))
        except ValidationError as exc:
            raise self._resolution_error("SOURCE_DATA assignment scope is invalid", reason="invalid_assignment_scope") from exc

    def _load_datasets_by_id(self) -> dict[str, DataSetEntity]:
        datasets = self._catalog_repository.list_data_sets()
        return {
            str(dataset.id or "").strip(): dataset
            for dataset in datasets
            if str(dataset.id or "").strip()
        }

    def _load_products_by_id(self) -> dict[str, DataProductEntity]:
        products = self._catalog_repository.list_data_products()
        return {
            str(product.id or "").strip(): product
            for product in products
            if str(product.id or "").strip()
        }

    @staticmethod
    def _normalize_tags(values: list[str] | None) -> set[str]:
        return {str(value or "").strip() for value in (values or []) if str(value or "").strip()}

    def _matches_requested_tags(
        self,
        *,
        row: DataObjectCatalogEntity,
        dataset: DataSetEntity,
        product: DataProductEntity,
        scope_tags: set[str],
    ) -> bool:
        if not scope_tags:
            return True

        candidate_tags = {
            *self._normalize_tags(list(row.tags or [])),
            *self._normalize_tags(list(dataset.tags or [])),
            *self._normalize_tags(list(product.tags or [])),
        }
        if candidate_tags.intersection(scope_tags):
            return True

        latest_version = self._resolve_latest_version(row, str(row.id or ""))
        version_tags = self._normalize_tags(list(latest_version.tags or []))
        return bool(version_tags.intersection(scope_tags))

    def _resolve_allowed_dataset_ids(
        self,
        scope: GxArtifactAssignmentScopeView,
        datasets_by_id: dict[str, DataSetEntity],
    ) -> set[str]:
        if scope.dataProductId:
            product_datasets = self._catalog_repository.list_data_sets(product_id=scope.dataProductId)
            allowed_dataset_ids = {
                str(dataset.id or "").strip()
                for dataset in product_datasets
                if str(dataset.id or "").strip()
            }
            if not allowed_dataset_ids:
                raise self._resolution_error(
                    f"SOURCE_DATA dataProductId '{scope.dataProductId}' does not map to any data sets",
                    reason="missing_data_product_datasets",
                )
            if scope.datasetId and scope.datasetId not in allowed_dataset_ids:
                raise self._resolution_error(
                    f"SOURCE_DATA datasetId '{scope.datasetId}' does not belong to dataProductId '{scope.dataProductId}'",
                    reason="dataset_outside_data_product",
                )
        else:
            allowed_dataset_ids = set(datasets_by_id.keys())

        if scope.datasetId and scope.datasetId not in datasets_by_id:
            raise self._resolution_error(
                f"SOURCE_DATA datasetId '{scope.datasetId}' was not found in the catalog",
                reason="missing_dataset",
            )

        return allowed_dataset_ids

    def _resolve_candidate_objects(
        self,
        scope: GxArtifactAssignmentScopeView,
        allowed_dataset_ids: set[str],
        datasets_by_id: dict[str, DataSetEntity],
        products_by_id: dict[str, DataProductEntity],
    ) -> list[DataObjectCatalogEntity]:
        rows = self._catalog_repository.list_data_objects_catalog()
        requested_tags = self._normalize_tags(list(scope.tagIds or []))
        matching_rows = [
            row
            for row in rows
            if self._row_matches_scope(row, scope, allowed_dataset_ids)
            and self._matches_requested_tags(
                row=row,
                dataset=datasets_by_id.get(str(row.dataset_id or "").strip())
                or DataSetEntity(id=str(row.dataset_id or "").strip()),
                product=products_by_id.get(
                    str(
                        (
                            datasets_by_id.get(str(row.dataset_id or "").strip()).product_id
                            if datasets_by_id.get(str(row.dataset_id or "").strip()) is not None
                            else ""
                        )
                    ).strip()
                )
                or DataProductEntity(
                    id=str(
                        (
                            datasets_by_id.get(str(row.dataset_id or "").strip()).product_id
                            if datasets_by_id.get(str(row.dataset_id or "").strip()) is not None
                            else ""
                        )
                    ).strip()
                ),
                scope_tags=requested_tags,
            )
        ]

        if scope.dataObjectId:
            if not matching_rows:
                raise self._resolution_error(
                    f"SOURCE_DATA dataObjectId '{scope.dataObjectId}' was not found in the selected scope",
                    reason="missing_data_object",
                )
            if len(matching_rows) > 1:
                raise self._resolution_error(
                    f"SOURCE_DATA dataObjectId '{scope.dataObjectId}' resolved to multiple catalog entries",
                    reason="ambiguous_data_object",
                )
        return matching_rows

    def _row_matches_scope(
        self,
        row: DataObjectCatalogEntity,
        scope: GxArtifactAssignmentScopeView,
        allowed_dataset_ids: set[str],
    ) -> bool:
        dataset_id = str(row.dataset_id or "").strip()
        if not dataset_id or dataset_id not in allowed_dataset_ids:
            return False
        if scope.datasetId and dataset_id != scope.datasetId:
            return False
        if scope.dataObjectId and str(row.id or "").strip() != scope.dataObjectId:
            return False
        return True

    def _sort_candidate_rows(
        self,
        candidate_rows: list[DataObjectCatalogEntity],
        datasets_by_id: dict[str, DataSetEntity],
    ) -> list[DataObjectCatalogEntity]:
        def _sort_key(row: DataObjectCatalogEntity) -> tuple[str, str, str]:
            dataset = datasets_by_id.get(str(row.dataset_id or "").strip())
            dataset_name = str(dataset.name or "") if dataset is not None else str(row.dataset_id or "")
            return (dataset_name, str(row.name or ""), str(row.id or ""))

        return sorted(candidate_rows, key=_sort_key)

    def _build_resolved_target(
        self,
        row: DataObjectCatalogEntity,
        datasets_by_id: dict[str, DataSetEntity],
    ) -> dict[str, Any]:
        object_id = str(row.id or "").strip()
        dataset_id = str(row.dataset_id or "").strip()
        dataset = datasets_by_id.get(dataset_id)
        if dataset is None:
            raise self._resolution_error(
                f"SOURCE_DATA dataObjectId '{object_id}' references missing datasetId '{dataset_id}'",
                reason="missing_dataset_for_data_object",
            )

        version = self._resolve_latest_version(row, object_id)
        return {
            "dataObjectId": object_id,
            "datasetId": dataset_id,
            "dataProductId": str(dataset.product_id or "").strip() or None,
            "dataObjectVersionId": version.id,
            "dataObjectVersion": version.version,
        }

    def _resolve_latest_version(
        self,
        row: DataObjectCatalogEntity,
        object_id: str,
    ) -> DataObjectVersionEntity:
        latest_version_id = str(row.latest_version_id or "").strip()
        if not latest_version_id:
            raise self._resolution_error(
                f"SOURCE_DATA dataObjectId '{object_id}' does not define an active latest version",
                reason="missing_latest_version_id",
            )

        versions = {
            str(version.id or "").strip(): version
            for version in self._catalog_repository.list_data_object_versions(object_id)
            if str(version.id or "").strip()
        }
        if not versions:
            raise self._resolution_error(
                f"SOURCE_DATA dataObjectId '{object_id}' does not have any registered versions",
                reason="missing_registered_versions",
            )

        version = versions.get(latest_version_id)
        if version is None:
            raise self._resolution_error(
                f"SOURCE_DATA dataObjectId '{object_id}' latest_version_id '{latest_version_id}' was not found",
                reason="latest_version_not_found",
            )
        return version