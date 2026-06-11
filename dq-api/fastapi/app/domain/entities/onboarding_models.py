"""Domain models for guided rule generation (onboarding) feature."""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Literal

from app.domain.entities.base import EntityModel


class ProposedAttribute(EntityModel):
    """A single attribute in a proposal group."""

    attribute_id: str
    name: str
    data_type: str
    already_covered: bool = False


class ProposedObjectGroup(EntityModel):
    """Attributes grouped by data object."""

    data_object_version_id: str
    object_name: str
    dataset_name: str
    dataset_id: str
    count: int
    attributes: list[ProposedAttribute]


class ProposedTemplateGroup(EntityModel):
    """Rule proposals grouped by template."""

    template_id: str
    template_name: str
    dimension: str
    check_type: str
    total_count: int
    by_dataset: dict[str, list[ProposedObjectGroup]]


class GenerateProposalsRequest(EntityModel):
    """Request to generate rule proposals."""

    scope_type: Literal["workspace", "product", "dataset", "object"]
    scope_id: str
    workspace_id: str


class GenerateProposalsResponse(EntityModel):
    """Response with grouped rule proposals."""

    scope_type: str
    scope_id: str
    total_attributes: int
    total_proposals: int
    proposals: list[ProposedTemplateGroup]
    generated_at: datetime


class ScopeSummaryRequest(EntityModel):
    """Request to summarize object/attribute counts for a scope."""

    scope_type: Literal["workspace", "product", "dataset", "object"]
    scope_id: str
    workspace_id: str


class ScopeSummaryResponse(EntityModel):
    """Response with scope counts for UX preview."""

    scope_type: str
    scope_id: str
    workspace_id: str
    object_count: int
    attribute_count: int
    generated_at: datetime


class CreateBatchRequest(EntityModel):
    """Request to create draft rules from accepted proposals."""

    workspace_id: str
    accepted_proposal_ids: list[str]


class BatchRuleOutcome(EntityModel):
    """Outcome of one proposal in batch processing."""

    proposal_id: str
    status: Literal["created", "skipped", "failed"]
    rule_id: str | None = None
    reason: str | None = None


class CreateBatchResponse(EntityModel):
    """Batch creation summary and per-proposal outcomes."""

    batch_id: str
    workspace_id: str
    total_accepted: int
    created: int
    skipped: int
    failed: int
    outcomes: list[BatchRuleOutcome]
    created_at: datetime
