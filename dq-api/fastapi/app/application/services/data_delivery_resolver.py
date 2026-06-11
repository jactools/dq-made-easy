from __future__ import annotations

from typing import Any
from collections.abc import Mapping

from app.core.otel_metrics import increment_gx_failure
from app.domain.interfaces import DataCatalogRepository


class DataDeliveryResolutionError(RuntimeError):
    def __init__(self, message: str, *, reason: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code


class DataDeliveryResolver:
    def __init__(self, *, catalog_repository: DataCatalogRepository) -> None:
        self._catalog_repository = catalog_repository

    def _resolution_error(self, message: str, *, reason: str, status_code: int = 422) -> DataDeliveryResolutionError:
        increment_gx_failure(surface="data_delivery_resolver", operation="resolve_delivery", reason=reason)
        return DataDeliveryResolutionError(message, reason=reason, status_code=status_code)

    @staticmethod
    def _row_value(row: Any, field_name: str) -> Any:
        if isinstance(row, Mapping):
            return row.get(field_name)
        return getattr(row, field_name, None)

    def resolve_delivery(
        self,
        *,
        data_object_version_id: str,
        data_delivery_id: str | None = None,
    ) -> dict[str, Any]:
        version_id = str(data_object_version_id or "").strip()
        if not version_id:
            raise self._resolution_error(
                "data_object_version_id is required to resolve a data delivery",
                reason="missing_data_object_version_id",
            )

        deliveries = self._catalog_repository.list_data_deliveries(version_id)
        if not deliveries:
            raise self._resolution_error(
                f"No data_delivery was found for dataObjectVersionId '{version_id}'",
                reason="missing_data_delivery",
            )

        if data_delivery_id:
            delivery_id = str(data_delivery_id or "").strip()
            if not delivery_id:
                raise self._resolution_error(
                    "data_delivery_id is blank",
                    reason="invalid_data_delivery_id",
                )
            delivery = next((row for row in deliveries if str(self._row_value(row, "id") or "").strip() == delivery_id), None)
            if delivery is None:
                raise self._resolution_error(
                    f"data_delivery_id '{delivery_id}' does not belong to dataObjectVersionId '{version_id}'",
                    reason="delivery_outside_version",
                )
            resolution_mode = "specific_delivery"
        else:
            delivery = deliveries[0]
            resolution_mode = "latest_delivery"

        resolved_delivery_id = str(self._row_value(delivery, "id") or "").strip()
        if not resolved_delivery_id:
            raise self._resolution_error(
                f"dataObjectVersionId '{version_id}' resolved to a delivery without an id",
                reason="missing_delivery_id",
            )

        resolved_delivery_location = str(self._row_value(delivery, "delivery_location") or "").strip()
        if not resolved_delivery_location:
            raise self._resolution_error(
                f"data_delivery_id '{resolved_delivery_id}' does not define a delivery_location",
                reason="missing_delivery_location",
            )

        return {
            "resolvedDataObjectVersionId": version_id,
            "resolvedDataDeliveryId": resolved_delivery_id,
            "resolvedDeliveryLocation": resolved_delivery_location,
            "deliveryResolutionMode": resolution_mode,
        }