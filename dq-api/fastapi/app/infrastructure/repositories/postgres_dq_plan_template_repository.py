from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import select

from app.domain.entities import DQPlanTemplateEntity
from app.domain.interfaces import DQPlanTemplateRepository
from app.infrastructure.orm.models import DQPlanTemplateRow
from app.infrastructure.orm.models import DQPlanTemplateVersionRow
from app.infrastructure.orm.session import session_scope


class PostgresDQPlanTemplateRepository(DQPlanTemplateRepository):
    """PostgreSQL implementation of DQ Plan Template repository."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def create_template(self, template: DQPlanTemplateEntity) -> DQPlanTemplateEntity:
        """Create a new template."""
        with session_scope(self.database_url) as session:
            # Check if template with this ID already exists
            existing = session.get(DQPlanTemplateRow, template.template_id)
            if existing:
                raise ValueError(f"Template '{template.template_id}' already exists")

            now = datetime.now(UTC)
            template_row = DQPlanTemplateRow(
                template_id=template.template_id,
                template_name=template.template_name,
                template_description=template.template_description,
                template_version=template.template_version,
                template_type=template.template_type,
                domain=template.domain,
                tags=list(template.tags),
                workspace_id=template.workspace_id,
                parameters_json=self._serialize_parameters(template.parameters),
                scope_json=self._serialize_entity(template.scope) if template.scope else None,
                suites_json=self._serialize_suites(template.suites),
                configuration_json=self._serialize_entity(template.configuration),
                schedule_json=self._serialize_entity(template.schedule),
                owner=template.owner,
                approver=template.approver,
                approved=template.approved,
                approval_date=template.approval_date,
                created_by=template.created_by,
                created_at=now,
                updated_by=template.updated_by,
                updated_at=now,
                is_active=template.is_active,
                is_default=template.is_default,
            )

            session.add(template_row)
            session.commit()
            session.refresh(template_row)

            return template

    async def get_template(
        self,
        template_id: str,
        version: str | None = None,
    ) -> DQPlanTemplateEntity | None:
        """Get a template by ID and optional version."""
        with session_scope(self.database_url) as session:
            stmt = select(DQPlanTemplateRow).where(
                DQPlanTemplateRow.template_id == template_id
            )
            if version:
                stmt = stmt.where(DQPlanTemplateRow.template_version == version)

            row = session.execute(stmt).scalars().first()
            if not row:
                return None

            return self._row_to_entity(row)

    async def get_template_by_version(
        self,
        template_id: str,
        version: str,
    ) -> DQPlanTemplateEntity | None:
        """Get a specific version of a template."""
        return await self.get_template(template_id, version=version)

    async def list_templates(
        self,
        *,
        workspace_id: str | None = None,
        domain: str | None = None,
        template_type: str | None = None,
        tags: list[str] | None = None,
        is_active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DQPlanTemplateEntity]:
        """List templates with optional filters."""
        with session_scope(self.database_url) as session:
            stmt = select(DQPlanTemplateRow)

            if workspace_id:
                stmt = stmt.where(DQPlanTemplateRow.workspace_id == workspace_id)
            if domain:
                stmt = stmt.where(DQPlanTemplateRow.domain == domain)
            if template_type:
                stmt = stmt.where(DQPlanTemplateRow.template_type == template_type)
            if is_active is not None:
                stmt = stmt.where(DQPlanTemplateRow.is_active == is_active)

            if tags:
                # Match if any tag exists
                stmt = stmt.where(
                    DQPlanTemplateRow.tags.overlap(tags)
                )

            stmt = stmt.order_by(DQPlanTemplateRow.updated_at.desc())
            stmt = stmt.limit(limit).offset(offset)

            rows = session.execute(stmt).scalars().all()
            return [self._row_to_entity(row) for row in rows]

    async def update_template(self, template: DQPlanTemplateEntity) -> DQPlanTemplateEntity:
        """Update an existing template."""
        with session_scope(self.database_url) as session:
            row = session.get(DQPlanTemplateRow, template.template_id)
            if not row:
                raise ValueError(f"Template '{template.template_id}' not found")

            # Update fields
            row.template_name = template.template_name
            row.template_description = template.template_description
            row.template_version = template.template_version
            row.template_type = template.template_type
            row.domain = template.domain
            row.tags = list(template.tags)
            row.workspace_id = template.workspace_id
            row.parameters_json = self._serialize_parameters(template.parameters)
            row.scope_json = self._serialize_entity(template.scope) if template.scope else None
            row.suites_json = self._serialize_suites(template.suites)
            row.configuration_json = self._serialize_entity(template.configuration)
            row.schedule_json = self._serialize_entity(template.schedule)
            row.owner = template.owner
            row.approver = template.approver
            row.approved = template.approved
            row.approval_date = template.approval_date
            row.updated_by = template.updated_by
            row.updated_at = datetime.now(UTC)
            row.is_active = template.is_active
            row.is_default = template.is_default

            session.commit()
            session.refresh(row)

            return self._row_to_entity(row)

    async def delete_template(self, template_id: str) -> bool:
        """Delete a template."""
        with session_scope(self.database_url) as session:
            row = session.get(DQPlanTemplateRow, template_id)
            if not row:
                return False

            session.delete(row)
            session.commit()
            return True

    async def list_active_templates(
        self,
        *,
        workspace_id: str | None = None,
        domain: str | None = None,
    ) -> list[DQPlanTemplateEntity]:
        """List all active templates (current version)."""
        with session_scope(self.database_url) as session:
            stmt = select(DQPlanTemplateRow).where(
                DQPlanTemplateRow.is_active == True,
                DQPlanTemplateRow.is_default == True,
            )

            if workspace_id:
                stmt = stmt.where(DQPlanTemplateRow.workspace_id == workspace_id)
            if domain:
                stmt = stmt.where(DQPlanTemplateRow.domain == domain)

            stmt = stmt.order_by(DQPlanTemplateRow.template_name.asc())

            rows = session.execute(stmt).scalars().all()
            return [self._row_to_entity(row) for row in rows]

    async def get_template_versions(
        self,
        template_id: str,
    ) -> list[str]:
        """Get all versions of a template."""
        with session_scope(self.database_url) as session:
            stmt = select(DQPlanTemplateRow.template_version).where(
                DQPlanTemplateRow.template_id == template_id
            ).order_by(DQPlanTemplateRow.updated_at.desc())

            versions = session.execute(stmt).scalars().all()
            return list(versions)

    def _serialize_parameters(self, parameters: list) -> dict:
        """Serialize parameters list to JSON."""
        if not parameters:
            return {}

        return {
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "allowed_values": p.allowed_values,
                    "validation_regex": p.validation_regex,
                    "minimum": p.minimum,
                    "maximum": p.maximum,
                }
                for p in parameters
            ]
        }

    def _serialize_entity(self, entity: Any) -> dict | None:
        """Serialize a Pydantic entity to JSON."""
        if entity is None:
            return None

        if hasattr(entity, "model_dump"):
            return entity.model_dump(mode="python", by_alias=True, exclude_none=True)

        if isinstance(entity, dict):
            return entity

        return {"_type": type(entity).__name__, "data": str(entity)}

    def _serialize_suites(self, suites: list) -> list:
        """Serialize suites list to JSON."""
        if not suites:
            return []

        return [
            {
                "suite_id": s.suite_id,
                "suite_name": s.suite_name,
                "engine_type": s.engine_type,
                "rule_ids": s.rule_ids,
                "rule_definitions": s.rule_definitions,
                "configuration": s.configuration,
            }
            for s in suites
        ]

    def _row_to_entity(self, row: DQPlanTemplateRow) -> DQPlanTemplateEntity:
        """Convert a database row to a template entity."""
        parameters = []
        if row.parameters_json:
            for param_data in row.parameters_json.get("parameters", []):
                parameters.append(
                    self._param_data_to_entity(param_data)
                )

        scope = None
        if row.scope_json:
            scope = self._json_to_entity(row.scope_json)

        suites = [
            self._suite_data_to_entity(s)
            for s in (row.suites_json or [])
        ]

        configuration = None
        if row.configuration_json:
            configuration = self._json_to_entity(row.configuration_json)

        schedule = None
        if row.schedule_json:
            schedule = self._json_to_entity(row.schedule_json)

        return DQPlanTemplateEntity(
            template_id=row.template_id,
            template_name=row.template_name,
            template_description=row.template_description,
            template_version=row.template_version,
            template_type=row.template_type,
            domain=row.domain,
            tags=row.tags or [],
            workspace_id=row.workspace_id,
            parameters=parameters,
            scope=scope,
            suites=suites,
            configuration=configuration,
            schedule=schedule,
            owner=row.owner,
            approver=row.approver,
            approved=row.approved,
            approval_date=row.approval_date,
            created_by=row.created_by,
            created_at=row.created_at.isoformat() if row.created_at else None,
            updated_by=row.updated_by,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
            is_active=row.is_active,
            is_default=row.is_default,
        )

    def _param_data_to_entity(self, data: dict) -> Any:
        """Convert parameter JSON data to entity."""
        from app.domain.entities.dq_plan_template import DQPlanTemplateParameterEntity
        return DQPlanTemplateParameterEntity(
            name=data.get("name", ""),
            type=data.get("type", "string"),
            description=data.get("description"),
            required=data.get("required", True),
            default=data.get("default"),
            allowed_values=data.get("allowed_values"),
            validation_regex=data.get("validation_regex"),
            minimum=data.get("minimum"),
            maximum=data.get("maximum"),
        )

    def _suite_data_to_entity(self, data: dict) -> Any:
        """Convert suite JSON data to entity."""
        from app.domain.entities.dq_plan_template import DQPlanTemplateSuiteEntity
        return DQPlanTemplateSuiteEntity(
            suite_id=data.get("suite_id"),
            suite_name=data.get("suite_name"),
            engine_type=data.get("engine_type"),
            rule_ids=data.get("rule_ids"),
            rule_definitions=data.get("rule_definitions"),
            configuration=data.get("configuration", {}),
        )

    def _json_to_entity(self, data: dict) -> Any:
        """Convert JSON data to entity (dynamic)."""
        # This would normally use the specific entity types
        # For now, return the dict structure
        return data
