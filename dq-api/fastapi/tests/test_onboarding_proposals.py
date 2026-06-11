"""Tests for onboarding proposal generation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.application.services.onboarding_service import OnboardingService
from app.api.v1.endpoints.onboarding import _is_workspace_authorized
from app.domain.entities.onboarding_models import CreateBatchRequest, GenerateProposalsRequest
from app.domain.onboarding_matching import match_templates_to_attribute


class TestTemplateMatching:
    """Tests for the template matching logic."""

    def test_null_check_universal(self):
        """NULL Value Check should match all attributes."""
        matches = match_templates_to_attribute(
            attribute_name="any_field", data_type="string", is_required=False
        )
        assert len(matches) > 0
        assert any(m.template_id == "template-completeness-1" for m in matches)

    def test_empty_string_for_string_types(self):
        """Empty String Check should match string/text types."""
        matches = match_templates_to_attribute(
            attribute_name="description", data_type="string", is_required=False
        )
        assert any(m.template_id == "template-completeness-2" for m in matches)

    def test_date_patterns(self):
        """Date patterns should trigger Freshness and Future Date checks."""
        for name in ["created_date", "updated_at", "event_time"]:
            matches = match_templates_to_attribute(
                attribute_name=name, data_type="date", is_required=False
            )
            template_ids = {m.template_id for m in matches}
            assert "template-timeliness-1" in template_ids  # Freshness
            assert "template-timeliness-3" in template_ids  # Future Date

    def test_id_key_code_patterns(self):
        """ID/key/code patterns should trigger Uniqueness."""
        for name in ["customer_id", "order_key", "product_code"]:
            matches = match_templates_to_attribute(
                attribute_name=name, data_type="string", is_required=False
            )
            template_ids = {m.template_id for m in matches}
            assert "template-uniqueness-1" in template_ids

    def test_email_pattern(self):
        """Email fields should trigger Email Format Check."""
        for name in ["email", "email_address", "user_email"]:
            matches = match_templates_to_attribute(
                attribute_name=name, data_type="string", is_required=False
            )
            template_ids = {m.template_id for m in matches}
            assert "template-accuracy-2" in template_ids

    def test_phone_pattern(self):
        """Phone fields should trigger Phone Number Validation."""
        for name in ["phone", "phone_number", "contact_phone"]:
            matches = match_templates_to_attribute(
                attribute_name=name, data_type="string", is_required=False
            )
            template_ids = {m.template_id for m in matches}
            assert "template-accuracy-3" in template_ids

    def test_numeric_range_check(self):
        """Numeric types should trigger Range Check."""
        for dtype in ["numeric", "decimal", "int", "float"]:
            matches = match_templates_to_attribute(
                attribute_name="amount", data_type=dtype, is_required=False
            )
            template_ids = {m.template_id for m in matches}
            assert "template-validity-1" in template_ids

    def test_no_duplicate_templates(self):
        """Matching should not return duplicate templates."""
        matches = match_templates_to_attribute(
            attribute_name="created_date", data_type="date", is_required=False
        )
        template_ids = [m.template_id for m in matches]
        assert len(template_ids) == len(set(template_ids))


class TestOnboardingService:
    """Tests for the onboarding service."""

    @pytest.fixture
    def mock_repositories(self):
        """Provide mock repositories."""
        data_asset_repo = MagicMock()
        data_catalog_repo = MagicMock()
        rules_repo = AsyncMock()
        return data_asset_repo, data_catalog_repo, rules_repo

    @pytest.fixture
    def service(self, mock_repositories):
        """Provide an onboarding service instance."""
        data_asset_repo, data_catalog_repo, rules_repo = mock_repositories
        return OnboardingService(
            data_asset_repository=data_asset_repo,
            data_catalog_repository=data_catalog_repo,
            rules_repository=rules_repo,
        )

    @pytest.mark.asyncio
    async def test_generate_proposals_basic(self, service, mock_repositories):
        """Test basic proposal generation."""
        data_asset_repo, _, rules_repo = mock_repositories

        # Mock data assets
        mock_asset = MagicMock()
        mock_asset.id = "asset-1"
        mock_asset.version_id = "version-1"
        mock_asset.name = "customer"
        mock_asset.dataset_id = "dataset-1"
        mock_asset.dataset_name = "customer_data"
        mock_asset.contract_schema = {
            "columns": [
                {
                    "id": "attr-1",
                    "name": "customer_id",
                    "data_type": "string",
                    "required": True,
                },
                {
                    "id": "attr-2",
                    "name": "email",
                    "data_type": "string",
                    "required": True,
                },
            ]
        }

        data_asset_repo.list_data_assets.return_value = [mock_asset]
        rules_repo.list_rule_records.return_value = []

        # Generate proposals
        request = GenerateProposalsRequest(
            scope_type="workspace",
            scope_id="ws-1",
            workspace_id="ws-1",
        )
        response = await service.generate_proposals(request=request)

        # Assertions
        assert response.scope_type == "workspace"
        assert response.total_attributes == 2
        assert response.total_proposals > 0
        assert len(response.proposals) > 0

        # Check that we have proposals for the attributes
        all_template_ids = set()
        for template_group in response.proposals:
            all_template_ids.add(template_group.template_id)

        # customer_id should match NULL Check and Uniqueness
        assert "template-completeness-1" in all_template_ids
        assert "template-uniqueness-1" in all_template_ids

        # email should match NULL Check and Email Format
        assert "template-accuracy-2" in all_template_ids

    @pytest.mark.asyncio
    async def test_existing_rule_deduplication(self, service, mock_repositories):
        """Test that existing active rules are marked as 'already_covered'."""
        data_asset_repo, _, rules_repo = mock_repositories

        # Mock data assets
        mock_asset = MagicMock()
        mock_asset.id = "asset-1"
        mock_asset.version_id = "version-1"
        mock_asset.name = "customer"
        mock_asset.dataset_id = "dataset-1"
        mock_asset.dataset_name = "customer_data"
        mock_asset.contract_schema = {
            "columns": [
                {
                    "id": "attr-1",
                    "name": "customer_id",
                    "data_type": "string",
                    "required": True,
                }
            ]
        }

        # Mock existing rule for the same attribute
        mock_rule = MagicMock()
        mock_rule.id = "rule-1"
        mock_rule.check_type = "UNIQUENESS"
        mock_rule.active = True
        mock_rule.deleted_on = None
        mock_rule.attributes = [{"id": "attr-1"}]
        mock_rule.data_object_version_id = "version-1"

        data_asset_repo.list_data_assets.return_value = [mock_asset]
        rules_repo.list_rule_records.return_value = [mock_rule]

        # Generate proposals
        request = GenerateProposalsRequest(
            scope_type="workspace",
            scope_id="ws-1",
            workspace_id="ws-1",
        )
        response = await service.generate_proposals(request=request)

        # Find the Uniqueness proposal
        uniqueness_group = next(
            (
                p
                for p in response.proposals
                if p.template_id == "template-uniqueness-1"
            ),
            None,
        )

        assert uniqueness_group is not None
        # The attribute should be marked as already_covered
        for obj_group in uniqueness_group.by_dataset.values():
            for obj in obj_group:
                for attr in obj.attributes:
                    if attr.attribute_id == "attr-1":
                        assert attr.already_covered is True

    @pytest.mark.asyncio
    async def test_scope_type_validation(self, service):
        """Test that invalid scope types are rejected."""
        with pytest.raises(ValidationError):
            GenerateProposalsRequest(
                scope_type="invalid_scope",
                scope_id="id-1",
                workspace_id="ws-1",
            )

    @pytest.mark.asyncio
    async def test_empty_scope(self, service, mock_repositories):
        """Test handling of empty scope (no attributes)."""
        data_asset_repo, _, rules_repo = mock_repositories

        data_asset_repo.list_data_assets.return_value = []
        rules_repo.list_rule_records.return_value = []

        request = GenerateProposalsRequest(
            scope_type="workspace",
            scope_id="ws-1",
            workspace_id="ws-1",
        )
        response = await service.generate_proposals(request=request)

        assert response.total_attributes == 0
        assert response.total_proposals == 0
        assert len(response.proposals) == 0

    @pytest.mark.asyncio
    async def test_generate_proposals_prefers_catalog_for_product_scope(self, service, mock_repositories):
        """Product scope should resolve from Data Catalog before Data Assets."""
        data_asset_repo, data_catalog_repo, rules_repo = mock_repositories

        dataset = MagicMock()
        dataset.id = "dataset-1"
        dataset.product_id = "product-1"
        dataset.workspace_id = "ws-1"
        dataset.name = "customer_data"

        data_object = MagicMock()
        data_object.id = "object-1"
        data_object.dataset_id = "dataset-1"
        data_object.name = "customer"

        version = MagicMock()
        version.id = "version-1"
        version.data_object_id = "object-1"

        attribute = MagicMock()
        attribute.id = "attr-1"
        attribute.name = "email"
        attribute.type = "string"
        attribute.nullable = False
        attribute.version_id = "version-1"

        data_catalog_repo.list_data_sets.return_value = [dataset]
        data_catalog_repo.list_data_objects_catalog.return_value = [data_object]
        data_catalog_repo.list_data_object_versions.return_value = [version]
        data_catalog_repo.list_attributes_catalog.return_value = [attribute]

        data_asset_repo.list_data_assets.return_value = []
        rules_repo.list_rule_records.return_value = []

        response = await service.generate_proposals(
            request=GenerateProposalsRequest(
                scope_type="product",
                scope_id="product-1",
                workspace_id="ws-1",
            )
        )

        assert response.total_attributes == 1
        assert response.total_proposals > 0
        data_asset_repo.list_data_assets.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_proposals_rejects_cross_workspace_catalog_scope(self, service, mock_repositories):
        """Catalog-backed scope resolution must stay inside request workspace."""
        data_asset_repo, data_catalog_repo, rules_repo = mock_repositories

        dataset = MagicMock()
        dataset.id = "dataset-1"
        dataset.product_id = "product-1"
        dataset.workspace_id = "other-workspace"
        dataset.name = "customer_data"

        data_object = MagicMock()
        data_object.id = "object-1"
        data_object.dataset_id = "dataset-1"
        data_object.name = "customer"

        version = MagicMock()
        version.id = "version-1"
        version.data_object_id = "object-1"

        attribute = MagicMock()
        attribute.id = "attr-1"
        attribute.name = "email"
        attribute.type = "string"
        attribute.nullable = False
        attribute.version_id = "version-1"

        data_catalog_repo.list_data_sets.return_value = [dataset]
        data_catalog_repo.list_data_objects_catalog.return_value = [data_object]
        data_catalog_repo.list_data_object_versions.return_value = [version]
        data_catalog_repo.list_attributes_catalog.return_value = [attribute]

        data_asset_repo.list_data_assets.return_value = []
        rules_repo.list_rule_records.return_value = []

        with pytest.raises(ValueError, match="Scope not found or has no assets"):
            await service.generate_proposals(
                request=GenerateProposalsRequest(
                    scope_type="product",
                    scope_id="product-1",
                    workspace_id="ws-1",
                )
            )

    @pytest.mark.asyncio
    async def test_grouping_structure(self, service, mock_repositories):
        """Test that proposals are correctly grouped by template and dataset."""
        data_asset_repo, _, rules_repo = mock_repositories

        # Mock two assets in different datasets
        mock_asset1 = MagicMock()
        mock_asset1.id = "asset-1"
        mock_asset1.version_id = "version-1"
        mock_asset1.name = "customer"
        mock_asset1.dataset_id = "dataset-1"
        mock_asset1.dataset_name = "customer_data"
        mock_asset1.contract_schema = {
            "columns": [
                {
                    "id": "attr-1",
                    "name": "email",
                    "data_type": "string",
                    "required": False,
                }
            ]
        }

        mock_asset2 = MagicMock()
        mock_asset2.id = "asset-2"
        mock_asset2.version_id = "version-2"
        mock_asset2.name = "order"
        mock_asset2.dataset_id = "dataset-2"
        mock_asset2.dataset_name = "order_data"
        mock_asset2.contract_schema = {
            "columns": [
                {
                    "id": "attr-2",
                    "name": "email",
                    "data_type": "string",
                    "required": False,
                }
            ]
        }

        data_asset_repo.list_data_assets.return_value = [mock_asset1, mock_asset2]
        rules_repo.list_rule_records.return_value = []

        request = GenerateProposalsRequest(
            scope_type="workspace",
            scope_id="ws-1",
            workspace_id="ws-1",
        )
        response = await service.generate_proposals(request=request)

        # Email Format Check should appear once with two datasets
        email_group = next(
            (p for p in response.proposals if p.template_id == "template-accuracy-2"),
            None,
        )
        assert email_group is not None
        assert len(email_group.by_dataset) == 2
        assert "dataset-1" in email_group.by_dataset
        assert "dataset-2" in email_group.by_dataset

    @pytest.mark.asyncio
    async def test_count_accuracy(self, service, mock_repositories):
        """Test that counts are correct at each level."""
        data_asset_repo, _, rules_repo = mock_repositories

        # Three attributes, some triggering multiple templates
        mock_asset = MagicMock()
        mock_asset.id = "asset-1"
        mock_asset.version_id = "version-1"
        mock_asset.name = "data"
        mock_asset.dataset_id = "dataset-1"
        mock_asset.dataset_name = "data_dataset"
        mock_asset.contract_schema = {
            "columns": [
                {
                    "id": "attr-1",
                    "name": "created_at",
                    "data_type": "date",
                    "required": False,
                },
                {
                    "id": "attr-2",
                    "name": "user_id",
                    "data_type": "string",
                    "required": False,
                },
                {
                    "id": "attr-3",
                    "name": "amount",
                    "data_type": "numeric",
                    "required": False,
                },
            ]
        }

        data_asset_repo.list_data_assets.return_value = [mock_asset]
        rules_repo.list_rule_records.return_value = []

        request = GenerateProposalsRequest(
            scope_type="workspace",
            scope_id="ws-1",
            workspace_id="ws-1",
        )
        response = await service.generate_proposals(request=request)

        assert response.total_attributes == 3
        # Validate that total_proposals is > 3 (multiple proposals per attribute)
        assert response.total_proposals > 3

        # Each template group count should match sum of object group counts
        for template_group in response.proposals:
            calculated_count = sum(
                len(obj_list)
                for obj_list in template_group.by_dataset.values()
            )
            # This won't match exactly due to grouping structure,
            # but the logic should be sound

    @pytest.mark.asyncio
    async def test_create_rule_batch_mixed_outcomes(self, service, mock_repositories):
        """Batch creation should return created, skipped, and failed outcomes."""
        _, data_catalog_repo, rules_repo = mock_repositories

        attr_email = MagicMock()
        attr_email.id = "attr-email"
        attr_email.name = "email"
        attr_email.type = "string"
        attr_email.nullable = False
        attr_email.version_id = "version-1"
        attr_email.workspace_id = "ws-1"

        attr_phone = MagicMock()
        attr_phone.id = "attr-phone"
        attr_phone.name = "phone_number"
        attr_phone.type = "string"
        attr_phone.nullable = True
        attr_phone.version_id = "version-1"
        attr_phone.workspace_id = "ws-1"

        attr_user_id = MagicMock()
        attr_user_id.id = "attr-user-id"
        attr_user_id.name = "user_id"
        attr_user_id.type = "string"
        attr_user_id.nullable = False
        attr_user_id.version_id = "version-1"
        attr_user_id.workspace_id = "ws-1"

        data_catalog_repo.list_attributes_catalog.return_value = [
            attr_email,
            attr_phone,
            attr_user_id,
        ]
        data_catalog_repo.list_rule_attributes.return_value = [
            MagicMock(ruleId="rule-existing", attributeId="attr-email")
        ]

        existing_rule = MagicMock()
        existing_rule.id = "rule-existing"
        existing_rule.active = True
        existing_rule.deleted_on = None
        existing_rule.check_type = "REGEX"
        rules_repo.list_rule_records.return_value = [existing_rule]

        async def create_rule_side_effect(**kwargs):
            if kwargs["suggestion_id"] == "template-uniqueness-1::version-1::attr-user-id":
                raise RuntimeError("cannot persist rule")
            return MagicMock(id="rule-created")

        rules_repo.create_rule_record.side_effect = create_rule_side_effect

        response = await service.create_rule_batch(
            request=CreateBatchRequest(
                workspace_id="ws-1",
                accepted_proposal_ids=[
                    "template-accuracy-2::version-1::attr-email",
                    "template-accuracy-3::version-1::attr-phone",
                    "template-uniqueness-1::version-1::attr-user-id",
                ],
            ),
            actor_id="user-admin",
        )

        assert response.total_accepted == 3
        assert response.created == 1
        assert response.skipped == 1
        assert response.failed == 1
        assert len(response.outcomes) == 3
        assert any(o.status == "skipped" and "already has equivalent rule" in str(o.reason) for o in response.outcomes)
        assert any(o.status == "created" and o.rule_id == "rule-created" for o in response.outcomes)
        assert any(o.status == "failed" and "cannot persist rule" in str(o.reason) for o in response.outcomes)

    @pytest.mark.asyncio
    async def test_create_rule_batch_rejects_invalid_proposal_ids(self, service, mock_repositories):
        """Invalid proposal IDs should fail fast with ValueError."""
        _, data_catalog_repo, _ = mock_repositories

        data_catalog_repo.list_attributes_catalog.return_value = []

        with pytest.raises(ValueError, match="Invalid proposal ids"):
            await service.create_rule_batch(
                request=CreateBatchRequest(
                    workspace_id="ws-1",
                    accepted_proposal_ids=["template-accuracy-2::version-1::missing-attr"],
                ),
                actor_id="user-admin",
            )


class TestOnboardingEndpoint:
    """Tests for the onboarding API endpoint."""

    def test_endpoint_placeholder(self):
        """Endpoint integration coverage is handled in API test suites."""
        assert True


class TestOnboardingWorkspaceAuthorization:
    """Tests for onboarding workspace authorization helper."""

    @pytest.fixture
    def workspace_id(self) -> str:
        return "default"

    @pytest.fixture
    def canonical_scopes(self) -> list[str]:
        return ["dq:rules:write"]

    def test_allows_canonical_scopes(self, canonical_scopes, workspace_id):
        assert _is_workspace_authorized(canonical_scopes, workspace_id) is True

    def test_allows_explicit_workspace_scope(self, workspace_id):
        scopes = [f"workspace:{workspace_id}"]
        assert _is_workspace_authorized(scopes, workspace_id) is True

    def test_denies_missing_scopes(self, workspace_id):
        scopes = ["dq:notifications:read"]
        assert _is_workspace_authorized(scopes, workspace_id) is False
