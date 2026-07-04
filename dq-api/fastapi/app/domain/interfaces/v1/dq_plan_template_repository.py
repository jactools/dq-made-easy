from typing import Protocol

from app.domain.entities import DQPlanTemplateEntity


class DQPlanTemplateRepository(Protocol):
    """Repository interface for DQ Plan templates."""
    
    async def create_template(self, template: DQPlanTemplateEntity) -> DQPlanTemplateEntity:
        """Create a new template."""
        ...
    
    async def get_template(
        self,
        template_id: str,
        version: str | None = None,
    ) -> DQPlanTemplateEntity | None:
        """Get a template by ID and optional version."""
        ...
    
    async def get_template_by_version(
        self,
        template_id: str,
        version: str,
    ) -> DQPlanTemplateEntity | None:
        """Get a specific version of a template."""
        ...
    
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
        ...
    
    async def update_template(
        self,
        template: DQPlanTemplateEntity,
    ) -> DQPlanTemplateEntity:
        """Update an existing template."""
        ...
    
    async def delete_template(self, template_id: str) -> bool:
        """Delete a template."""
        ...
    
    async def list_active_templates(
        self,
        *,
        workspace_id: str | None = None,
        domain: str | None = None,
    ) -> list[DQPlanTemplateEntity]:
        """List all active templates (current version)."""
        ...
    
    async def get_template_versions(
        self,
        template_id: str,
    ) -> list[str]:
        """Get all versions of a template."""
        ...
