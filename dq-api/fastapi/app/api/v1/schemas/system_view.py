from pydantic import ConfigDict

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class ApiInfoView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    version: str
    buildDate: str


class DatabaseInfoView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    schemaVersion: str
    schemaUpdated: str | None = None
    schemaGitCommit: str | None = None

class DeploymentInfoView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    deploymentVerificationDate: str | None = None
    deploymentVerifiedBy: str | None = None


class VersionCatalogAppView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ui: str
    api: str


class VersionCatalogView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    apps: VersionCatalogAppView
    components: dict[str, str] = {}


class SystemInfoView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    api: ApiInfoView
    database: DatabaseInfoView
    deployment: DeploymentInfoView
    versions: VersionCatalogView
