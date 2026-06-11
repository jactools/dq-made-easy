import app.application.services.delivery_inventory as delivery_inventory_mod
from app.application.services.delivery_inventory import DeliveryInventoryInspector


class _StubStorageService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def inspect(self, delivery_location: str) -> dict[str, object]:
        self.calls.append(delivery_location)
        return {
            "storage_exists": True,
            "storage_object_count": 2,
            "file_names": ["part-0000.parquet", "part-0001.parquet"],
        }


def test_delivery_inventory_inspector_delegates_to_storage_service() -> None:
    storage_service = _StubStorageService()
    inspector = DeliveryInventoryInspector.__new__(DeliveryInventoryInspector)
    inspector._storage_service = storage_service

    result = inspector.inspect("s3a://bucket/path")

    assert storage_service.calls == ["s3a://bucket/path"]
    assert result["storage_exists"] is True
    assert result["storage_object_count"] == 2
    assert result["file_names"] == ["part-0000.parquet", "part-0001.parquet"]


def test_delivery_inventory_inspector_uses_default_storage_service(monkeypatch) -> None:
    storage_service = _StubStorageService()

    monkeypatch.setattr(delivery_inventory_mod, "S3DeliveryStorageService", lambda: storage_service)

    inspector = DeliveryInventoryInspector()
    result = inspector.inspect("s3a://bucket/default")

    assert inspector._storage_service is storage_service
    assert storage_service.calls == ["s3a://bucket/default"]
    assert result["storage_exists"] is True
