from pydantic import ConfigDict

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class DataEncryptionKeyView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    key_name: str = ""
    key_scope: str = "app"
    workspace_id: str | None = None
    key_algorithm: str = "fernet"
    key_fingerprint: str = ""
    is_active: bool = True
    created_by: str | None = None
    created_at: str = ""
    updated_at: str = ""


class DataEncryptionKeyCreateRequestView(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_snake_alias)

    key_name: str
    key_scope: str = "app"
    workspace_id: str | None = None
    key_algorithm: str = "fernet"
    key_material: str
    is_active: bool = True