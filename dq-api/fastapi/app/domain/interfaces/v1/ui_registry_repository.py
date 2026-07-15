from typing import Protocol, Any


class UiRegistryRepository(Protocol):
    def get_current_manifest(self) -> Any | None: ...

    def upsert_current_manifest(
        self,
        manifest: Any,
        *,
        source_type: str | None,
        source_ref: str | None = None,
    ) -> Any: ...