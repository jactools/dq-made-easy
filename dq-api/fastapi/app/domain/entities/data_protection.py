from __future__ import annotations

from app.domain.entities.base import EntityModel


class DataEncryptionKeyEntity(EntityModel):
    id: str
    keyName: str = ""
    keyScope: str = "app"
    workspaceId: str | None = None
    keyAlgorithm: str = "fernet"
    keyFingerprint: str = ""
    isActive: bool = True
    createdBy: str | None = None
    createdAt: str = ""
    updatedAt: str = ""


class AttributeProtectionPolicyEntity(EntityModel):
    attributeId: str
    maskingMethod: str = "none"
    encryptionRequired: bool = False
    encryptionKeyId: str | None = None
    protectionConfiguredBy: str | None = None
    protectionUpdatedAt: str | None = None