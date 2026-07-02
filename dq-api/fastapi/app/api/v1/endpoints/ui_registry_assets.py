from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.v1.schemas.ui_registry_asset import UiRegistryAssetImportRequestView
from app.api.v1.schemas.ui_registry_asset import UiRegistryAssetImportResponseView
from app.application.services.ui_registry import RegistryManifest
from app.application.services.ui_registry import RegistryManager
from app.application.services.ui_registry import StyleEntry
from app.application.services.ui_registry_assets import ImportedUiRegistryAsset
from app.application.services.ui_registry_assets import import_remote_ui_registry_asset
from app.application.services.ui_registry_assets import import_uploaded_ui_registry_asset
from app.application.services.ui_registry_assets import resolve_ui_registry_asset_path
from app.core.dependencies import get_ui_registry_manager
from fastapi import Depends


router = APIRouter(tags=["configuration"])


def _register_uploaded_style_bundle(
    manager: RegistryManager,
    imported: ImportedUiRegistryAsset,
    *,
    label: str | None = None,
) -> None:
    manifest = manager.load()
    style_id = imported.public_url.removeprefix("/system/v1/ui-registry/assets/styles/")
    style_label = (label or "").strip() or Path(imported.file_name).name
    updated_styles = [entry for entry in manifest.styles if entry.id != style_id]
    next_priority = max((entry.priority for entry in updated_styles), default=-1) + 1
    updated_manifest = RegistryManifest(
        version=manifest.version,
        created=manifest.created,
        updated=datetime.now(UTC).isoformat(),
        styles=[
            *updated_styles,
            StyleEntry(
                id=style_id,
                label=style_label,
                description=f"Uploaded style bundle from {imported.source_url}",
                source_ref=imported.source_url,
                css_url=imported.public_url,
                fallback="ignore",
                priority=next_priority,
                is_active=True,
            ),
        ],
        component_bundles=manifest.component_bundles,
        metadata=dict(manifest.metadata),
    )
    manager.save_manifest(updated_manifest)


@router.post("/ui-registry/assets/import", response_model=UiRegistryAssetImportResponseView)
def import_ui_registry_asset(
    payload: UiRegistryAssetImportRequestView,
    manager: RegistryManager = Depends(get_ui_registry_manager),
) -> UiRegistryAssetImportResponseView:
    try:
        imported = import_remote_ui_registry_asset(
            source_url=str(payload.sourceUrl),
            kind=payload.kind,
            filename=payload.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if imported.kind == "styles":
        _register_uploaded_style_bundle(manager, imported)

    return UiRegistryAssetImportResponseView.model_validate(
        {
            "kind": imported.kind,
            "source_url": imported.source_url,
            "file_name": imported.file_name,
            "content_type": imported.content_type,
            "asset_path": imported.asset_path,
            "public_url": imported.public_url,
            "byte_count": imported.byte_count,
        }
    )


@router.post("/ui-registry/assets/upload", response_model=UiRegistryAssetImportResponseView)
async def upload_ui_registry_asset(
    kind: str = Form(...),
    label: str | None = Form(None),
    file: UploadFile = File(...),
    manager: RegistryManager = Depends(get_ui_registry_manager),
) -> UiRegistryAssetImportResponseView:
    try:
        uploaded_content = await file.read()
        imported = import_uploaded_ui_registry_asset(
            content=uploaded_content,
            upload_filename=file.filename or "ui-registry-asset.zip",
            kind=kind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if imported.kind == "styles":
        _register_uploaded_style_bundle(manager, imported, label=label)

    return UiRegistryAssetImportResponseView.model_validate(
        {
            "kind": imported.kind,
            "source_url": imported.source_url,
            "file_name": imported.file_name,
            "content_type": imported.content_type,
            "asset_path": imported.asset_path,
            "public_url": imported.public_url,
            "byte_count": imported.byte_count,
        }
    )


@router.get("/ui-registry/assets/{kind}/{file_name:path}")
def get_ui_registry_asset(kind: str, file_name: str):
    try:
        asset_path = resolve_ui_registry_asset_path(kind, file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="UI registry asset not found")

    return FileResponse(Path(asset_path))