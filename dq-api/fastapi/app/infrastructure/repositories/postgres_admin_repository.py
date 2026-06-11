from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import update

from app.core.auth import expand_granted_scopes
from app.domain.entities.admin import AdminRoleEntity, AdminUserEntity, ExceptionFactAccessRequestEntity, UserWorkspaceRoleEntity
from app.domain.interfaces.v1.admin_repository import AdminRepository
from app.domain.user_names import compose_user_display_name, name_parts_from_profile, normalize_user_name_parts
from app.infrastructure.orm.models import ExceptionFactAccessRequestRow
from app.infrastructure.orm.models import RoleRow
from app.infrastructure.orm.models import UserRoleRow
from app.infrastructure.orm.models import UserRow
from app.infrastructure.orm.session import session_scope


class PostgresAdminRepository(AdminRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def list_users(self) -> list[AdminUserEntity]:
        with session_scope(self.database_url) as session:
            users = session.execute(select(UserRow)).scalars().all()
            role_rows = session.execute(select(UserRoleRow.user_id, UserRoleRow.role_id)).all()
            role_defs = session.execute(select(RoleRow.id, RoleRow.name, RoleRow.workspace, RoleRow.permissions)).all()

        roles_by_user: dict[str, list[str]] = {}
        for user_id, role_id in role_rows:
            if not user_id or not role_id:
                continue
            roles_by_user.setdefault(str(user_id), []).append(str(role_id))

        permissions_by_role = {
            str(role_id): self._decode_permissions(raw_permissions)
            for role_id, _, _, raw_permissions in role_defs
            if role_id is not None
        }

        role_meta_by_id = {
            str(role_id): {
                "name": str(role_name or role_id),
                "workspace": str(role_workspace or "").strip(),
                "permissions": self._decode_permissions(raw_permissions),
            }
            for role_id, role_name, role_workspace, raw_permissions in role_defs
            if role_id is not None
        }

        granted_scopes_by_user = {
            user_id: self._expand_permissions([permission for role_id in role_ids for permission in permissions_by_role.get(role_id, [])])
            for user_id, role_ids in roles_by_user.items()
        }

        return [
            self._to_user_entity(
                {
                    "id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "external_id": user.external_id,
                    "preferences": user.preferences,
                    "roles": roles_by_user.get(str(user.id), []),
                    "granted_scopes": granted_scopes_by_user.get(str(user.id), []),
                    "workspaces": self._parse_workspaces(user),
                    "workspace_roles": self._build_workspace_roles(
                        roles_by_user.get(str(user.id), []),
                        self._parse_workspaces(user),
                        role_meta_by_id,
                    ),
                }
            )
            for user in users
        ]

    def list_roles(self) -> list[AdminRoleEntity]:
        with session_scope(self.database_url) as session:
            rows = session.execute(select(RoleRow).order_by(RoleRow.id)).scalars().all()
        return [
            AdminRoleEntity(
                id=str(row.id or ""),
                name=str(row.name or ""),
                workspace=str(row.workspace or "default"),
                permissions=self._decode_permissions(row.permissions),
            )
            for row in rows
        ]

    def create_role(self, payload: dict) -> AdminRoleEntity:
        role_id = str(payload.get("id") or "").strip()
        if not role_id:
            raise ValueError("Role id is required")

        role_name = str(payload.get("name") or role_id).strip() or role_id
        workspace = str(payload.get("workspace") or "default").strip() or "default"
        permissions = self._encode_permissions(payload.get("permissions"))

        with session_scope(self.database_url) as session:
            existing = session.get(RoleRow, role_id)
            if existing is not None:
                raise ValueError(f"Role {role_id} already exists")

            row = RoleRow(id=role_id, name=role_name, workspace=workspace, permissions=permissions)
            session.add(row)
            session.commit()

        return AdminRoleEntity(id=role_id, name=role_name, workspace=workspace, permissions=self._decode_permissions(permissions))

    def update_role(self, role_id: str, payload: dict) -> AdminRoleEntity | None:
        with session_scope(self.database_url) as session:
            row = session.get(RoleRow, role_id)
            if row is None:
                return None

            if "name" in payload:
                row.name = str(payload.get("name") or role_id).strip() or role_id
            if "workspace" in payload:
                row.workspace = str(payload.get("workspace") or "default").strip() or "default"
            if "permissions" in payload:
                row.permissions = self._encode_permissions(payload.get("permissions"))

            session.commit()
            session.refresh(row)

            return AdminRoleEntity(
                id=str(row.id or ""),
                name=str(row.name or ""),
                workspace=str(row.workspace or "default"),
                permissions=self._decode_permissions(row.permissions),
            )

    def list_exception_fact_access_requests(
        self,
        workspace_id: str | None = None,
        requester_id: str | None = None,
        status: str | None = None,
        request_timeout_minutes: int | None = None,
    ) -> list[ExceptionFactAccessRequestEntity]:
        with session_scope(self.database_url) as session:
            self._timeout_pending_exception_fact_access_requests(session, request_timeout_minutes)
            stmt = select(ExceptionFactAccessRequestRow)
            if workspace_id is not None:
                stmt = stmt.where(ExceptionFactAccessRequestRow.workspace_id == workspace_id)
            if requester_id is not None:
                stmt = stmt.where(ExceptionFactAccessRequestRow.requester_id == requester_id)
            if status is not None:
                stmt = stmt.where(ExceptionFactAccessRequestRow.status == status)
            rows = session.execute(stmt.order_by(ExceptionFactAccessRequestRow.requested_at.desc())).scalars().all()
        return [self._to_exception_fact_access_request_entity(row) for row in rows]

    def create_exception_fact_access_request(self, payload: dict, actor_id: str | None = None) -> ExceptionFactAccessRequestEntity:
        requester_id = str(actor_id or payload.get("requester_id") or payload.get("requesterId") or "").strip()
        workspace_id = str(payload.get("workspace_id") or payload.get("workspaceId") or "default").strip() or "default"
        role_id = str(payload.get("role_id") or payload.get("roleId") or "").strip()
        if not requester_id:
            raise ValueError("requester_id is required")
        if not role_id:
            raise ValueError("role_id is required")

        requested_duration_minutes = self._read_duration_minutes(
            payload.get("requested_duration_minutes") or payload.get("requestedDurationMinutes")
        )
        comments = str(payload.get("comments") or "").strip() or None
        requested_at = datetime.now(UTC).replace(tzinfo=None)

        with session_scope(self.database_url) as session:
            request_id = str(uuid4())
            session.add(
                ExceptionFactAccessRequestRow(
                    id=request_id,
                    requester_id=requester_id,
                    workspace_id=workspace_id,
                    role_id=role_id,
                    status="pending",
                    requested_duration_minutes=requested_duration_minutes,
                    comments=comments,
                    requested_at=requested_at,
                    reviewed_by=None,
                    reviewed_at=None,
                    expires_at=None,
                )
            )
            session.commit()

        row = self._fetch_exception_fact_access_request(request_id)
        if row is None:
            raise RuntimeError("Failed to create exception fact access request")
        return self._to_exception_fact_access_request_entity(row)

    def update_exception_fact_access_request(
        self,
        request_id: str,
        payload: dict,
        actor_id: str | None = None,
        max_duration_minutes: int | None = None,
        request_timeout_minutes: int | None = None,
    ) -> ExceptionFactAccessRequestEntity | None:
        with session_scope(self.database_url) as session:
            self._timeout_pending_exception_fact_access_requests(session, request_timeout_minutes)
            row = session.get(ExceptionFactAccessRequestRow, request_id)
            if row is None:
                return None

            if str(row.status or "").strip().lower() != "pending":
                raise ValueError("Request is not pending")

            requester_id = str(row.requester_id or "").strip()
            reviewer_id = str(actor_id or "").strip() or None
            if requester_id and reviewer_id and requester_id == reviewer_id:
                raise PermissionError("Requester cannot approve their own request")

            status = str(payload.get("status") or row.status or "pending").strip().lower() or "pending"
            if status not in {"approved", "rejected", "revoked"}:
                raise ValueError("status must be approved, rejected, or revoked")

            comments = str(payload.get("comments") or row.comments or "").strip() or None
            row.status = status
            row.comments = comments
            row.reviewed_by = reviewer_id
            row.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
            if status == "approved":
                requested_duration = int(row.requested_duration_minutes or 0)
                duration_limit = int(max_duration_minutes or requested_duration or 0)
                granted_duration = requested_duration if requested_duration > 0 else duration_limit
                if duration_limit > 0:
                    granted_duration = min(granted_duration, duration_limit)
                granted_duration = max(1, granted_duration or 1)
                row.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=granted_duration)
            else:
                row.expires_at = None

            session.commit()
            session.refresh(row)
            return self._to_exception_fact_access_request_entity(row)

    def resolve_login_user(self, payload: dict, sso: bool = False) -> AdminUserEntity | None:
        with session_scope(self.database_url) as session:
            if sso:
                email = str(payload.get("email") or "").strip()
                if email:
                    row = session.execute(
                        select(UserRow.id).where(func.lower(UserRow.email) == func.lower(email)).limit(1)
                    ).first()
                    return self._fetch_user(str(row[0])) if row else None
                row = session.execute(select(UserRow.id).order_by(UserRow.id).limit(1)).first()
                return self._fetch_user(str(row[0])) if row else None

            if payload.get("email"):
                email = str(payload["email"]).strip()
                row = session.execute(
                    select(UserRow.id).where(func.lower(UserRow.email) == func.lower(email)).limit(1)
                ).first()
                return self._fetch_user(str(row[0])) if row else None

            if payload.get("id"):
                return self._fetch_user(str(payload["id"]).strip())

            if payload.get("first_name") and payload.get("last_name"):
                first_name = str(payload["first_name"]).strip()
                last_name = str(payload["last_name"]).strip()
                row = session.execute(
                    select(UserRow.id)
                    .where(func.lower(UserRow.first_name) == func.lower(first_name))
                    .where(func.lower(UserRow.last_name) == func.lower(last_name))
                    .limit(1)
                ).first()
                return self._fetch_user(str(row[0])) if row else None

            if payload.get("role"):
                role = str(payload["role"]).strip()
                row = session.execute(
                    select(UserRoleRow.user_id)
                    .where(UserRoleRow.role_id == role)
                    .order_by(UserRoleRow.user_id)
                    .limit(1)
                ).first()
                return self._fetch_user(str(row[0])) if row else None

        return None

    def find_or_create_user_from_oidc(
        self,
        profile: dict,
        allow_signup: bool,
        default_role: str,
    ) -> AdminUserEntity:
        if not isinstance(profile, dict) or not profile:
            raise ValueError("No OIDC user provided")

        raw_identifiers = [
            profile.get("email"),
            profile.get("preferred_username"),
            profile.get("upn"),
        ]
        unique_emails: list[str] = []
        seen_emails: set[str] = set()
        for value in raw_identifiers:
            candidate = str(value or "").strip()
            if not candidate:
                continue
            lowered = candidate.lower()
            if lowered in seen_emails:
                continue
            seen_emails.add(lowered)
            unique_emails.append(candidate)

        preferred_username = str(profile.get("preferred_username") or "").strip()
        subject = str(profile.get("sub") or profile.get("sub_id") or "").strip() or None

        with session_scope(self.database_url) as session:
            user: UserRow | None = None

            for candidate_email in unique_emails:
                user = session.execute(
                    select(UserRow)
                    .where(func.lower(UserRow.email) == func.lower(candidate_email))
                    .limit(1)
                ).scalar_one_or_none()
                if user is not None:
                    break

            if user is None and preferred_username and "@" not in preferred_username:
                user = session.execute(
                    select(UserRow)
                    .where(func.lower(func.split_part(UserRow.email, "@", 1)) == func.lower(preferred_username))
                    .order_by(UserRow.id)
                    .limit(1)
                ).scalar_one_or_none()

            # Attempt to resolve by OIDC subject/external id for SSO users.
            # This ensures existing users whose `id` or `external_id` matches the
            # provider subject are linked and their sparse profiles are enriched.
            if user is None and subject:
                # try direct primary-key match first
                user = session.get(UserRow, subject)
                if user is None:
                    user = session.execute(
                        select(UserRow).where(UserRow.external_id == subject).limit(1)
                    ).scalar_one_or_none()

                if user is not None:
                    # populate missing email/name from profile when available
                    updated = False
                    if (not getattr(user, "email", None) or str(user.email).strip() == "") and unique_emails:
                        user.email = unique_emails[0]
                        updated = True
                    current_display_name = compose_user_display_name(
                        getattr(user, "first_name", None),
                        getattr(user, "last_name", None),
                    )
                    if not current_display_name:
                        resolved_first_name, resolved_last_name = name_parts_from_profile(
                            profile,
                            fallback=preferred_username or (unique_emails[0] if unique_emails else user.id),
                        )
                        user.first_name = resolved_first_name
                        user.last_name = resolved_last_name
                        updated = True

                    # ensure at least the default role exists for the user
                    role_row = session.execute(
                        select(UserRoleRow.role_id).where(UserRoleRow.user_id == str(user.id)).limit(1)
                    ).first()
                    if role_row is None:
                        session.add(UserRoleRow(user_id=str(user.id), role_id=str(default_role or "viewer").strip() or "viewer"))
                        updated = True

                    if updated:
                        session.commit()

            if user is None:
                if not allow_signup:
                    raise PermissionError("User signup is disabled")

                user_id = str(uuid4())
                email = unique_emails[0] if unique_emails else None
                first_name, last_name = name_parts_from_profile(
                    profile,
                    fallback=preferred_username or email or user_id,
                )
                user = UserRow(id=user_id, first_name=first_name, last_name=last_name, email=email)
                session.add(user)
                session.add(UserRoleRow(user_id=user_id, role_id=str(default_role or "viewer").strip() or "viewer"))
                session.commit()

            resolved_id = str(user.id)

        resolved = self._fetch_user(resolved_id)
        if resolved is None:
            raise RuntimeError("Failed to load user")
        return resolved

    def update_user(self, user_id: str, payload: dict, max_users_per_workspace: int) -> AdminUserEntity | None:
        self._reject_direct_user_permission_payload(payload)

        with session_scope(self.database_url) as session:
            existing = session.get(UserRow, user_id)
            if existing is None:
                return None

            email = payload["email"] if "email" in payload else existing.email
            roles = [str(role) for role in payload.get("roles", [])] if isinstance(payload.get("roles"), list) else None
            workspaces = self._payload_workspaces(payload, existing)

            if workspaces:
                self._assert_workspace_capacity(user_id, workspaces, max_users_per_workspace)

            if "first_name" in payload or "last_name" in payload:
                existing.first_name, existing.last_name = normalize_user_name_parts(
                    payload.get("first_name", existing.first_name),
                    payload.get("last_name", existing.last_name),
                    fallback=existing.email or existing.id,
                )
            existing.email = email
            existing.workspaces = ";".join(workspaces)

            if roles is not None:
                session.execute(delete(UserRoleRow).where(UserRoleRow.user_id == user_id))
                for role_id in roles:
                    session.add(UserRoleRow(user_id=user_id, role_id=role_id))

            session.commit()

        return self._fetch_user(user_id)

    def _reject_direct_user_permission_payload(self, payload: dict) -> None:
        forbidden_fields = [field for field in ("permissions", "granted_scopes", "workspace_roles") if field in payload]
        if forbidden_fields:
            raise ValueError("User updates must assign roles and workspaces, not permissions")

    def reset_user_preferences(self, user_id: str, scope: str) -> AdminUserEntity | None:
        with session_scope(self.database_url) as session:
            existing = session.get(UserRow, user_id)
            if existing is None:
                return None

            preferences = None
            if scope == "profile":
                preferences = self._decode_preferences(existing.preferences)
                if isinstance(preferences, dict):
                    preferences = dict(preferences)
                    preferences.pop("profile", None)
                    if not preferences:
                        preferences = None

            existing.preferences = self._encode_preferences(preferences)
            session.commit()

            return self._fetch_user(str(existing.id or user_id))

    def get_current_user(self, user_id: str | None, claims: dict | None = None) -> AdminUserEntity | None:
        user = self._find_current_user(user_id, claims)
        if user is None:
            return None
        return self._serialize_current_user(user)

    def update_current_user(self, user_id: str | None, claims: dict | None, payload: dict) -> AdminUserEntity | None:
        user = self._find_current_user(user_id, claims)
        if user is None:
            return None

        preferences = payload.get("preferences") if "preferences" in payload else None
        preference_value = self._encode_preferences(preferences if isinstance(preferences, dict) else None)

        with session_scope(self.database_url) as session:
            result = session.execute(update(UserRow).where(UserRow.id == user["id"]).values(preferences=preference_value))
            if not result.rowcount:
                raise RuntimeError("Unable to update current user")
            session.commit()

        refreshed = self._find_current_user(user_id, claims)
        return self._serialize_current_user(refreshed) if refreshed is not None else None

    def _parse_workspaces(self, user: UserRow | dict[str, Any]) -> list[str]:
        workspaces_value = user.workspaces if isinstance(user, UserRow) else user.get("workspaces")
        if workspaces_value:
            return [workspace.strip() for workspace in str(workspaces_value).split(";") if workspace and workspace.strip()]
        workspace_value = user.get("workspace") if isinstance(user, dict) else None
        if workspace_value:
            workspace = str(workspace_value).strip()
            return [workspace] if workspace else []
        return []

    def _payload_workspaces(self, payload: dict[str, Any], existing: UserRow) -> list[str]:
        if isinstance(payload.get("workspaces"), list):
            return [str(workspace) for workspace in payload["workspaces"]]
        return self._parse_workspaces(existing)

    def _assert_workspace_capacity(self, user_id: str, workspaces: list[str], max_users_per_workspace: int) -> None:
        with session_scope(self.database_url) as session:
            rows = session.execute(select(UserRow.id, UserRow.workspaces)).all()

        workspace_counts: dict[str, int] = {}
        for row_id, row_workspaces in rows:
            if str(row_id) == str(user_id):
                continue
            parsed = [item.strip() for item in str(row_workspaces or "").split(";") if item and item.strip()]
            for workspace in set(parsed):
                workspace_counts[workspace] = workspace_counts.get(workspace, 0) + 1

        for workspace in {item for item in workspaces if item.strip()}:
            if workspace_counts.get(workspace, 0) + 1 > max_users_per_workspace:
                raise ValueError(f"User limit reached for workspace {workspace} ({max_users_per_workspace})")

    def _fetch_user(self, user_id: str) -> AdminUserEntity | None:
        with session_scope(self.database_url) as session:
            user = session.get(UserRow, user_id)
            if user is None:
                return None
            role_rows = session.execute(select(UserRoleRow.role_id).where(UserRoleRow.user_id == user_id)).all()
            role_defs = session.execute(select(RoleRow.id, RoleRow.name, RoleRow.workspace, RoleRow.permissions)).all()

        role_ids = [str(role_id) for (role_id,) in role_rows if role_id is not None]
        role_meta_by_id = {
            str(role_id): {
                "name": str(role_name or role_id),
                "workspace": str(role_workspace or "").strip(),
                "permissions": self._decode_permissions(raw_permissions),
            }
            for role_id, role_name, role_workspace, raw_permissions in role_defs
            if role_id is not None
        }

        user_payload = {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "external_id": user.external_id,
            "preferences": user.preferences,
            "roles": role_ids,
            "workspaces": self._parse_workspaces(user),
            "workspace_roles": self._build_workspace_roles(role_ids, self._parse_workspaces(user), role_meta_by_id),
        }
        return self._to_user_entity(user_payload)

    def _find_current_user(self, user_id: str | None, claims: dict | None = None) -> dict | None:
        claim_map = claims or {}

        with session_scope(self.database_url) as session:
            if user_id:
                row = session.get(UserRow, user_id)
                if row is not None:
                    return self._user_row_to_dict(row)

            email = claim_map.get("email")
            if email:
                row = session.execute(select(UserRow).where(func.lower(UserRow.email) == func.lower(str(email))).limit(1)).scalar_one_or_none()
                if row is not None:
                    return self._user_row_to_dict(row)

            preferred_username = str(claim_map.get("preferred_username") or "").strip()
            if preferred_username:
                row = session.execute(
                    select(UserRow)
                    .where(func.lower(func.split_part(UserRow.email, "@", 1)) == func.lower(preferred_username))
                    .order_by(UserRow.id)
                    .limit(1)
                ).scalar_one_or_none()
                if row is not None:
                    return self._user_row_to_dict(row)

            subject = claim_map.get("sub")
            if subject:
                # Try to resolve by OIDC subject/external_id. Some deployments
                # store the provider `sub` in `users.external_id` or as the
                # primary key `users.id`. When found, prefer DB values but
                # populate missing name/email from claims for the current
                # request to avoid showing anonymous/Guest UI for SSO users.
                user_row = session.get(UserRow, subject)
                if user_row is None:
                    user_row = session.execute(
                        select(UserRow).where(UserRow.external_id == subject).limit(1)
                    ).scalar_one_or_none()

                if user_row is not None:
                    user_dict = self._user_row_to_dict(user_row)
                    # Fill missing email/name parts from claims for transient view
                    if (not user_dict.get("email") or str(user_dict.get("email") or "").strip() == ""):
                        claim_email = claim_map.get("email")
                        if claim_email:
                            user_dict["email"] = str(claim_email)
                    current_display_name = compose_user_display_name(
                        user_dict.get("first_name"),
                        user_dict.get("last_name"),
                    )
                    if not current_display_name:
                        first_name, last_name = name_parts_from_profile(
                            claim_map,
                            fallback=claim_map.get("preferred_username") or user_dict.get("email") or user_dict.get("id"),
                        )
                        user_dict["first_name"] = first_name
                        user_dict["last_name"] = last_name
                    return user_dict

        return None

    def _serialize_current_user(self, user: dict[str, Any]) -> AdminUserEntity:
        with session_scope(self.database_url) as session:
            role_rows = session.execute(select(UserRoleRow.role_id).where(UserRoleRow.user_id == user["id"])).all()
            role_defs = session.execute(select(RoleRow.id, RoleRow.name, RoleRow.workspace, RoleRow.permissions)).all()

        role_ids = [str(role_id) for (role_id,) in role_rows if role_id is not None]
        role_meta_by_id = {
            str(role_id): {
                "name": str(role_name or role_id),
                "workspace": str(role_workspace or "").strip(),
                "permissions": self._decode_permissions(raw_permissions),
            }
            for role_id, role_name, role_workspace, raw_permissions in role_defs
            if role_id is not None
        }
        return self._to_user_entity(
            {
                **dict(user),
                "roles": role_ids,
                "workspaces": self._parse_workspaces(user),
                "workspace_roles": self._build_workspace_roles(role_ids, self._parse_workspaces(user), role_meta_by_id),
                "preferences": self._decode_preferences(user.get("preferences")),
            }
        )

    def _to_user_entity(self, user: dict[str, Any]) -> AdminUserEntity:
        preferences_raw = user.get("preferences")
        if isinstance(preferences_raw, dict):
            preferences = dict(preferences_raw)
        else:
            preferences = self._decode_preferences(preferences_raw) or {}
        roles = list(user.get("roles") or [])
        workspaces = list(user.get("workspaces") or [])
        workspace_roles = [
            UserWorkspaceRoleEntity.model_validate(item)
            if isinstance(item, dict)
            else item
            for item in list(user.get("workspace_roles") or [])
        ]
        workspace_roles = self._build_exception_fact_access_workspace_roles(str(user.get("id") or "")) + workspace_roles
        granted_scopes = list(user.get("granted_scopes") or self._get_granted_scopes(roles))
        granted_scopes.extend(self._get_active_exception_fact_access_scopes(str(user.get("id") or ""), workspaces))
        return AdminUserEntity(
            id=str(user.get("id") or ""),
            first_name=str(user.get("first_name") or ""),
            last_name=str(user.get("last_name") or ""),
            email=user.get("email"),
            roles=roles,
            granted_scopes=sorted({str(scope).strip() for scope in granted_scopes if str(scope).strip()}),
            workspaces=workspaces,
            workspace_roles=workspace_roles,
            preferences=preferences,
            external_id=user.get("external_id"),
        )

    def _build_workspace_roles(
        self,
        role_ids: list[str],
        workspaces: list[str],
        role_meta_by_id: dict[str, dict[str, Any]],
    ) -> list[UserWorkspaceRoleEntity]:
        normalized_role_ids = [str(role_id).strip() for role_id in role_ids if str(role_id).strip()]
        normalized_workspaces = [str(workspace).strip() for workspace in workspaces if str(workspace).strip()]
        if not normalized_role_ids or not normalized_workspaces:
            return []

        workspace_roles: list[UserWorkspaceRoleEntity] = []
        for workspace in normalized_workspaces:
            exact_matches = [
                role_id
                for role_id in normalized_role_ids
                if self._role_matches_workspace(role_meta_by_id.get(role_id), workspace)
            ]
            candidate_role_ids = exact_matches or [
                role_id
                for role_id in normalized_role_ids
                if self._role_is_global(role_meta_by_id.get(role_id))
            ]
            if not candidate_role_ids:
                candidate_role_ids = normalized_role_ids

            selected_role_id = self._select_best_role_id(candidate_role_ids, role_meta_by_id)
            workspace_roles.append(
                UserWorkspaceRoleEntity(
                    workspace_id=workspace,
                    role=self._classify_role(selected_role_id, role_meta_by_id.get(selected_role_id)),
                )
            )

        return workspace_roles

    def _select_best_role_id(self, role_ids: list[str], role_meta_by_id: dict[str, dict[str, Any]]) -> str:
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
            "exception-fact-investigator": 1,
            "exception-fact-reader": 1,
            "admin": 3,
            "data-steward": 2,
            "analyst": 1,
            "auditor": 1,
            "regulator": 1,
            "viewer": 0,
        }
        return priorities.get(role, 0)

    def _role_matches_workspace(self, meta: dict[str, Any] | None, workspace: str) -> bool:
        if not meta:
            return False
        return str(meta.get("workspace") or "").strip() == workspace

    def _role_is_global(self, meta: dict[str, Any] | None) -> bool:
        if not meta:
            return False
        return str(meta.get("workspace") or "").strip().lower() == "global"

    def _classify_role(self, role_id: str, meta: dict[str, Any] | None) -> str:
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

    def _decode_preferences(self, value: Any) -> dict | None:
        if value is None:
            return None
        import json

        try:
            parsed = json.loads(str(value)) if not isinstance(value, dict) else value
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _encode_preferences(self, value: dict | None) -> str | None:
        if value is None:
            return None
        import json

        return json.dumps(value)

    def _decode_permissions(self, value: Any) -> list[str]:
        if value is None:
            return []
        import json

        if isinstance(value, list):
            parsed = value
        else:
            try:
                parsed = json.loads(str(value))
            except Exception:
                return []
        if not isinstance(parsed, list):
            return []
        return sorted({str(permission).strip() for permission in parsed if str(permission).strip()})

    def _encode_permissions(self, value: Any) -> str:
        permissions = self._decode_permissions(value if isinstance(value, str) else value or [])
        import json

        return json.dumps(permissions)

    def _get_granted_scopes(self, role_ids: list[str]) -> list[str]:
        if not role_ids:
            return []
        with session_scope(self.database_url) as session:
            rows = session.execute(select(RoleRow.id, RoleRow.permissions).where(RoleRow.id.in_(role_ids))).all()
        permissions: list[str] = []
        for _, raw_permissions in rows:
            permissions.extend(self._decode_permissions(raw_permissions))
        return self._expand_permissions(permissions)

    def _expand_permissions(self, permissions: list[str]) -> list[str]:
        return sorted(expand_granted_scopes(permissions))

    def _get_active_exception_fact_access_scopes(self, user_id: str, workspaces: list[str]) -> list[str]:
        if not user_id or not workspaces:
            return []
        normalized_workspaces = {str(workspace).strip() for workspace in workspaces if str(workspace).strip()}
        if not normalized_workspaces:
            return []

        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(ExceptionFactAccessRequestRow.requested_duration_minutes, ExceptionFactAccessRequestRow.role_id)
                .where(ExceptionFactAccessRequestRow.requester_id == user_id)
                .where(ExceptionFactAccessRequestRow.status == "approved")
                .where(ExceptionFactAccessRequestRow.workspace_id.in_(sorted(normalized_workspaces)))
                .where(ExceptionFactAccessRequestRow.expires_at.is_not(None))
            ).all()
            role_ids = [str(role_id or "").strip() for _, role_id in rows if str(role_id or "").strip()]
            if not role_ids:
                return []
            now = datetime.now(UTC).replace(tzinfo=None)
            active_rows = session.execute(
                select(ExceptionFactAccessRequestRow)
                .where(ExceptionFactAccessRequestRow.requester_id == user_id)
                .where(ExceptionFactAccessRequestRow.status == "approved")
                .where(ExceptionFactAccessRequestRow.workspace_id.in_(sorted(normalized_workspaces)))
            ).scalars().all()
            role_ids = [
                str(row.role_id or "").strip()
                for row in active_rows
                if row.expires_at is not None and row.expires_at > now and str(row.role_id or "").strip()
            ]
            if not role_ids:
                return []
            role_rows = session.execute(select(RoleRow.id, RoleRow.permissions).where(RoleRow.id.in_(role_ids))).all()

        permissions: list[str] = []
        for _, raw_permissions in role_rows:
            permissions.extend(self._decode_permissions(raw_permissions))
        return self._expand_permissions(permissions)

    def _build_exception_fact_access_workspace_roles(self, user_id: str) -> list[UserWorkspaceRoleEntity]:
        if not user_id:
            return []
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(ExceptionFactAccessRequestRow)
                .where(ExceptionFactAccessRequestRow.requester_id == user_id)
                .where(ExceptionFactAccessRequestRow.status == "approved")
            ).scalars().all()

        now = datetime.now(UTC).replace(tzinfo=None)
        return [
            UserWorkspaceRoleEntity(
                workspace_id=str(row.workspace_id or ""),
                role=self._classify_role(str(row.role_id or ""), {"name": str(row.role_id or ""), "workspace": str(row.workspace_id or ""), "permissions": []}),
            )
            for row in rows
            if row.expires_at is not None and row.expires_at > now
        ]

    def _timeout_pending_exception_fact_access_requests(self, session, request_timeout_minutes: int | None) -> None:
        timeout_minutes = max(0, int(request_timeout_minutes or 0))
        if timeout_minutes <= 0:
            return

        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=timeout_minutes)
        now = datetime.now(UTC).replace(tzinfo=None)
        stale_rows = session.execute(
            select(ExceptionFactAccessRequestRow).where(
                ExceptionFactAccessRequestRow.status == "pending",
                ExceptionFactAccessRequestRow.requested_at <= cutoff,
            )
        ).scalars().all()
        if not stale_rows:
            return

        for row in stale_rows:
            row.status = "timed_out"
            row.reviewed_by = None
            row.reviewed_at = now
            row.expires_at = None
        session.commit()

    def _fetch_exception_fact_access_request(self, request_id: str) -> ExceptionFactAccessRequestRow | None:
        with session_scope(self.database_url) as session:
            return session.get(ExceptionFactAccessRequestRow, request_id)

    @staticmethod
    def _read_duration_minutes(value: object) -> int:
        try:
            duration = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return max(0, duration)

    @staticmethod
    def _to_exception_fact_access_request_entity(row: ExceptionFactAccessRequestRow) -> ExceptionFactAccessRequestEntity:
        def _to_text(value: datetime | None) -> str | None:
            if value is None:
                return None
            return value.isoformat().replace("+00:00", "Z")

        return ExceptionFactAccessRequestEntity(
            id=str(row.id or ""),
            requesterId=str(row.requester_id or ""),
            workspaceId=str(row.workspace_id or ""),
            roleId=str(row.role_id or ""),
            status=str(row.status or "pending"),
            requestedDurationMinutes=int(row.requested_duration_minutes or 0),
            comments=str(row.comments or "").strip() or None,
            requestedAt=_to_text(row.requested_at) or "",
            reviewedBy=str(row.reviewed_by or "").strip() or None,
            reviewedAt=_to_text(row.reviewed_at),
            expiresAt=_to_text(row.expires_at),
        )
    @staticmethod
    def _user_row_to_dict(row: UserRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "email": row.email,
            "workspaces": row.workspaces,
            "preferences": row.preferences,
            "external_id": row.external_id,
        }
