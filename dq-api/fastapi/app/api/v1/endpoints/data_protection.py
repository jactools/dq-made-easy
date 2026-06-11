from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.v1.schemas import DataEncryptionKeyCreateRequestView, DataEncryptionKeyView
from app.core.auth import has_required_scope
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_data_protection_repository
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import DataProtectionRepository

router = APIRouter(tags=["data-protection"])


def _to_encryption_key_view(row: object) -> DataEncryptionKeyView:
    return DataEncryptionKeyView.model_validate(
        {
            "id": str(getattr(row, "id", "") or ""),
            "key_name": str(getattr(row, "keyName", "") or ""),
            "key_scope": str(getattr(row, "keyScope", "app") or "app"),
            "workspace_id": getattr(row, "workspaceId", None),
            "key_algorithm": str(getattr(row, "keyAlgorithm", "fernet") or "fernet"),
            "key_fingerprint": str(getattr(row, "keyFingerprint", "") or ""),
            "is_active": bool(getattr(row, "isActive", True)),
            "created_by": getattr(row, "createdBy", None),
            "created_at": str(getattr(row, "createdAt", "") or ""),
            "updated_at": str(getattr(row, "updatedAt", "") or ""),
        }
    )


def _ensure_config_admin(request: Request, admin_repository: AdminRepository) -> None:
    current_user = admin_repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    granted_scopes = [str(scope).strip() for scope in getattr(current_user, "granted_scopes", []) or [] if str(scope).strip()]
    if not has_required_scope(granted_scopes, ["dq:config:manage"]):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "data_protection_access_denied",
                "message": "App admin access is required to manage encryption keys",
            },
        )


@router.get("/encryption-keys", response_model=list[DataEncryptionKeyView])
async def list_encryption_keys(
    request: Request,
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    scope: str | None = Query(default=None),
    repository: DataProtectionRepository = Depends(get_data_protection_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
) -> list[DataEncryptionKeyView]:
    _ensure_config_admin(request, admin_repository)
    rows = repository.list_encryption_keys(workspace_id=workspace_id, scope=scope)
    return [_to_encryption_key_view(row) for row in rows]


@router.post("/encryption-keys", response_model=DataEncryptionKeyView)
async def create_encryption_key(
    request: Request,
    payload: DataEncryptionKeyCreateRequestView,
    repository: DataProtectionRepository = Depends(get_data_protection_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
) -> DataEncryptionKeyView:
    _ensure_config_admin(request, admin_repository)
    try:
        row = repository.create_encryption_key(payload.model_dump(mode="python"), created_by=getattr(request.state, "user_id", None))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_encryption_key_view(row)
