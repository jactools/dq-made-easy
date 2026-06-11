"""Service for guided rule generation (onboarding) feature."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from app.domain.entities.onboarding_models import (
    BatchRuleOutcome,
    CreateBatchRequest,
    CreateBatchResponse,
    GenerateProposalsRequest,
    GenerateProposalsResponse,
    ProposedAttribute,
    ProposedObjectGroup,
    ProposedTemplateGroup,
    ScopeSummaryRequest,
    ScopeSummaryResponse,
)
from app.domain.interfaces import DataAssetRepository, DataCatalogRepository, RulesRepository
from app.domain.onboarding_matching import DAMA_TEMPLATES_REGISTRY, TemplateMatch, match_templates_to_attribute

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ResolvedProposal:
    proposal_id: str
    template: TemplateMatch
    data_object_version_id: str
    attribute_id: str
    attribute_name: str
    data_type: str
    is_required: bool


class OnboardingService:
    """Service for guided rule generation."""

    def __init__(
        self,
        *,
        data_asset_repository: DataAssetRepository,
        data_catalog_repository: DataCatalogRepository,
        rules_repository: RulesRepository,
    ):
        self._data_asset_repository = data_asset_repository
        self._data_catalog_repository = data_catalog_repository
        self._rules_repository = rules_repository

    async def generate_proposals(
        self,
        *,
        request: GenerateProposalsRequest,
    ) -> GenerateProposalsResponse:
        """Generate rule proposals for a given scope.
        
        Args:
            request: Scope selection and workspace context
            
        Returns:
            Grouped proposal tree with counts at each level
            
        Raises:
            HTTPException(400) if scope does not exist
            HTTPException(503) if metadata or rules service unavailable
        """
        # Fetch attributes in scope
        attributes_by_object = await self._fetch_attributes_for_scope(
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            workspace_id=request.workspace_id,
        )

        # Fetch existing rules for deduplication
        existing_rules = await self._rules_repository.list_rule_records(
            workspace=request.workspace_id,
            limit=10000,  # Large limit to get all rules
        )
        existing_checks = self._index_existing_rules(existing_rules)

        # Build proposals
        proposals_by_template: dict[str, ProposedTemplateGroup] = {}
        total_attributes = 0
        total_proposals = 0

        for data_object_version_id, obj_meta in attributes_by_object.items():
            for attribute in obj_meta["attributes"]:
                total_attributes += 1
                
                # Match templates for this attribute
                matches = match_templates_to_attribute(
                    attribute_name=attribute["name"],
                    data_type=attribute.get("data_type", "unknown"),
                    is_required=attribute.get("is_required", False),
                )

                for match in matches:
                    # Check if already covered
                    already_covered = (
                        (
                            data_object_version_id,
                            attribute["id"],
                            match.check_type,
                        )
                        in existing_checks
                    )

                    # Add to proposal group
                    if match.template_id not in proposals_by_template:
                        proposals_by_template[match.template_id] = ProposedTemplateGroup(
                            template_id=match.template_id,
                            template_name=match.template_name,
                            dimension=match.dimension,
                            check_type=match.check_type,
                            total_count=0,
                            by_dataset={},
                        )

                    template_group = proposals_by_template[match.template_id]
                    dataset_id = obj_meta["dataset_id"]

                    if dataset_id not in template_group.by_dataset:
                        template_group.by_dataset[dataset_id] = []

                    # Check if object already in this dataset's list
                    obj_group = next(
                        (
                            og
                            for og in template_group.by_dataset[dataset_id]
                            if og.data_object_version_id == data_object_version_id
                        ),
                        None,
                    )

                    if obj_group is None:
                        obj_group = ProposedObjectGroup(
                            data_object_version_id=data_object_version_id,
                            object_name=obj_meta["object_name"],
                            dataset_name=obj_meta["dataset_name"],
                            dataset_id=dataset_id,
                            count=0,
                            attributes=[],
                        )
                        template_group.by_dataset[dataset_id].append(obj_group)

                    # Add attribute to object group
                    proposed_attr = ProposedAttribute(
                        attribute_id=attribute["id"],
                        name=attribute["name"],
                        data_type=attribute.get("data_type", "unknown"),
                        already_covered=already_covered,
                    )
                    obj_group.attributes.append(proposed_attr)
                    obj_group.count += 1
                    template_group.total_count += 1
                    total_proposals += 1

        return GenerateProposalsResponse(
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            total_attributes=total_attributes,
            total_proposals=total_proposals,
            proposals=list(proposals_by_template.values()),
            generated_at=datetime.now(UTC),
        )

    async def summarize_scope(
        self,
        *,
        request: ScopeSummaryRequest,
    ) -> ScopeSummaryResponse:
        """Return object/attribute counts for the selected scope."""
        attributes_by_object = await self._fetch_attributes_for_scope(
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            workspace_id=request.workspace_id,
        )

        object_count = len(attributes_by_object)
        attribute_count = sum(
            len(meta.get("attributes", []))
            for meta in attributes_by_object.values()
        )

        return ScopeSummaryResponse(
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            workspace_id=request.workspace_id,
            object_count=object_count,
            attribute_count=attribute_count,
            generated_at=datetime.now(UTC),
        )

    async def create_rule_batch(
        self,
        *,
        request: CreateBatchRequest,
        actor_id: str,
    ) -> CreateBatchResponse:
        """Create draft rules for selected onboarding proposals.

        The batch continues on per-proposal failures and returns a complete
        outcome summary.
        """
        if not request.accepted_proposal_ids:
            raise ValueError("accepted_proposal_ids must contain at least one proposal id")

        normalized_ids = [str(value or "").strip() for value in request.accepted_proposal_ids]
        if any(not proposal_id for proposal_id in normalized_ids):
            raise ValueError("accepted_proposal_ids must not contain empty values")
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("accepted_proposal_ids must not contain duplicates")

        resolved_proposals = self._resolve_batch_proposals(
            workspace_id=request.workspace_id,
            proposal_ids=normalized_ids,
        )
        existing_rules = await self._rules_repository.list_rule_records(
            workspace=request.workspace_id,
            limit=10000,
        )
        rule_ids_by_attribute = self._index_rule_ids_by_attribute()

        batch_id = f"onb-{uuid4().hex}"
        outcomes: list[BatchRuleOutcome] = []

        for proposal in resolved_proposals:
            if self._has_equivalent_active_rule(
                attribute_id=proposal.attribute_id,
                check_type=proposal.template.check_type,
                existing_rules=existing_rules,
                rule_ids_by_attribute=rule_ids_by_attribute,
            ):
                outcomes.append(
                    BatchRuleOutcome(
                        proposal_id=proposal.proposal_id,
                        status="skipped",
                        reason="attribute already has equivalent rule",
                    )
                )
                continue

            check_type_params = self._build_check_type_params(proposal=proposal)
            dsl = {
                "schemaVersion": "1.0.0",
                "source": {
                    "kind": "check_type",
                    "checkType": proposal.template.check_type,
                    "checkTypeParams": check_type_params,
                    "joinConditions": [],
                    "aliasMappings": {},
                    "reusableFilterIds": [],
                    "reusableJoinId": None,
                },
            }
            taxonomy = {
                "type": proposal.template.check_type,
                "domain": request.workspace_id,
                "owner": actor_id,
                "data_steward": actor_id,
                "sla_scope": "dataset",
                "onboarding_batch_id": batch_id,
                "onboarding_proposal_id": proposal.proposal_id,
            }

            try:
                created = await self._rules_repository.create_rule_record(
                    name=self._build_rule_name(proposal=proposal, batch_id=batch_id),
                    description=(
                        f"Onboarding generated draft for {proposal.attribute_name} "
                        f"({proposal.template.template_name})"
                    ),
                    comments=f"Generated by onboarding batch {batch_id}",
                    expression="1 = 1",
                    dimension=proposal.template.dimension,
                    active=False,
                    workspace=request.workspace_id,
                    created_by=actor_id,
                    generated=True,
                    is_template=False,
                    template_id=proposal.template.template_id,
                    suggestion_id=proposal.proposal_id,
                    dsl=dsl,
                    join_conditions=[],
                    alias_mappings={},
                    reusable_join_id=None,
                    reusable_filter_ids=[],
                    manual_override_by=None,
                    manual_override_at=None,
                    check_type=proposal.template.check_type,
                    check_type_params=check_type_params,
                    taxonomy=taxonomy,
                )
                self._data_catalog_repository.add_rule_attributes(
                    [
                        {
                            "ruleId": created.id,
                            "attributeId": proposal.attribute_id,
                        }
                    ]
                )
            except Exception as exc:
                _log.exception(
                    "Failed to create onboarding draft rule",
                    extra={
                        "batch_id": batch_id,
                        "proposal_id": proposal.proposal_id,
                        "workspace_id": request.workspace_id,
                    },
                )
                outcomes.append(
                    BatchRuleOutcome(
                        proposal_id=proposal.proposal_id,
                        status="failed",
                        reason=str(exc),
                    )
                )
                continue

            outcomes.append(
                BatchRuleOutcome(
                    proposal_id=proposal.proposal_id,
                    status="created",
                    rule_id=created.id,
                )
            )
            rule_ids_by_attribute.setdefault(proposal.attribute_id, set()).add(created.id)
            existing_rules.append(
                SimpleNamespace(
                    id=created.id,
                    active=True,
                    deleted_on=None,
                    check_type=proposal.template.check_type,
                )
            )

        created_count = sum(1 for outcome in outcomes if outcome.status == "created")
        skipped_count = sum(1 for outcome in outcomes if outcome.status == "skipped")
        failed_count = sum(1 for outcome in outcomes if outcome.status == "failed")

        return CreateBatchResponse(
            batch_id=batch_id,
            workspace_id=request.workspace_id,
            total_accepted=len(resolved_proposals),
            created=created_count,
            skipped=skipped_count,
            failed=failed_count,
            outcomes=outcomes,
            created_at=datetime.now(UTC),
        )

    async def _fetch_attributes_for_scope(
        self,
        *,
        scope_type: str,
        scope_id: str,
        workspace_id: str,
    ) -> dict[str, dict[str, Any]]:
        """Fetch attributes from metadata catalog for the given scope.
        
        Returns a dict keyed by data_object_version_id with structure:
        {
            "object_name": "...",
            "dataset_id": "...",
            "dataset_name": "...",
            "attributes": [
                {"id": "...", "name": "...", "data_type": "...", "is_required": bool},
                ...
            ]
        }
        """
        normalized_scope_type = str(scope_type or "").strip()
        if normalized_scope_type not in {"workspace", "product", "dataset", "object"}:
            raise ValueError(f"Unknown scope_type: {scope_type}")

        # Data Catalog is the canonical onboarding source. Use Data Assets only as fallback.
        attributes_by_object = self._fetch_attributes_for_scope_from_catalog(
            scope_type=normalized_scope_type,
            scope_id=scope_id,
            workspace_id=workspace_id,
        )
        if attributes_by_object:
            return attributes_by_object

        attributes_by_object = self._fetch_attributes_for_scope_from_assets(
            scope_type=normalized_scope_type,
            scope_id=scope_id,
            workspace_id=workspace_id,
        )
        if normalized_scope_type != "workspace" and not attributes_by_object:
            raise ValueError(f"Scope not found or has no assets: {scope_type} '{scope_id}'")

        return attributes_by_object

    def _fetch_attributes_for_scope_from_assets(
        self,
        *,
        scope_type: str,
        scope_id: str,
        workspace_id: str,
    ) -> dict[str, dict[str, Any]]:
        attributes_by_object: dict[str, dict[str, Any]] = {}

        assets = self._data_asset_repository.list_data_assets(workspace_id=workspace_id)
        if scope_type == "product":
            assets = [asset for asset in assets if self._belongs_to_product(asset, scope_id)]
        elif scope_type == "dataset":
            assets = [asset for asset in assets if self._belongs_to_dataset(asset, scope_id)]
        elif scope_type == "object":
            assets = [asset for asset in assets if self._matches_object_scope(asset, scope_id)]

        for asset in assets:
            asset_id = getattr(asset, "id", None) or getattr(asset, "asset_id", None)
            asset_name = getattr(asset, "name", "unknown")
            asset_version_id = getattr(asset, "version_id", None) or asset_id
            attributes = self._extract_attributes_from_asset(asset)
            if not attributes:
                continue
            attributes_by_object[asset_version_id] = {
                "object_name": asset_name,
                "dataset_id": getattr(asset, "dataset_id", "unknown"),
                "dataset_name": getattr(asset, "dataset_name", "unknown"),
                "attributes": attributes,
            }

        return attributes_by_object

    def _fetch_attributes_for_scope_from_catalog(
        self,
        *,
        scope_type: str,
        scope_id: str,
        workspace_id: str,
    ) -> dict[str, dict[str, Any]]:
        datasets = self._data_catalog_repository.list_data_sets()
        dataset_by_id = {
            str(getattr(dataset, "id", "") or "").strip(): dataset
            for dataset in datasets
            if str(getattr(dataset, "id", "") or "").strip()
        }

        objects = self._data_catalog_repository.list_data_objects_catalog()
        object_by_id = {
            str(getattr(obj, "id", "") or "").strip(): obj
            for obj in objects
            if str(getattr(obj, "id", "") or "").strip()
        }

        versions = self._data_catalog_repository.list_data_object_versions()
        all_attributes = self._data_catalog_repository.list_attributes_catalog()

        selected_versions: list[Any] = []
        normalized_scope_id = str(scope_id or "").strip()
        normalized_workspace_id = str(workspace_id or "").strip()

        for version in versions:
            version_id = str(getattr(version, "id", "") or "").strip()
            object_id = str(getattr(version, "data_object_id", "") or "").strip()
            obj = object_by_id.get(object_id)
            dataset_id = str(getattr(obj, "dataset_id", "") or "").strip()
            dataset = dataset_by_id.get(dataset_id)
            product_id = str(getattr(dataset, "product_id", "") or "").strip() if dataset else ""
            dataset_workspace_id = str(getattr(dataset, "workspace_id", "") or "").strip() if dataset else ""

            if normalized_workspace_id and dataset_workspace_id != normalized_workspace_id:
                continue

            include = False
            if scope_type == "workspace":
                include = bool(dataset_workspace_id)
            elif scope_type == "product":
                include = bool(normalized_scope_id) and product_id == normalized_scope_id
            elif scope_type == "dataset":
                include = bool(normalized_scope_id) and dataset_id == normalized_scope_id
            elif scope_type == "object":
                include = bool(normalized_scope_id) and (
                    version_id == normalized_scope_id or object_id == normalized_scope_id
                )

            if include:
                selected_versions.append(version)

        attributes_by_version: dict[str, list[dict[str, Any]]] = {}
        for attribute in all_attributes:
            version_id = str(getattr(attribute, "version_id", "") or "").strip()
            if not version_id:
                continue
            attributes_by_version.setdefault(version_id, []).append(
                {
                    "id": str(getattr(attribute, "id", "") or "").strip(),
                    "name": str(getattr(attribute, "name", "") or "").strip(),
                    "data_type": str(getattr(attribute, "type", "unknown") or "unknown").strip(),
                    "is_required": not bool(getattr(attribute, "nullable", True)),
                }
            )

        attributes_by_object: dict[str, dict[str, Any]] = {}
        for version in selected_versions:
            version_id = str(getattr(version, "id", "") or "").strip()
            object_id = str(getattr(version, "data_object_id", "") or "").strip()
            obj = object_by_id.get(object_id)
            dataset_id = str(getattr(obj, "dataset_id", "") or "").strip() if obj else ""
            dataset = dataset_by_id.get(dataset_id)
            dataset_name = str(getattr(dataset, "name", "unknown") or "unknown")
            object_name = str(getattr(obj, "name", "unknown") or "unknown")
            attributes = [entry for entry in attributes_by_version.get(version_id, []) if entry.get("id") and entry.get("name")]

            if not attributes:
                continue

            attributes_by_object[version_id] = {
                "object_name": object_name,
                "dataset_id": dataset_id or "unknown",
                "dataset_name": dataset_name,
                "attributes": attributes,
            }

        return attributes_by_object

    def _extract_attributes_from_asset(self, asset: Any) -> list[dict[str, Any]]:
        """Extract attributes from a data asset.
        
        This traverses the asset's contract or schema to get attributes.
        """
        attributes = []

        # Try contract_schema first
        contract = getattr(asset, "contract_schema", None)
        if contract and isinstance(contract, dict):
            columns = contract.get("columns", [])
            for col in columns:
                attributes.append(
                    {
                        "id": col.get("id", col.get("name", "")),
                        "name": col.get("name", ""),
                        "data_type": col.get("data_type", col.get("type", "unknown")),
                        "is_required": col.get("required", False)
                        or col.get("is_required", False),
                    }
                )
        
        # Fallback: try attributes field
        if not attributes:
            asset_attrs = getattr(asset, "attributes", [])
            if isinstance(asset_attrs, list):
                for attr in asset_attrs:
                    if isinstance(attr, dict):
                        attributes.append(
                            {
                                "id": attr.get("id", attr.get("name", "")),
                                "name": attr.get("name", ""),
                                "data_type": attr.get("data_type", "unknown"),
                                "is_required": attr.get("required", False),
                            }
                        )

        return attributes

    @staticmethod
    def _belongs_to_product(asset: Any, product_id: str) -> bool:
        """Check if an asset belongs to the given product."""
        business_context = getattr(asset, "business_context", None)
        context_product_id = str(getattr(business_context, "data_product_id", "") or "").strip()
        direct_product_id = str(getattr(asset, "product_id", "") or "").strip()
        expected_product_id = str(product_id or "").strip()
        return bool(expected_product_id) and (context_product_id == expected_product_id or direct_product_id == expected_product_id)

    @staticmethod
    def _belongs_to_dataset(asset: Any, dataset_id: str) -> bool:
        """Check if an asset belongs to the given dataset."""
        business_context = getattr(asset, "business_context", None)
        context_dataset_id = str(getattr(business_context, "dataset_id", "") or "").strip()
        direct_dataset_id = str(getattr(asset, "dataset_id", "") or "").strip()
        expected_dataset_id = str(dataset_id or "").strip()
        return bool(expected_dataset_id) and (context_dataset_id == expected_dataset_id or direct_dataset_id == expected_dataset_id)

    @staticmethod
    def _matches_object_scope(asset: Any, scope_id: str) -> bool:
        expected_scope_id = str(scope_id or "").strip()
        if not expected_scope_id:
            return False

        candidates = {
            str(getattr(asset, "id", "") or "").strip(),
            str(getattr(asset, "current_version_id", "") or "").strip(),
            str(getattr(asset, "version_id", "") or "").strip(),
        }
        candidates.discard("")
        return expected_scope_id in candidates

    @staticmethod
    def _index_existing_rules(
        existing_rules: list[Any],
    ) -> set[tuple[str, str, str]]:
        """Index existing rules by (data_object_version_id, attribute_id, check_type).
        
        Returns a set of tuples for O(1) lookup during deduplication.
        """
        indexed = set()
        for rule in existing_rules:
            # Skip deleted rules
            if getattr(rule, "deleted_on", None):
                continue
            
            # Skip inactive rules (we want to match active rules only)
            if not getattr(rule, "active", True):
                continue
            
            # Get check type
            check_type = getattr(rule, "check_type", None)
            if not check_type:
                continue

            # Get associated data object version ID and attributes
            # This depends on how rules store their data object associations
            # For now, assume rule has attributes or check_type_params with attribute info
            rule_attributes = getattr(rule, "attributes", [])
            
            # Simplified: if rule has attributes, index it
            if rule_attributes:
                for attr_ref in rule_attributes:
                    attr_id = attr_ref.get("id") if isinstance(attr_ref, dict) else getattr(attr_ref, "id", None)
                    if attr_id:
                        # We approximate data_object_version_id; ideally rules store this explicitly
                        obj_version_id = getattr(rule, "data_object_version_id", "")
                        indexed.add((obj_version_id, attr_id, check_type))

        return indexed

    @staticmethod
    def _parse_proposal_id(proposal_id: str) -> tuple[str, str, str] | None:
        parts = proposal_id.split("::")
        if len(parts) != 3:
            return None
        template_id, data_object_version_id, attribute_id = (part.strip() for part in parts)
        if not template_id or not data_object_version_id or not attribute_id:
            return None
        return template_id, data_object_version_id, attribute_id

    def _resolve_batch_proposals(
        self,
        *,
        workspace_id: str,
        proposal_ids: list[str],
    ) -> list[_ResolvedProposal]:
        template_by_id = {
            template.template_id: template
            for template in DAMA_TEMPLATES_REGISTRY
        }
        attributes = self._data_catalog_repository.list_attributes_catalog()
        attribute_by_key: dict[tuple[str, str], Any] = {}
        for attribute in attributes:
            attribute_workspace = str(getattr(attribute, "workspace_id", "") or "").strip()
            if attribute_workspace and attribute_workspace != workspace_id:
                continue
            version_id = str(getattr(attribute, "version_id", "") or "").strip()
            attribute_id = str(getattr(attribute, "id", "") or "").strip()
            if not version_id or not attribute_id:
                continue
            attribute_by_key[(version_id, attribute_id)] = attribute

        resolved: list[_ResolvedProposal] = []
        invalid: list[str] = []
        for proposal_id in proposal_ids:
            parsed = self._parse_proposal_id(proposal_id)
            if parsed is None:
                invalid.append(proposal_id)
                continue

            template_id, data_object_version_id, attribute_id = parsed
            template = template_by_id.get(template_id)
            if template is None:
                invalid.append(proposal_id)
                continue

            attribute = attribute_by_key.get((data_object_version_id, attribute_id))
            if attribute is None:
                invalid.append(proposal_id)
                continue

            attribute_name = str(getattr(attribute, "name", "") or "").strip()
            data_type = str(getattr(attribute, "type", "") or "unknown").strip() or "unknown"
            is_required = not bool(getattr(attribute, "nullable", True))
            template_matches = {
                match.template_id
                for match in match_templates_to_attribute(
                    attribute_name=attribute_name,
                    data_type=data_type,
                    is_required=is_required,
                )
            }
            if template.template_id not in template_matches:
                invalid.append(proposal_id)
                continue

            resolved.append(
                _ResolvedProposal(
                    proposal_id=proposal_id,
                    template=template,
                    data_object_version_id=data_object_version_id,
                    attribute_id=attribute_id,
                    attribute_name=attribute_name,
                    data_type=data_type,
                    is_required=is_required,
                )
            )

        if invalid:
            raise ValueError(f"Invalid proposal ids: {', '.join(sorted(set(invalid)))}")
        return resolved

    def _index_rule_ids_by_attribute(self) -> dict[str, set[str]]:
        mapping: dict[str, set[str]] = {}
        for row in self._data_catalog_repository.list_rule_attributes():
            rule_id = str(getattr(row, "ruleId", "") or "").strip()
            attribute_id = str(getattr(row, "attributeId", "") or "").strip()
            if not rule_id or not attribute_id:
                continue
            mapping.setdefault(attribute_id, set()).add(rule_id)
        return mapping

    @staticmethod
    def _has_equivalent_active_rule(
        *,
        attribute_id: str,
        check_type: str,
        existing_rules: list[Any],
        rule_ids_by_attribute: dict[str, set[str]],
    ) -> bool:
        candidate_rule_ids = rule_ids_by_attribute.get(attribute_id, set())
        if not candidate_rule_ids:
            return False
        normalized_check_type = str(check_type or "").strip().upper()
        for rule in existing_rules:
            rule_id = str(getattr(rule, "id", "") or "").strip()
            if rule_id not in candidate_rule_ids:
                continue
            if getattr(rule, "deleted_on", None):
                continue
            if not bool(getattr(rule, "active", True)):
                continue
            if str(getattr(rule, "check_type", "") or "").strip().upper() != normalized_check_type:
                continue
            return True
        return False

    @staticmethod
    def _build_rule_name(*, proposal: _ResolvedProposal, batch_id: str) -> str:
        return f"{proposal.template.template_name} [{proposal.attribute_name}] ({batch_id[:8]})"

    @staticmethod
    def _build_check_type_params(*, proposal: _ResolvedProposal) -> dict[str, Any]:
        check_type = proposal.template.check_type
        attribute_name = proposal.attribute_name

        if check_type == "THRESHOLD":
            metric = "null_pct"
            params: dict[str, Any] = {
                "attribute": attribute_name,
                "metric": metric,
                "operator": "lte",
                "threshold": 0.0,
            }
            if proposal.template.template_id == "template-completeness-2":
                params["metric"] = "empty_pct"
                params["threshold"] = 0.0
            if proposal.template.template_id == "template-completeness-3":
                params["metric"] = "default_val_pct"
                params["threshold"] = 0.0
                params["expectedValue"] = "N/A"
            return params

        if check_type == "REGEX":
            pattern = r".+"
            if proposal.template.template_id == "template-accuracy-2":
                pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
            elif proposal.template.template_id == "template-accuracy-3":
                pattern = r"^[+0-9()\-\s]{7,20}$"
            return {
                "attribute": attribute_name,
                "pattern": pattern,
                "requirePresent": False,
            }

        if check_type == "ALLOWLIST":
            return {
                "attribute": attribute_name,
                "allowedValues": ["valid"],
                "caseSensitive": False,
            }

        if check_type == "REFERENTIAL_INTEGRITY":
            return {
                "attribute": attribute_name,
                "refDataObjectId": proposal.data_object_version_id,
                "refDataObjectVersionId": proposal.data_object_version_id,
                "refAttribute": attribute_name,
            }

        if check_type == "FRESHNESS":
            return {
                "attribute": attribute_name,
                "maxDaysOld": 1,
                "anchor": "now",
            }

        if check_type == "LAG":
            return {
                "startAttribute": attribute_name,
                "endAttribute": attribute_name,
                "maxHours": 24,
            }

        if check_type == "FUTURE_DATE":
            return {
                "attribute": attribute_name,
            }

        if check_type == "RANGE":
            return {
                "attribute": attribute_name,
                "minValue": 0,
                "inclusive": True,
            }

        if check_type == "UNIQUENESS":
            return {
                "attributes": [attribute_name],
            }

        return {}
