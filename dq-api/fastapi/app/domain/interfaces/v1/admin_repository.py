from typing import Protocol

from app.domain.entities.admin import AdminRoleEntity, AdminUserEntity, ExceptionFactAccessRequestEntity


class AdminRepository(Protocol):
    def list_users(self) -> list[AdminUserEntity]: ...

    def list_roles(self) -> list[AdminRoleEntity]: ...

    def create_role(self, payload: dict) -> AdminRoleEntity: ...

    def update_role(self, role_id: str, payload: dict) -> AdminRoleEntity | None: ...

    def list_exception_fact_access_requests(
        self,
        workspace_id: str | None = None,
        requester_id: str | None = None,
        status: str | None = None,
        request_timeout_minutes: int | None = None,
    ) -> list[ExceptionFactAccessRequestEntity]: ...

    def create_exception_fact_access_request(self, payload: dict, actor_id: str | None = None) -> ExceptionFactAccessRequestEntity: ...

    def update_exception_fact_access_request(
        self,
        request_id: str,
        payload: dict,
        actor_id: str | None = None,
        max_duration_minutes: int | None = None,
        request_timeout_minutes: int | None = None,
    ) -> ExceptionFactAccessRequestEntity | None: ...

    def resolve_login_user(self, payload: dict, sso: bool = False) -> AdminUserEntity | None: ...

    def find_or_create_user_from_oidc(
        self,
        profile: dict,
        allow_signup: bool,
        default_role: str,
    ) -> AdminUserEntity: ...

    def update_user(self, user_id: str, payload: dict, max_users_per_workspace: int) -> AdminUserEntity | None: ...

    def reset_user_preferences(self, user_id: str, scope: str) -> AdminUserEntity | None: ...

    def get_current_user(self, user_id: str | None, claims: dict | None = None) -> AdminUserEntity | None: ...

    def update_current_user(self, user_id: str | None, claims: dict | None, payload: dict) -> AdminUserEntity | None: ...