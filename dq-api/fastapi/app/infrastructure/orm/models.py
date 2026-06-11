"""
SQLAlchemy ORM model declarations for all database tables.

Models are organized by domain section:
  - Core:            workspaces, users, roles, user_roles
  - Rules:           rules, reusable_filters, rule_reusable_filters, reusable_joins, rule_attributes
  - Rule versioning: rule_versions, rule_version_diffs, rule_rollbacks, rule_version_relationships
  - Approvals:       approvals, audit
    - Data catalog:    data_products, data_sets, data_objects, data_objects_catalog,
                                         data_object_versions, attributes_catalog, data_deliveries,
                                         data_delivery_notes
  - Testing:         test_proofs, batch_test_requests
  - Configuration:   app_config, system_info
  - Profiling:       data_source_metadata, data_source_profiling_requests,
                     suggestions, suggestion_interactions

Schema source files:
  dq-db/init/01_schema.sql
  dq-db/init/02_profiling_schema.sql
  dq-db/init/04_rule_versioning.sql
    dq-db/init/05_rule_compiler_artifacts.sql

Known divergences between DDL files and the live database:
    - approvals.workspace  → renamed to workspace_id in the live DB (undocumented migration).
    - users.external_id    → added column for OIDC subject tracking; absent from original DDL.
  - Column names that appear as camelCase in the DDL (e.g. ruleId, approvalId) are stored
    lowercase by PostgreSQL (e.g. ruleid, approvalid) because the DDL uses unquoted identifiers.
    The ORM uses the lowercase names that PostgreSQL actually stores.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, column_property, mapped_column

from app.infrastructure.orm.base import Base

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


class WorkspaceRow(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alert_routing_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # PostgreSQL column: "workspaces"
    workspaces: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferences: Mapped[Optional[str]] = mapped_column(
        Text,
        server_default='{"display":{"theme":"auto"}}',
        nullable=True,
    )
    # Not in original 01_schema.sql; added for OIDC subject-claim tracking.
    external_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RoleRow(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace: Mapped[Optional[str]] = mapped_column(
        Text, server_default="default", nullable=True
    )
    permissions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class UserRoleRow(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class ExceptionFactAccessRequestRow(Base):
    __tablename__ = "exception_fact_access_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(Text, nullable=False)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="pending", nullable=False)
    requested_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_exception_fact_access_requests_workspace", "workspace_id"),
        Index("ix_exception_fact_access_requests_requester", "requester_id"),
        Index("ix_exception_fact_access_requests_status", "status"),
        Index("ix_exception_fact_access_requests_expires_at", "expires_at"),
    )


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class RuleRow(Base):
    """Maps to the *rules* table.

    Includes the versioning columns defined in the base rules schema.
    ``current_version_id`` is exposed as a derived field backed by the
    ``rule_current_versions`` table to avoid circular DDL dependencies.
    """

    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expression: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dimension: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    generated: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    is_template: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    template_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # DDL column is "createdBy" (unquoted) → stored by PostgreSQL as "createdby"
    created_by: Mapped[Optional[str]] = mapped_column("createdby", Text, nullable=True)
    last_approval_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_approval_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_approval_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_on: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggestion_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dsl: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    taxonomy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_steward: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domain_owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    technical_owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    join_conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alias_mappings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reusable_join_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    check_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    check_type_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manual_override_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manual_override_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    total_versions: Mapped[Optional[int]] = mapped_column(
        Integer, server_default="1", nullable=True
    )
    versioning_enabled: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="true", nullable=True
    )
    version_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    version_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ReusableFilterRow(Base):
    __tablename__ = "reusable_filters"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filter_expression: Mapped[str] = mapped_column(Text, nullable=False)
    workspace: Mapped[Optional[str]] = mapped_column(
        Text, server_default="default", nullable=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="true", nullable=True
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RuleReusableFilterRow(Base):
    """Association table linking rules to reusable filters."""

    __tablename__ = "rule_reusable_filters"

    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), primary_key=True
    )
    reusable_filter_id: Mapped[str] = mapped_column(
        ForeignKey("reusable_filters.id", ondelete="CASCADE"), primary_key=True
    )


class ReusableJoinRow(Base):
    __tablename__ = "reusable_joins"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    join_definition: Mapped[str] = mapped_column(Text, nullable=False)
    workspace: Mapped[Optional[str]] = mapped_column(
        Text, server_default="default", nullable=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="true", nullable=True
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RuleAttributeRow(Base):
    __tablename__ = "rule_attributes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # DDL columns "ruleId" / "attributeId" are stored lowercase by PostgreSQL
    rule_id: Mapped[Optional[str]] = mapped_column("ruleid", Text, nullable=True)
    attribute_id: Mapped[Optional[str]] = mapped_column("attributeid", Text, nullable=True)
    workspace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    threshold_override: Mapped[Optional[float]] = mapped_column("threshold_override", Numeric, nullable=True)


# ---------------------------------------------------------------------------
# Rule versioning  (04_rule_versioning.sql)
# ---------------------------------------------------------------------------


class RuleVersionRow(Base):
    """Immutable snapshot of a rule at a given version number."""

    __tablename__ = "rule_versions"
    __table_args__ = (
        UniqueConstraint("rule_id", "version_number", name="uq_rule_versions_rule_version_number"),
        UniqueConstraint("rule_id", "id", name="uq_rule_versions_rule_id_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Snapshot fields
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    dimension: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    is_template: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    template_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dsl: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    taxonomy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_steward: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domain_owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    technical_owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    check_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    check_type_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text()), nullable=True)
    marked_for_rollback: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    validation_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    validated_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RuleCurrentVersionRow(Base):
    """Stores the current immutable version pointer for each rule."""

    __tablename__ = "rule_current_versions"
    __table_args__ = (
        ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["rule_id", "version_id"],
            ["rule_versions.rule_id", "rule_versions.id"],
            ondelete="CASCADE",
        ),
    )

    rule_id: Mapped[str] = mapped_column(Text, primary_key=True)
    version_id: Mapped[str] = mapped_column(Text, nullable=False)


RuleRow.current_version_id = column_property(
    select(RuleCurrentVersionRow.version_id)
    .where(RuleCurrentVersionRow.rule_id == RuleRow.id)
    .correlate_except(RuleCurrentVersionRow)
    .scalar_subquery()
)


class RuleVersionDiffRow(Base):
    """Per-field change record between two rule versions."""

    __tablename__ = "rule_version_diffs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    from_version_id: Mapped[str] = mapped_column(
        ForeignKey("rule_versions.id", ondelete="CASCADE"), nullable=False
    )
    to_version_id: Mapped[str] = mapped_column(
        ForeignKey("rule_versions.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RuleRollbackRow(Base):
    """Audit trail for rule rollback operations."""

    __tablename__ = "rule_rollbacks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False
    )
    from_version_id: Mapped[str] = mapped_column(
        ForeignKey("rule_versions.id", ondelete="CASCADE"), nullable=False
    )
    to_version_id: Mapped[str] = mapped_column(
        ForeignKey("rule_versions.id", ondelete="CASCADE"), nullable=False
    )
    rolled_back_by: Mapped[str] = mapped_column(Text, nullable=False)
    rolled_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_version_created_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("rule_versions.id", ondelete="SET NULL"), nullable=True
    )


class RuleStatusHistoryRow(Base):
    """Immutable audit trail of rule lifecycle events."""

    __tablename__ = "rule_status_history"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RuleVersionRelationshipRow(Base):
    """Links a rule version to approvals, test proofs, and deployments."""

    __tablename__ = "rule_version_relationships"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("rule_versions.id", ondelete="CASCADE"), nullable=False
    )
    approval_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True
    )
    test_proof_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("test_proofs.id", ondelete="SET NULL"), nullable=True
    )
    deployment_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RuleVersionCompilerArtifactRow(Base):
    """Compiler artifacts generated for a specific immutable rule version."""

    __tablename__ = "rule_version_compiler_artifacts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    rule_version_id: Mapped[str] = mapped_column(
        ForeignKey("rule_versions.id", ondelete="CASCADE"), nullable=False
    )
    compiler_version: Mapped[str] = mapped_column(Text, nullable=False)
    compiler_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_key: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    diagnostics_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    compile_status: Mapped[str] = mapped_column(Text, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="true", nullable=True
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class GxSuiteRegistryRow(Base):
    """Registry for versioned GX suite artifacts."""

    __tablename__ = "gx_suite_registry"
    __table_args__ = (
        UniqueConstraint("suite_id", "suite_version", name="uq_gx_suite_registry_suite_version"),
        CheckConstraint(
            "status IN ('active', 'deprecated', 'disabled')",
            name="ck_gx_suite_registry_status",
        ),
        CheckConstraint(
            "data_object_id IS NOT NULL OR dataset_id IS NOT NULL OR data_product_id IS NOT NULL",
            name="ck_gx_suite_registry_assignment_scope",
        ),
        Index("ix_gx_suite_registry_data_object_status", "data_object_id", "status"),
        Index("ix_gx_suite_registry_dataset_status", "dataset_id", "status"),
        Index("ix_gx_suite_registry_data_product_status", "data_product_id", "status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    suite_id: Mapped[str] = mapped_column(Text, nullable=False)
    suite_version: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="v1"
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="active"
    )
    data_object_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dataset_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_product_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gx_suite_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    compiler_version: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    saved_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_pipeline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class GxSuiteExecutionTargetMapRow(Base):
    """Maps a suite version to one or more resolved execution target versions."""

    __tablename__ = "gx_suite_execution_target_map"
    __table_args__ = (
        ForeignKeyConstraint(
            ["suite_id", "suite_version"],
            ["gx_suite_registry.suite_id", "gx_suite_registry.suite_version"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "suite_id",
            "suite_version",
            "data_object_version_id",
            name="uq_gx_suite_execution_target_map",
        ),
        Index(
            "ix_gx_suite_execution_target_map_version",
            "data_object_version_id",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    suite_id: Mapped[str] = mapped_column(Text, nullable=False)
    suite_version: Mapped[int] = mapped_column(Integer, nullable=False)
    data_object_version_id: Mapped[str] = mapped_column(Text, nullable=False)


class GxSuiteRuleMapRow(Base):
    """Maps a suite version to the source DQ rule identifiers."""

    __tablename__ = "gx_suite_rule_map"
    __table_args__ = (
        ForeignKeyConstraint(
            ["suite_id", "suite_version"],
            ["gx_suite_registry.suite_id", "gx_suite_registry.suite_version"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "suite_id",
            "suite_version",
            "rule_id",
            name="uq_gx_suite_rule_map",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    suite_id: Mapped[str] = mapped_column(Text, nullable=False)
    suite_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)


class GxSuiteStatusHistoryRow(Base):
    """Immutable audit trail of every status transition for a GX suite version."""

    __tablename__ = "gx_suite_status_history"
    __table_args__ = (
        Index("ix_gx_suite_status_history_suite", "suite_id", "suite_version"),
        Index("ix_gx_suite_status_history_changed_at", "changed_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    suite_id: Mapped[str] = mapped_column(Text, nullable=False)
    suite_version: Mapped[int] = mapped_column(Integer, nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ValidationArtifactRegistryRow(Base):
    """Registry for engine-neutral validation artifacts."""

    __tablename__ = "validation_artifact_registry"
    __table_args__ = (
        UniqueConstraint(
            "validation_artifact_id",
            "validation_artifact_version",
            name="uq_validation_artifact_registry_artifact_version",
        ),
        CheckConstraint(
            "status IN ('active', 'deprecated', 'disabled')",
            name="ck_validation_artifact_registry_status",
        ),
        CheckConstraint(
            "data_object_id IS NOT NULL OR dataset_id IS NOT NULL OR data_product_id IS NOT NULL",
            name="ck_validation_artifact_registry_assignment_scope",
        ),
        Index(
            "ix_validation_artifact_registry_artifact_status",
            "validation_artifact_id",
            "status",
        ),
        Index(
            "ix_validation_artifact_registry_data_object_status",
            "data_object_id",
            "status",
        ),
        Index(
            "ix_validation_artifact_registry_dataset_status",
            "dataset_id",
            "status",
        ),
        Index(
            "ix_validation_artifact_registry_data_product_status",
            "data_product_id",
            "status",
        ),
        Index(
            "ix_validation_artifact_registry_engine_status",
            "engine_type",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    validation_artifact_id: Mapped[str] = mapped_column(Text, nullable=False)
    validation_artifact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_contract_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="v1"
    )
    engine_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    data_object_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dataset_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_product_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_data_object_version_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    compiled_rule_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    compiler_version: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    envelope_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    saved_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_pipeline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ValidationArtifactStatusHistoryRow(Base):
    """Immutable audit trail of every status transition for a validation artifact version."""

    __tablename__ = "validation_artifact_status_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["validation_artifact_id", "validation_artifact_version"],
            [
                "validation_artifact_registry.validation_artifact_id",
                "validation_artifact_registry.validation_artifact_version",
            ],
            ondelete="CASCADE",
        ),
        Index(
            "ix_validation_artifact_status_history_artifact",
            "validation_artifact_id",
            "validation_artifact_version",
        ),
        Index(
            "ix_validation_artifact_status_history_changed_at",
            "changed_at",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    validation_artifact_id: Mapped[str] = mapped_column(Text, nullable=False)
    validation_artifact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ValidationRunPlanRow(Base):
    """Engine-neutral scheduling plan with draft and active lifecycle state."""

    __tablename__ = "validation_run_plans"
    __table_args__ = (
        Index("ix_validation_run_plans_workspace", "workspace_id"),
        Index("ix_validation_run_plans_status", "status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    business_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace_id: Mapped[str] = mapped_column(Text, nullable=False)
    scope_selector_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    planning_mode: Mapped[str] = mapped_column(Text, nullable=False)
    current_active_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_dispatched_run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ValidationRunPlanVersionRow(Base):
    """Immutable snapshot of a neutral validation run-plan version."""

    __tablename__ = "validation_run_plan_versions"
    __table_args__ = (
        ForeignKeyConstraint(["run_plan_id"], ["validation_run_plans.id"], ondelete="CASCADE"),
        Index("ix_validation_run_plan_versions_plan", "run_plan_id", "created_at"),
        Index("ix_validation_run_plan_versions_artifact", "artifact_id", "artifact_version"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_plan_id: Mapped[str] = mapped_column(Text, nullable=False)
    validation_artifact_selection_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    artifact_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artifact_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    artifact_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    execution_contract_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    schedule_definition_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    governance_state: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ValidationRunPlanTransitionRow(Base):
    """Immutable audit event for neutral validation run-plan lifecycle transitions."""

    __tablename__ = "validation_run_plan_transitions"
    __table_args__ = (
        ForeignKeyConstraint(["run_plan_id"], ["validation_run_plans.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["run_plan_version_id"], ["validation_run_plan_versions.id"], ondelete="SET NULL"),
        Index("ix_validation_run_plan_transitions_plan_occurred_at", "run_plan_id", "occurred_at"),
        Index("ix_validation_run_plan_transitions_version_occurred_at", "run_plan_version_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_plan_id: Mapped[str] = mapped_column(Text, nullable=False)
    run_plan_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    from_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    details_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GxExecutionRunRow(Base):
    """Immutable execution lifecycle record for a GX suite run."""

    __tablename__ = "gx_execution_runs"
    __table_args__ = (
        UniqueConstraint(
            "correlation_id",
            "suite_id",
            "suite_version",
            name="uq_gx_execution_runs_correlation_suite",
        ),
        Index("ix_gx_execution_runs_suite", "suite_id", "suite_version"),
        Index("ix_gx_execution_runs_status", "status"),
        Index("ix_gx_execution_runs_submitted_at", "submitted_at"),
        Index("ix_gx_execution_runs_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    suite_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suite_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rule_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    engine_type: Mapped[str] = mapped_column(Text, nullable=False)
    engine_target: Mapped[str] = mapped_column(Text, nullable=False)
    execution_shape: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_progress_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    execution_contract_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    handoff_payload_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    result_summary_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    diagnostics_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class GxExecutionRunStatusHistoryRow(Base):
    """Immutable audit trail of every status transition for a GX execution run."""

    __tablename__ = "gx_execution_run_status_history"
    __table_args__ = (
        ForeignKeyConstraint(["run_id"], ["gx_execution_runs.id"], ondelete="CASCADE"),
        Index("ix_gx_execution_run_status_history_run", "run_id", "changed_at"),
        Index("ix_gx_execution_run_status_history_changed_at", "changed_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class DqResultEventRow(Base):
    """Immutable event history for GX result reporting and future trend analysis."""

    __tablename__ = "dq_result_events"
    __table_args__ = (
        UniqueConstraint("correlation_id", "run_id", "run_status", name="uq_dq_result_events_run_status"),
        Index("ix_dq_result_events_emitted_at", "emitted_at"),
        Index("ix_dq_result_events_rule_emitted_at", "rule_id", "emitted_at"),
        Index("ix_dq_result_events_dataset_emitted_at", "dataset_id", "emitted_at"),
        Index("ix_dq_result_events_domain_emitted_at", "domain_id", "emitted_at"),
        Index("ix_dq_result_events_data_product_emitted_at", "dataset_data_product_id", "emitted_at"),
        Index("ix_dq_result_events_correlation_id", "correlation_id"),
        Index("ix_dq_result_events_run_status", "run_status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_version: Mapped[str] = mapped_column(Text, nullable=False)
    emitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dataset_workspace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dataset_data_product_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dataset_data_object_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dataset_data_object_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domain_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domain_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_version_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_status: Mapped[str] = mapped_column(Text, nullable=False)
    run_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    run_total_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_valid_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_invalid_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_warning_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_error_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_score: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    run_score_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    queue_message_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_correlation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_system: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score_dimensions_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    event_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class GxRunPlanRow(Base):
    """User-managed scheduling plan with separate draft/active lifecycle."""

    __tablename__ = "gx_run_plans"
    __table_args__ = (
        Index("ix_gx_run_plans_workspace", "workspace_id"),
        Index("ix_gx_run_plans_status", "status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    business_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace_id: Mapped[str] = mapped_column(Text, nullable=False)
    scope_selector_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    planning_mode: Mapped[str] = mapped_column(Text, nullable=False)
    current_active_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_dispatched_run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class GxRunPlanVersionRow(Base):
    """Immutable snapshot of a run plan version."""

    __tablename__ = "gx_run_plan_versions"
    __table_args__ = (
        ForeignKeyConstraint(["run_plan_id"], ["gx_run_plans.id"], ondelete="CASCADE"),
        Index("ix_gx_run_plan_versions_plan", "run_plan_id", "created_at"),
        Index("ix_gx_run_plan_versions_suite", "suite_id", "suite_version"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_plan_id: Mapped[str] = mapped_column(Text, nullable=False)
    gx_suite_selection_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    suite_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suite_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    suite_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    execution_contract_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    schedule_definition_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    governance_state: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GxRunPlanTransitionRow(Base):
    """Immutable audit event for a GX run plan lifecycle transition."""

    __tablename__ = "gx_run_plan_transitions"
    __table_args__ = (
        ForeignKeyConstraint(["run_plan_id"], ["gx_run_plans.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["run_plan_version_id"], ["gx_run_plan_versions.id"], ondelete="SET NULL"),
        Index("ix_gx_run_plan_transitions_plan_occurred_at", "run_plan_id", "occurred_at"),
        Index("ix_gx_run_plan_transitions_version_occurred_at", "run_plan_version_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_plan_id: Mapped[str] = mapped_column(Text, nullable=False)
    run_plan_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    from_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    details_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GxExecutionViolationRow(Base):
    """Scoped row-level violation record for a single data object version."""

    __tablename__ = "gx_execution_violations"
    __table_args__ = (
        PrimaryKeyConstraint("data_object_version_id", "id"),
        ForeignKeyConstraint(["execution_run_id"], ["gx_execution_runs.id"], ondelete="CASCADE"),
        Index("ix_gx_execution_violations_data_object_detected_at", "data_object_version_id", "detected_at"),
        Index("ix_gx_execution_violations_run", "data_object_version_id", "execution_run_id", "detected_at"),
        Index("ix_gx_execution_violations_rule", "data_object_version_id", "rule_id", "detected_at"),
    )

    data_object_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    id: Mapped[str] = mapped_column(Text, nullable=False)
    execution_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    data_primary_key: Mapped[str] = mapped_column(Text, nullable=False)
    violation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    ops_metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class GxExceptionAnalysisSliceRow(Base):
    __tablename__ = "gx_exception_analysis_slices"
    __table_args__ = (
        PrimaryKeyConstraint("analysis_session_id", "analysis_slice_id"),
        Index("ix_gx_exception_analysis_slices_session", "analysis_session_id", "slice_index"),
        Index("ix_gx_exception_analysis_slices_anchor", "data_object_version_id", "execution_run_id", "rule_id", "slice_index"),
    )

    analysis_session_id: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_slice_id: Mapped[str] = mapped_column(Text, nullable=False)
    slice_index: Mapped[int] = mapped_column(Integer, nullable=False)
    data_object_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    execution_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    slice_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    anchor_total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_matching_count: Mapped[int] = mapped_column(Integer, nullable=False)
    returned_count: Mapped[int] = mapped_column(Integer, nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    filters_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    next_slice_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    analysis_pack_uri: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_pack_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_manifest_uri: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class ExceptionReasonAnalyticsProjectionRow(Base):
    __tablename__ = "exception_reason_analytics_projection"
    __table_args__ = (
        Index("ix_exception_reason_analytics_projection_bucket", "bucket_start"),
        Index("ix_exception_reason_analytics_projection_scope", "data_object_version_id", "bucket_start"),
        Index("ix_exception_reason_analytics_projection_reason", "reason_code", "bucket_start"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    engine_type: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_plan_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_plan_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suite_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_object_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    reason_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    failed_record_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    distinct_record_identifier_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    distinct_execution_run_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    record_identifier_values_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    execution_run_ids_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


class ApprovalRow(Base):
    """Maps to the *approvals* table.

    Note: the DDL has ``workspace TEXT``; the live database uses ``workspace_id``
    after an applied (but undocumented) migration.
    """

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    business_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # DDL "ruleId" → PostgreSQL stores as "ruleid"
    rule_id: Mapped[Optional[str]] = mapped_column("ruleid", Text, nullable=True)
    effective_status: Mapped[Optional[str]] = mapped_column("effectivestatus", Text, nullable=True)
    gx_run_plan_id: Mapped[Optional[str]] = mapped_column("gxrunplanid", Text, nullable=True)
    gx_run_plan_version_id: Mapped[Optional[str]] = mapped_column("gxrunplanversionid", Text, nullable=True)
    rule_attribute_id: Mapped[Optional[str]] = mapped_column(
        "ruleattributeid", Text, nullable=True
    )
    status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # DDL "requesterId" → PostgreSQL stores as "requesterid"
    requester_id: Mapped[Optional[str]] = mapped_column("requesterid", Text, nullable=True)
    requested_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acted_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # DDL had "workspace"; live DB column is also "workspace".
    workspace_id: Mapped[Optional[str]] = mapped_column("workspace", Text, nullable=True)


class AuditRow(Base):
    __tablename__ = "audit"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # DDL "approvalId" → PostgreSQL stores as "approvalid"
    approval_id: Mapped[Optional[str]] = mapped_column("approvalid", Text, nullable=True)
    action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # DDL "actorId" → PostgreSQL stores as "actorid"
    actor_id: Mapped[Optional[str]] = mapped_column("actorid", Text, nullable=True)
    timestamp: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ConnectorRegistryRow(Base):
    __tablename__ = "connector_registry"

    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    implementation_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    capabilities_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    supported_asset_kinds_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConnectorInstanceRow(Base):
    __tablename__ = "connector_instances"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    configuration_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Data catalog
# ---------------------------------------------------------------------------


class DataProductRow(Base):
    __tablename__ = "data_products"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        Text, server_default="default", nullable=True
    )
    odcs_data_product_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DataSetRow(Base):
    __tablename__ = "data_sets"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    product_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("data_products.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        Text, server_default="default", nullable=True
    )
    business_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DataObjectRow(Base):
    __tablename__ = "data_objects"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DataObjectCatalogRow(Base):
    __tablename__ = "data_objects_catalog"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("data_sets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    latest_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DataObjectVersionRow(Base):
    __tablename__ = "data_object_versions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    data_object_id: Mapped[str] = mapped_column(
        ForeignKey("data_objects_catalog.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    schema_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attribute_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    storage_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_options_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class AttributeCatalogRow(Base):
    __tablename__ = "attributes_catalog"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    nullable: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_cde: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    is_primary_key: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    is_business_key: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default="false", nullable=True
    )
    masking_method: Mapped[Optional[str]] = mapped_column(Text, nullable=True, server_default="none")
    encryption_required: Mapped[Optional[bool]] = mapped_column(Boolean, server_default="false", nullable=True)
    encryption_key_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_object_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("data_objects_catalog.id", ondelete="CASCADE"), nullable=True
    )
    version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("data_object_versions.id", ondelete="CASCADE"), nullable=True
    )


class DataEncryptionKeyRow(Base):
    __tablename__ = "data_encryption_keys"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    key_name: Mapped[str] = mapped_column(Text, nullable=False)
    key_scope: Mapped[str] = mapped_column(Text, nullable=False, server_default="app")
    workspace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_algorithm: Mapped[str] = mapped_column(Text, nullable=False, server_default="fernet")
    key_material_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    key_fingerprint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default="true", nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class AttributeDefinitionMappingRow(Base):
    __tablename__ = "attribute_definition_mappings"
    __table_args__ = (
        UniqueConstraint("attribute_id", name="uq_attribute_definition_mappings_attribute_id"),
        CheckConstraint("mapping_state IN ('mapped', 'unmapped')", name="ck_attribute_definition_mappings_state"),
        CheckConstraint(
            "(mapping_state = 'mapped' AND definition_id IS NOT NULL) OR (mapping_state = 'unmapped' AND definition_id IS NULL)",
            name="ck_attribute_definition_mappings_definition_consistency",
        ),
        Index("ix_attribute_definition_mappings_definition_id", "definition_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    attribute_id: Mapped[str] = mapped_column(
        ForeignKey("attributes_catalog.id", ondelete="CASCADE"), nullable=False
    )
    definition_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mapping_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="mapped")
    mapped_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class DataDeliveryRow(Base):
    __tablename__ = "data_deliveries"
    __table_args__ = (
        Index("ix_data_deliveries_data_object_version_id", "data_object_version_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    data_object_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("data_object_versions.id", ondelete="CASCADE"), nullable=True
    )
    data_object_id: Mapped[str] = mapped_column(
        ForeignKey("data_objects_catalog.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    layer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivery_location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    record_count: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attributes_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class DataDeliveryNoteRow(Base):
    __tablename__ = "data_delivery_notes"

    data_delivery_id: Mapped[str] = mapped_column(
        ForeignKey("data_deliveries.id", ondelete="CASCADE"), primary_key=True
    )
    layer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivery_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ingestor_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ingestor_run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_system: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_snapshot_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checksum_algorithm: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class MasterRecordRow(Base):
    __tablename__ = "master_records"
    __table_args__ = (
        Index("ix_master_records_domain", "domain"),
        Index("ix_master_records_workspace_id", "workspace_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    domain: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    golden_record_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    match_rule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    survivorship_rule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_systems: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    merged_from_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class DataAssetRow(Base):
    __tablename__ = "data_assets"
    __table_args__ = (
        UniqueConstraint("id", name="uq_data_assets_id"),
        Index("ix_data_assets_workspace_name", "workspace_id", "name"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    current_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_object_version_ids_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    business_context_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class DataAssetVersionRow(Base):
    __tablename__ = "data_asset_versions"
    __table_args__ = (
        UniqueConstraint("data_asset_id", "version", name="uq_data_asset_versions_asset_version"),
        Index("ix_data_asset_versions_data_asset_id_version", "data_asset_id", "version"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    data_asset_id: Mapped[str] = mapped_column(ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    source_bindings_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    filters_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    derived_fields_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    upload_preview_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class DataAssetContractVersionRow(Base):
    __tablename__ = "data_asset_contract_versions"
    __table_args__ = (
        UniqueConstraint("data_asset_id", "version", name="uq_data_asset_contract_versions_asset_version"),
        Index("ix_data_asset_contract_versions_data_asset_id_version", "data_asset_id", "version"),
        Index("ix_data_asset_contract_versions_contract_hash", "contract_hash"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    data_asset_id: Mapped[str] = mapped_column(
        ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_where: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_what: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_data_asset_version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class DataAssetLineageSnapshotRow(Base):
    __tablename__ = "data_asset_lineage_snapshots"
    __table_args__ = (
        Index("ix_data_asset_lineage_snapshots_data_asset_id_captured_at", "data_asset_id", "captured_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    data_asset_id: Mapped[str] = mapped_column(ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    snapshot_kind: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    captured_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lineage_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    business_context_overlay_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    classification_view_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    anomaly_annotations_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

class OntologyGraphSnapshotRow(Base):
    __tablename__ = "ontology_graph_snapshots"
    __table_args__ = (
        Index("ix_ontology_graph_snapshots_graph_id_captured_at", "graph_id", "captured_at"),
        Index("ix_ontology_graph_snapshots_workspace_id_captured_at", "workspace_id", "captured_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    graph_id: Mapped[str] = mapped_column(Text, nullable=False)
    graph_name: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_product_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    captured_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    graph_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class FederatedMetadataRegistryExchangeSnapshotRow(Base):
    __tablename__ = "federated_metadata_registry_exchange_snapshots"
    __table_args__ = (
        Index("ix_federated_metadata_registry_exchange_snapshots_workspace_id_captured_at", "workspace_id", "captured_at"),
        Index("ix_federated_metadata_registry_exchange_snapshots_package_id_captured_at", "package_id", "captured_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    package_id: Mapped[str] = mapped_column(Text, nullable=False)
    package_kind: Mapped[str] = mapped_column(Text, nullable=False)
    exchange_kind: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[str] = mapped_column(Text, nullable=False)
    data_product_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    captured_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    package_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class FederatedMetadataRegistryExternalPartyRow(Base):
    __tablename__ = "federated_metadata_registry_external_parties"
    __table_args__ = (
        Index("ix_federated_metadata_registry_external_parties_workspace_id_registered_at", "workspace_id", "registered_at"),
        Index("ix_federated_metadata_registry_external_parties_tenant_id_registered_at", "tenant_id", "registered_at"),
        Index("ix_federated_metadata_registry_external_parties_approval_status_registered_at", "approval_status", "registered_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    governing_scope_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    approval_status: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approval_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registered_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FederatedMetadataRegistryAccessGrantRow(Base):
    __tablename__ = "federated_metadata_registry_access_grants"
    __table_args__ = (
        UniqueConstraint("external_party_id", "target_kind", "target_id", name="uq_federated_metadata_registry_access_grants_party_target"),
        Index("ix_federated_metadata_registry_access_grants_party_granted_at", "external_party_id", "granted_at"),
        Index("ix_federated_metadata_registry_access_grants_target_granted_at", "target_kind", "target_id", "granted_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    external_party_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    subscribed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    can_push: Mapped[bool] = mapped_column(Boolean, nullable=False)
    can_pull: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    granted_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------


class TestProofRow(Base):
    __tablename__ = "test_proofs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # DDL "ruleid" (lowercase in DDL and PostgreSQL)
    rule_id: Mapped[str] = mapped_column("ruleid", Text, nullable=False)
    test_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    coverage: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    records_tested_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    failures_found: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    success_rate: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    test_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    workspace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tested_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    diagnostics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class BatchTestRequestRow(Base):
    __tablename__ = "batch_test_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # DDL "ruleid" (matches PostgreSQL lowercase storage)
    rule_id: Mapped[str] = mapped_column(
        "ruleid", ForeignKey("rules.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    test_data_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(
        Text, server_default="pending", nullable=True
    )
    workspace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    proof_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("test_proofs.id", ondelete="SET NULL"), nullable=True
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class AppConfigRow(Base):
    __tablename__ = "app_config"

    config_key: Mapped[str] = mapped_column(Text, primary_key=True)
    config_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# Simple sessions table for server-side idle session enforcement
class AppSessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_activity: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    id_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SystemInfoRow(Base):
    __tablename__ = "system_info"

    info_key: Mapped[str] = mapped_column(Text, primary_key=True)
    info_value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Profiling  (02_profiling_schema.sql)
# ---------------------------------------------------------------------------


class DataSourceMetadataRow(Base):
    __tablename__ = "data_source_metadata"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    data_source_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    connection_string: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    column_definitions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    record_count: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    statistics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    quality_metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    last_profiled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    profiled_by_user_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profiling_method: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class DataSourceProfilingRequestRow(Base):
    __tablename__ = "data_source_profiling_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    data_source_id: Mapped[str] = mapped_column(
        ForeignKey("data_source_metadata.data_source_id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(
        Text, server_default="pending", nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_metadata_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SuggestionRow(Base):
    __tablename__ = "suggestions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    data_source_id: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_rule: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence_score: Mapped[Optional[float]] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_from_profiling_request_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("data_source_profiling_requests.id", ondelete="CASCADE"),
        nullable=True,
    )
    status: Mapped[Optional[str]] = mapped_column(
        Text, server_default="pending", nullable=True
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SuggestionInteractionRow(Base):
    __tablename__ = "suggestion_interactions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    suggestion_id: Mapped[str] = mapped_column(
        ForeignKey("suggestions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    # ID of a rule that was created as a result of accepting this suggestion
    rule_created_from_suggestion_id: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SuggestionPreviewInteractionRow(Base):
    __tablename__ = "suggestion_preview_interactions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class NaturalLanguageAnalysisRequestRow(Base):
    __tablename__ = "natural_language_analysis_requests"

    request_id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    current_workspace_id: Mapped[str] = mapped_column(Text, nullable=False)
    search_scope: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_provider: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_type: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    selected_attribute_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    accessible_workspace_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(Text, server_default="pending", nullable=True)
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggestion_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class NaturalLanguageAnalysisRequestHistoryRow(Base):
    __tablename__ = "natural_language_analysis_request_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["request_id"],
            ["natural_language_analysis_requests.request_id"],
            ondelete="CASCADE",
        ),
        Index("ix_natural_language_analysis_request_history_request", "request_id", "changed_at"),
        Index("ix_natural_language_analysis_request_history_changed_at", "changed_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    details_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


# ---------------------------------------------------------------------------
# Monitor schedules  (DQ-12.AC-01)
# ---------------------------------------------------------------------------


class MonitorScheduleRow(Base):
    """User-defined schedule for a monitor scoped to a data asset or source dataset."""

    __tablename__ = "monitor_schedules"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    scope_kind: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[str] = mapped_column(Text, nullable=False)
    monitor_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="scheduled_monitor")
    cron_expression: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1440")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    signals: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("scope_kind", "scope_id", name="uq_monitor_schedules_scope"),
        Index("ix_monitor_schedules_scope", "scope_kind", "scope_id"),
        Index("ix_monitor_schedules_workspace", "workspace_id"),
    )


class SlaSloDefinitionRow(Base):
    __tablename__ = "sla_slo_definitions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_kind: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str] = mapped_column(Text, nullable=False)
    metric_kind: Mapped[str] = mapped_column(Text, nullable=False)
    threshold_value: Mapped[Any] = mapped_column(Numeric(12, 4), nullable=False)
    threshold_operator: Mapped[str] = mapped_column(Text, nullable=False, server_default="gte")
    lookback_amount: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    lookback_unit: Mapped[str] = mapped_column(Text, nullable=False, server_default="day")
    lifecycle_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    approval_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    requested_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    itsm_system: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    itsm_ticket_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    itsm_ticket_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    itsm_ticket_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_sla_slo_definitions_workspace", "workspace_id"),
        Index("ix_sla_slo_definitions_scope", "scope_kind", "scope_id"),
        Index("ix_sla_slo_definitions_metric", "metric_kind"),
        Index("ix_sla_slo_definitions_status", "lifecycle_status", "approval_status"),
    )


# ---------------------------------------------------------------------------
# Incidents  (DQ-13)
# ---------------------------------------------------------------------------


class IncidentRow(Base):
    """An incident record tracking either a technical run error or a functional data violation."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    incident_kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_plan_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_kind: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_correlation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_parent_correlation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_request_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_queue_message_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_trace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_system: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    violated_rule_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    violation_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    itsm_ticket_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    itsm_ticket_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    comments: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    resolution_history: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_incidents_kind", "incident_kind"),
        Index("ix_incidents_status", "status"),
        Index("ix_incidents_workspace", "workspace_id"),
        Index("ix_incidents_run_id", "run_id"),
        Index("ix_incidents_scope", "scope_kind", "scope_id"),
        Index("ix_incidents_source_correlation", "source_correlation_id"),
        Index("ix_incidents_source_parent_correlation", "source_parent_correlation_id"),
    )


class IncidentRootCauseSuggestionRow(Base):
    __tablename__ = "incident_root_cause_suggestions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    incident_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    incident_count: Mapped[int] = mapped_column(Integer, nullable=False)
    suggested_root_cause: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(Text, server_default="pending", nullable=True)
    events_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    assistance_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    assistance_request_reference_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assistance_request_ticket_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assistance_request_ticket_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assistance_request_ticket_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assistance_request_ticket_system: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assistance_request_delivery_modes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    assistance_request_payload_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_incident_root_cause_suggestions_workspace", "workspace_id"),
        Index("ix_incident_root_cause_suggestions_status", "status"),
        Index("ix_incident_root_cause_suggestions_created_at", "created_at"),
    )




class ValidationRunRow(Base):
    """Top-level record for a batch validation run (DQ-1.4)."""

    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    valid_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    invalid_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(
        Text, server_default="complete", nullable=True
    )


class ValidationRunItemRow(Base):
    """Per-rule result within a validation run (DQ-1.4)."""

    __tablename__ = "validation_run_items"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    valid: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    errors: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    warnings: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    diagnostics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    conflicts: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
