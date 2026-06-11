from __future__ import annotations

from typing import Any

from app.application.services.delivery_storage import DeliveryStorageService
from app.application.services.delivery_storage import S3DeliveryStorageService


class DeliveryInventoryInspector:
    def __init__(self, storage_service: DeliveryStorageService | None = None) -> None:
        self._storage_service: DeliveryStorageService = storage_service or S3DeliveryStorageService()

    def inspect(self, delivery_location: str) -> dict[str, Any]:
        return self._storage_service.inspect(delivery_location)