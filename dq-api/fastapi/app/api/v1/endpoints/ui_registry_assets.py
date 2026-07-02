from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.v1.schemas.ui_registry_asset import UiRegistryAssetImportRequestView
from app.api.v1.schemas.ui_registry_asset import UiRegistryAssetImportResponseView
from app.application.services.ui_registry_assets import import_remote_ui_registry_asset
from app.application.services.ui_registry_assets import import_uploaded_ui_registry_asset
from app.application.services.ui_registry_assets import resolve_ui_registry_asset_path


router = APIRouter(tags=["configuration"])


@router.post("/ui-registry/assets/import", response_model=UiRegistryAssetImportResponseView)
def import_ui_registry_asset(payload: UiRegistryAssetImportRequestView) -> UiRegistryAssetImportResponseView:
    try:
        imported = import_remote_ui_registry_asset(
            source_url=str(payload.sourceUrl),
            kind=payload.kind,
            filename=payload.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
    file: UploadFile = File(...),
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


@router.get("/ui-registry/assets/{kind}/{file_name}")
def get_ui_registry_asset(kind: str, file_name: str):
    try:
        asset_path = resolve_ui_registry_asset_path(kind, file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="UI registry asset not found")

    return FileResponse(Path(asset_path))