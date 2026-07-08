from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PRIMARY_DATABASE_URL_ENV_NAMES = "DQ_DB_INTERNAL_URL or DQ_DB_LOCAL_URL"


class Settings(BaseSettings):
    app_name: str = "DQ API (FastAPI)"
    # Group-first versioning: /<group>/v1/... (gateway) and /api/<group>/v1/... (internal)
    api_v1_prefix: str = "/api"
    gateway_api_prefix: str = ""
    environment: str = "development"
    log_level: str = "INFO"
    cors_allow_origins: str = "http://localhost:3000,http://localhost:5173"
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("COMPOSE_DATABASE_URL", "DQ_DB_LOCAL_URL", "DQ_DB_INTERNAL_URL"),
    )
    require_database: bool = False
    sso_enabled: bool = False
    sso_issuer: str | None = Field(default=None, validation_alias="SSO_PUBLIC_ISSUER_URL")
    sso_client_id: str | None = None
    # Comma-separated list of allowed OIDC client ids (Keycloak `azp`).
    # When set, the backend will accept tokens issued to any of these clients.
    # Defaults to `SSO_CLIENT_ID` when not provided.
    sso_allowed_client_ids: str | None = None
    allow_local_auth: bool = True
    # When true, Kong (or another trusted reverse proxy) has already validated
    # the JWT before the request reaches this service.  The backend will skip
    # its own JWT re-validation (signature / issuer / audience checks) and
    # only perform *authorisation* (scope checking against DB-derived roles).
    # Must only be set to true when the backend is exclusively accessible via
    # the trusted proxy — direct exposure to the internet is a security risk.
    trust_proxy_auth: bool = False
    catalog_provider: str | None = None
    catalog_endpoint: str | None = None
    catalog_api_key: str | None = None
    catalog_oidc_issuer: str | None = None
    catalog_oidc_token_url: str | None = None
    catalog_oidc_client_id: str | None = None
    catalog_oidc_client_secret: str | None = None
    catalog_oidc_scope: str | None = None
    catalog_oidc_username: str | None = None
    catalog_oidc_password: str | None = None
    catalog_timeout_seconds: int = 30
    ui_registry_source: str = Field(default="default", validation_alias="DQ_UI_REGISTRY_SOURCE")
    ui_registry_file: str | None = Field(default=None, validation_alias="DQ_UI_REGISTRY_FILE")
    ui_registry_url: str | None = Field(default=None, validation_alias="DQ_UI_REGISTRY_URL")
    ui_registry_json: str | None = Field(default=None, validation_alias="DQ_UI_REGISTRY_JSON")
    ui_registry_manifest_version: str = Field(default="1.0.0", validation_alias="DQ_UI_REGISTRY_VERSION")
    ui_registry_cache_ttl_seconds: int = Field(default=300, validation_alias="DQ_UI_REGISTRY_CACHE_TTL_SECONDS")
    ui_registry_assets_dir: str = Field(default="tmp/ui-registry-assets", validation_alias="DQ_UI_REGISTRY_ASSETS_DIR")
    llm_service_url: str = Field(default="https://ollama-nginx:8443", validation_alias="DQ_LLM_BASE_URL")
    gx_exception_storage_backend: str = "s3"
    gx_exception_storage_endpoint: str | None = None
    gx_exception_storage_bucket: str = "dq-gx-exceptions"
    gx_exception_storage_prefix: str = "gx-exceptions"
    gx_exception_storage_access_key: str | None = None
    gx_exception_storage_secret_key: str | None = None
    gx_exception_storage_region: str = "us-east-1"
    gx_exception_storage_ssl_enabled: bool = True
    redis_host: str | None = None
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    redis_contract_cache_key_prefix: str = "dq:openmetadata:contract-policy"

    model_config = SettingsConfigDict(
        env_file=[".env", "../../.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def sso_allowed_client_ids_list(self) -> list[str]:
        raw = (self.sso_allowed_client_ids or "").strip()
        if raw:
            return [item.strip() for item in raw.split(",") if item.strip()]
        if self.sso_client_id:
            return [str(self.sso_client_id).strip()]
        return []

    def validate_runtime_requirements(self) -> None:
        if self.require_database and not self.database_url:
            raise RuntimeError(f"{PRIMARY_DATABASE_URL_ENV_NAMES} is required when REQUIRE_DATABASE=true")


@lru_cache
def get_settings() -> Settings:
    return Settings()
