from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.schemas.ui_registry_view import UiRegistryComponentBundleView
from app.api.v1.schemas.ui_registry_view import UiRegistryStyleView
from app.api.v1.schemas.ui_registry_view import UiRegistryView
from app.core.dependencies import get_ui_registry_manager
from app.application.services.ui_registry import RegistryManager


router = APIRouter(tags=["configuration"])


@router.get("/ui-registry", response_model=UiRegistryView)
def get_ui_registry(
    manager: RegistryManager = Depends(get_ui_registry_manager),
) -> UiRegistryView:
    manifest = manager.load()
    return UiRegistryView.model_validate(
        {
            "source": manager.source.value,
            "version": manifest.version,
            "created": manifest.created,
            "updated": manifest.updated,
            "cache_ttl_seconds": manager.configuration.cache_ttl_seconds,
            "styles": [UiRegistryStyleView.model_validate(entry.to_dict()) for entry in manifest.styles],
            "component_bundles": [
                UiRegistryComponentBundleView.model_validate(entry.to_dict())
                for entry in manifest.component_bundles
            ],
            "metadata": manifest.metadata,
        }
    )