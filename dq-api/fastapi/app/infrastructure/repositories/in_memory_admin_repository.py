from app.core.auth import expand_granted_scopes
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.entities.admin import AdminRoleEntity, AdminUserEntity, ExceptionFactAccessRequestEntity, UserWorkspaceRoleEntity
from app.domain.interfaces.v1.admin_repository import AdminRepository
from app.domain.user_names import name_parts_from_profile, normalize_user_name_parts
from app.infrastructure.repositories.in_memory_test_data import admin_seed_data


class InMemoryAdminRepository(AdminRepository):
    def __init__(self) -> None:
        self._users, self._roles = admin_seed_data()
        self._exception_fact_access_requests: list[dict] = []

    def list_users(self) -> list[AdminUserEntity]:
        return [self._to_user_entity(user) for user in self._users]

    def list_roles(self) -> list[AdminRoleEntity]:
        return [
            AdminRoleEntity(
                id=str(role["id"]),
                name=str(role["name"]),
                workspace=str(role.get("workspace") or "default"),
                permissions=[str(permission) for permission in role.get("permissions", []) if str(permission).strip()],
            )
            for role in self._roles
        ]

    def create_role(self, payload: dict) -> AdminRoleEntity:
        role_id = str(payload.get("id") or "").strip()
        if not role_id:
            raise ValueError("Role id is required")
        if any(str(role.get("id")) == role_id for role in self._roles):
            raise ValueError(f"Role {role_id} already exists")

        role = {
            "id": role_id,
            "name": str(payload.get("name") or role_id).strip() or role_id,
            "workspace": str(payload.get("workspace") or "default").strip() or "default",
            "permissions": self._normalize_permissions(payload.get("permissions")),
        }
        self._roles.append(role)
        return self._to_role_entity(role)

    def update_role(self, role_id: str, payload: dict) -> AdminRoleEntity | None:
        role = next((entry for entry in self._roles if str(entry.get("id")) == str(role_id)), None)
        if role is None:
            return None

        if "name" in payload:
            role["name"] = str(payload.get("name") or role_id).strip() or role_id
        if "workspace" in payload:
            role["workspace"] = str(payload.get("workspace") or "default").strip() or "default"
        if "permissions" in payload:
            role["permissions"] = self._normalize_permissions(payload.get("permissions"))

        return self._to_role_entity(role)

    def list_exception_fact_access_requests(
        self,
        workspace_id: str | None = None,
        requester_id: str | None = None,
        status: str | None = None,
        request_timeout_minutes: int | None = None,
    ) -> list[ExceptionFactAccessRequestEntity]:
        self._timeout_pending_exception_fact_access_requests(request_timeout_minutes)
        rows = list(self._exception_fact_access_requests)
        if workspace_id is not None:
            target_workspace = str(workspace_id).strip().lower()
            rows = [row for row in rows if str(row.get("workspaceId") or "").strip().lower() == target_workspace]
        if requester_id is not None:
            target_requester = str(requester_id).strip().lower()
            rows = [row for row in rows if str(row.get("requesterId") or "").strip().lower() == target_requester]
        if status is not None:
            target_status = str(status).strip().lower()
            rows = [row for row in rows if str(row.get("status") or "").strip().lower() == target_status]
        rows.sort(key=lambda row: str(row.get("requestedAt") or ""), reverse=True)
        return [self._to_exception_fact_access_request_entity(row) for row in rows]

    def create_exception_fact_access_request(self, payload: dict, actor_id: str | None = None) -> ExceptionFactAccessRequestEntity:
        request_id = str(uuid4())
        requester_id = str(actor_id or payload.get("requester_id") or payload.get("requesterId") or "").strip()
        workspace_id = str(payload.get("workspace_id") or payload.get("workspaceId") or "default").strip() or "default"
        role_id = str(payload.get("role_id") or payload.get("roleId") or "").strip()
        if not requester_id:
            raise ValueError("requester_id is required")
        if not role_id:
            raise ValueError("role_id is required")

        requested_duration_minutes = self._read_duration_minutes(payload.get("requested_duration_minutes") or payload.get("requestedDurationMinutes"))
        comments = str(payload.get("comments") or "").strip() or None
        requested_at = self._current_timestamp()
        row = {
            "id": request_id,
            "requesterId": requester_id,
            "workspaceId": workspace_id,
            "roleId": role_id,
            "status": "pending",
            "requestedDurationMinutes": requested_duration_minutes,
            "comments": comments,
            "requestedAt": requested_at,
            "reviewedBy": None,
            "reviewedAt": None,
            "expiresAt": None,
        }
        self._exception_fact_access_requests.append(row)
        return self._to_exception_fact_access_request_entity(row)

    def update_exception_fact_access_request(
        self,
        request_id: str,
        payload: dict,
        actor_id: str | None = None,
        max_duration_minutes: int | None = None,
        request_timeout_minutes: int | None = None,
    ) -> ExceptionFactAccessRequestEntity | None:
        self._timeout_pending_exception_fact_access_requests(request_timeout_minutes)
        row = next((item for item in self._exception_fact_access_requests if str(item.get("id") or "") == str(request_id)), None)
        if row is None:
            return None

        if str(row.get("status") or "").strip().lower() != "pending":
            raise ValueError("Request is not pending")

        requester_id = str(row.get("requesterId") or "").strip()
        reviewer_id = str(actor_id or "").strip() or None
        if requester_id and reviewer_id and requester_id == reviewer_id:
            raise PermissionError("Requester cannot approve their own request")

        status = str(payload.get("status") or row.get("status") or "pending").strip().lower() or "pending"
        if status not in {"approved", "rejected", "revoked"}:
            raise ValueError("status must be approved, rejected, or revoked")

        comments = str(payload.get("comments") or row.get("comments") or "").strip() or None
        reviewed_at = self._current_timestamp()
        row["status"] = status
        row["comments"] = comments
        row["reviewedBy"] = reviewer_id
        row["reviewedAt"] = reviewed_at

        if status == "approved":
            requested_duration = int(row.get("requestedDurationMinutes") or 0)
            duration_limit = int(max_duration_minutes or requested_duration or 0)
            granted_duration = requested_duration if requested_duration > 0 else duration_limit
            if duration_limit > 0:
                granted_duration = min(granted_duration, duration_limit)
            granted_duration = max(1, granted_duration or 1)
            expires_at = datetime.now(UTC) + timedelta(minutes=granted_duration)
            row["expiresAt"] = expires_at.isoformat(timespec="seconds").replace("+00:00", "Z")
        else:
            row["expiresAt"] = None

        return self._to_exception_fact_access_request_entity(row)

    def resolve_login_user(self, payload: dict, sso: bool = False) -> AdminUserEntity | None:
        if sso:
            email = str(payload.get("email") or "").strip().lower()
            if email:
                return next(
                    (
                        self._to_user_entity(user)
                        for user in self._users
                        if str(user.get("email") or "").strip().lower() == email
                    ),
                    None,
                )
            return self._to_user_entity(self._users[0]) if self._users else None

        if payload.get("email"):
            email = str(payload["email"]).strip().lower()
            return next(
                (
                    self._to_user_entity(user)
                    for user in self._users
                    if str(user.get("email") or "").strip().lower() == email
                ),
                None,
            )
        if payload.get("id"):
            user_id = str(payload["id"]).strip().lower()
            return next(
                (
                    self._to_user_entity(user)
                    for user in self._users
                    if str(user.get("id") or "").strip().lower() == user_id
                ),
                None,
            )
        if payload.get("first_name") and payload.get("last_name"):
            first_name = str(payload["first_name"]).strip().lower()
            last_name = str(payload["last_name"]).strip().lower()
            return next(
                (
                    self._to_user_entity(user)
                    for user in self._users
                    if str(user.get("first_name") or "").strip().lower() == first_name
                    and str(user.get("last_name") or "").strip().lower() == last_name
                ),
                None,
            )
        if payload.get("role"):
            role = str(payload["role"]).strip().lower()
            return next(
                (
                    self._to_user_entity(user)
                    for user in self._users
                    if role in {str(value).strip().lower() for value in user.get("roles", [])}
                ),
                None,
            )
        return None

    def find_or_create_user_from_oidc(
        self,
        profile: dict,
        allow_signup: bool,
        default_role: str,
    ) -> AdminUserEntity:
        user = self._resolve_user(None, profile)
        subject = str(profile.get("sub") or "").strip()
        if user is None and subject:
            user = next(
                (
                    entry
                    for entry in self._users
                    if str(entry.get("external_id") or "").strip() == subject
                ),
                None,
            )

        if user is None:
            if not allow_signup:
                raise PermissionError("User signup is disabled")

            email = str(profile.get("email") or profile.get("preferred_username") or "").strip() or None
            first_name, last_name = name_parts_from_profile(
                profile,
                fallback=profile.get("preferred_username") or email or "",
            )
            user = {
                "id": f"user-oidc-{len(self._users) + 1}",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "roles": [str(default_role or "viewer")],
                "workspaces": ["default"],
                "preferences": None,
            }
            self._users.append(user)

        if subject:
            user["external_id"] = subject

        return self._to_user_entity(user)

    def update_user(self, user_id: str, payload: dict, max_users_per_workspace: int) -> AdminUserEntity | None:
        self._reject_direct_user_permission_payload(payload)

        user = next((entry for entry in self._users if str(entry.get("id")) == str(user_id)), None)
        if user is None:
            return None

        email = payload["email"] if "email" in payload else user.get("email")
        roles = [str(role) for role in payload.get("roles", user.get("roles", []))]
        workspaces = [str(workspace) for workspace in payload.get("workspaces", user.get("workspaces", []))]

        workspace_counts: dict[str, int] = {}
        for existing in self._users:
            if str(existing.get("id")) == str(user_id):
                continue
            for workspace in {str(item) for item in existing.get("workspaces", []) if str(item).strip()}:
                workspace_counts[workspace] = workspace_counts.get(workspace, 0) + 1

        for workspace in {value for value in workspaces if value.strip()}:
            if workspace_counts.get(workspace, 0) + 1 > max_users_per_workspace:
                raise ValueError(f"User limit reached for workspace {workspace} ({max_users_per_workspace})")

        if "first_name" in payload or "last_name" in payload:
            user["first_name"], user["last_name"] = normalize_user_name_parts(
                payload.get("first_name", user.get("first_name")),
                payload.get("last_name", user.get("last_name")),
                fallback=user.get("email") or user.get("id"),
            )
        user["email"] = email
        user["roles"] = roles
        user["workspaces"] = workspaces
        return self._to_user_entity(user)

    def _reject_direct_user_permission_payload(self, payload: dict) -> None:
        forbidden_fields = [field for field in ("permissions", "granted_scopes", "workspace_roles") if field in payload]
        if forbidden_fields:
            raise ValueError("User updates must assign roles and workspaces, not permissions")

    def reset_user_preferences(self, user_id: str, scope: str) -> AdminUserEntity | None:
        user = next((entry for entry in self._users if str(entry.get("id")) == str(user_id)), None)
        if user is None:
            return None

        if scope == "profile":
            preferences = user.get("preferences")
            if isinstance(preferences, dict):
                preferences = dict(preferences)
                preferences.pop("profile", None)
                user["preferences"] = preferences or None
        else:
            user["preferences"] = None

        return self._to_user_entity(user)

    def get_current_user(self, user_id: str | None, claims: dict | None = None) -> AdminUserEntity | None:
        user = self._resolve_user(user_id, claims)
        if user is None:
            return None
        return self._serialize_current_user(user)

    def update_current_user(self, user_id: str | None, claims: dict | None, payload: dict) -> AdminUserEntity | None:
        user = self._resolve_user(user_id, claims)
        if user is None:
            return None

        user["preferences"] = payload.get("preferences") if "preferences" in payload else None
        return self._serialize_current_user(user)

    def _resolve_user(self, user_id: str | None, claims: dict | None = None) -> dict | None:
        claim_map = claims or {}
        candidates = [
            user_id,
            claim_map.get("email"),
            claim_map.get("preferred_username"),
            claim_map.get("sub"),
        ]

        for candidate in candidates:
            if not candidate:
                continue
            candidate_text = str(candidate).strip().lower()
            for user in self._users:
                if str(user.get("id") or "").strip().lower() == candidate_text:
                    return user
                if str(user.get("email") or "").strip().lower() == candidate_text:
                    return user
                email_prefix = str(user.get("email") or "").split("@", 1)[0].strip().lower()
                if email_prefix and email_prefix == candidate_text:
                    return user
        return None

    def _serialize_current_user(self, user: dict) -> AdminUserEntity:
        return self._to_user_entity(user)

    def _to_user_entity(self, user: dict) -> AdminUserEntity:
        roles = list(user.get("roles") or [])
        workspaces = list(user.get("workspaces") or [])
        granted_scopes = self._get_granted_scopes(roles)
        granted_scopes.extend(self._get_active_exception_fact_access_scopes(str(user.get("id") or ""), workspaces))
        granted_scopes = sorted({scope for scope in granted_scopes if str(scope).strip()})
        workspace_roles = [
            UserWorkspaceRoleEntity.model_validate(item)
            if isinstance(item, dict)
            else item
            for item in list(user.get("workspace_roles") or self._build_workspace_roles(user))
        ]
        workspace_roles = self._build_exception_fact_access_workspace_roles(str(user.get("id") or "")) + workspace_roles
        return AdminUserEntity(
            id=str(user.get("id") or ""),
            first_name=str(user.get("first_name") or ""),
            last_name=str(user.get("last_name") or ""),
            email=user.get("email"),
            roles=roles,
            granted_scopes=granted_scopes,
            workspaces=workspaces,
            workspace_roles=workspace_roles,
            preferences=dict(user.get("preferences") or {}),
            external_id=user.get("external_id"),
        )

    def _build_workspace_roles(self, user: dict) -> list[UserWorkspaceRoleEntity]:
        role_ids = [str(role_id).strip() for role_id in list(user.get("roles") or []) if str(role_id).strip()]
        workspaces = [str(workspace).strip() for workspace in list(user.get("workspaces") or []) if str(workspace).strip()]
        if not role_ids or not workspaces:
            return []

        role_meta_by_id = {
            str(role.get("id") or ""): {
                "name": str(role.get("name") or role.get("id") or ""),
                "workspace": str(role.get("workspace") or "").strip(),
                "permissions": list(role.get("permissions") or []),
            }
            for role in self._roles
            if str(role.get("id") or "").strip()
        }

        workspace_roles: list[UserWorkspaceRoleEntity] = []
        for workspace in workspaces:
            exact_matches = [
                role_id for role_id in role_ids if str(role_meta_by_id.get(role_id, {}).get("workspace") or "").strip() == workspace
            ]
            candidate_role_ids = exact_matches or [
                role_id for role_id in role_ids if str(role_meta_by_id.get(role_id, {}).get("workspace") or "").strip().lower() == "global"
            ]
            if not candidate_role_ids:
                candidate_role_ids = role_ids

            selected_role_id = self._select_best_role_id(candidate_role_ids, role_meta_by_id)
            workspace_roles.append(
                UserWorkspaceRoleEntity(
                    workspace_id=workspace,
                    role=self._classify_role(selected_role_id, role_meta_by_id.get(selected_role_id)),
                )
            )

        return workspace_roles

    def _select_best_role_id(self, role_ids: list[str], role_meta_by_id: dict[str, dict[str, object]]) -> str:
        best_role_id = role_ids[0]
        best_priority = -1
        for role_id in role_ids:
            priority = self._role_priority(self._classify_role(role_id, role_meta_by_id.get(role_id)))
            if priority > best_priority:
                best_priority = priority
                best_role_id = role_id
        return best_role_id

    def _role_priority(self, role: str) -> int:
        priorities = {
            "admin": 3,
            "data-steward": 2,
            "exception-fact-investigator": 1,
            "exception-fact-reader": 1,
            "analyst": 1,
            "auditor": 1,
            "regulator": 1,
            "viewer": 0,
        }
        return priorities.get(role, 0)

    def _classify_role(self, role_id: str, meta: dict[str, object] | None) -> str:
        role_text = " ".join(
            str(value or "").lower().strip()
            for value in [role_id, (meta or {}).get("name"), (meta or {}).get("workspace")]
        )
        permissions = [str(permission).strip().lower() for permission in ((meta or {}).get("permissions") or []) if str(permission).strip()]
        permission_set = set(permissions)

        if (
            "admin" in role_text
            or {"dq:users:manage", "dq:workspace:manage", "dq:config:manage"}.intersection(permission_set)
        ):
            return "admin"

        if "auditor" in role_text:
            return "auditor"

        if "regulator" in role_text:
            return "regulator"

        if "exception-fact-investigator" in role_text or "dq:exceptions:detail" in permission_set:
            return "exception-fact-investigator"

        if "exception-fact-reader" in role_text or "dq:exceptions:read" in permission_set:
            return "exception-fact-reader"

        if (
            any(token in role_text for token in ["steward", "approver", "reviewer"])
            or "dq:rules:approve" in permission_set
        ):
            return "data-steward"

        if (
            any(token in role_text for token in ["analyst", "editor", "owner"])
            or {"dq:rules:create", "dq:rules:edit", "dq:rules:test", "dq:profiling:request"}.intersection(permission_set)
        ):
            return "analyst"

        return "viewer"

    def _to_role_entity(self, role: dict) -> AdminRoleEntity:
        return AdminRoleEntity(
            id=str(role.get("id") or ""),
            name=str(role.get("name") or ""),
            workspace=str(role.get("workspace") or "default"),
            permissions=[str(permission) for permission in role.get("permissions", []) if str(permission).strip()],
        )

    def _normalize_permissions(self, permissions: object) -> list[str]:
        if not isinstance(permissions, list):
            return []
        return sorted({str(permission).strip() for permission in permissions if str(permission).strip()})

    def _get_granted_scopes(self, role_ids: list[str]) -> list[str]:
        permissions: list[str] = []
        for role_id in role_ids:
            role = next((entry for entry in self._roles if str(entry.get("id")) == str(role_id)), None)
            if role is None:
                continue
            permissions.extend(self._normalize_permissions(role.get("permissions")))
        return sorted(expand_granted_scopes(permissions))

    def _get_active_exception_fact_access_scopes(self, user_id: str, workspaces: list[str]) -> list[str]:
        if not user_id:
            return []
        active_roles = {
            str(row.get("roleId") or "")
            for row in self._exception_fact_access_requests
            if str(row.get("requesterId") or "").strip().lower() == user_id.strip().lower()
            and str(row.get("status") or "").strip().lower() == "approved"
            and self._is_request_active(row)
            and str(row.get("workspaceId") or "").strip() in {str(workspace).strip() for workspace in workspaces if str(workspace).strip()}
        }
        permissions: list[str] = []
        for role_id in active_roles:
            role = next((entry for entry in self._roles if str(entry.get("id")) == role_id), None)
            if role is None:
                continue
            permissions.extend(self._normalize_permissions(role.get("permissions")))
        return sorted(expand_granted_scopes(permissions))

    def _build_exception_fact_access_workspace_roles(self, user_id: str) -> list[UserWorkspaceRoleEntity]:
        if not user_id:
            return []
        rows = [
            row
            for row in self._exception_fact_access_requests
            if str(row.get("requesterId") or "").strip().lower() == user_id.strip().lower()
            and str(row.get("status") or "").strip().lower() == "approved"
            and self._is_request_active(row)
        ]
        return [
            UserWorkspaceRoleEntity(
                workspace_id=str(row.get("workspaceId") or ""),
                role=str(row.get("roleId") or ""),
            )
            for row in rows
        ]

    def _timeout_pending_exception_fact_access_requests(self, request_timeout_minutes: int | None) -> None:
        timeout_minutes = max(0, int(request_timeout_minutes or 0))
        if timeout_minutes <= 0:
            return

        cutoff = datetime.now(UTC) - timedelta(minutes=timeout_minutes)
        for row in self._exception_fact_access_requests:
            if str(row.get("status") or "").strip().lower() != "pending":
                continue
            requested_at = str(row.get("requestedAt") or "").strip()
            if not requested_at:
                continue
            try:
                requested_at_dt = datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
            except Exception:
                continue
            if requested_at_dt <= cutoff:
                row["status"] = "timed_out"
                row["reviewedBy"] = None
                row["reviewedAt"] = self._current_timestamp()
                row["expiresAt"] = None

    @staticmethod
    def _current_timestamp() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _is_request_active(row: dict) -> bool:
        expires_at = str(row.get("expiresAt") or "").strip()
        if not expires_at:
            return False
        try:
            expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except Exception:
            return False
        return expires > datetime.now(UTC)

    @staticmethod
    def _read_duration_minutes(value: object) -> int:
        try:
            duration = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return max(0, duration)

    def _to_exception_fact_access_request_entity(self, row: dict) -> ExceptionFactAccessRequestEntity:
        return ExceptionFactAccessRequestEntity(
            id=str(row.get("id") or ""),
            requesterId=str(row.get("requesterId") or ""),
            workspaceId=str(row.get("workspaceId") or ""),
            roleId=str(row.get("roleId") or ""),
            status=str(row.get("status") or "pending"),
            requestedDurationMinutes=int(row.get("requestedDurationMinutes") or 0),
            comments=str(row.get("comments") or "").strip() or None,
            requestedAt=str(row.get("requestedAt") or ""),
            reviewedBy=str(row.get("reviewedBy") or "").strip() or None,
            reviewedAt=str(row.get("reviewedAt") or "").strip() or None,
            expiresAt=str(row.get("expiresAt") or "").strip() or None,
        )