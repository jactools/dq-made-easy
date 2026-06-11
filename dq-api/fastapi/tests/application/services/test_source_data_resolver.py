import asyncio

import pytest

from app.application.services.source_data_resolver import SourceDataResolutionError
from app.application.services.source_data_resolver import SourceDataResolver
from app.api.v1.schemas.gx_artifact_view import GxArtifactAssignmentScopeView
from app.domain.entities.data_catalog import DataObjectCatalogEntity
from app.domain.entities.data_catalog import DataObjectVersionEntity
from app.domain.entities.data_catalog import DataProductEntity
from app.domain.entities.data_catalog import DataSetEntity


class _StubCatalogRepository:
    def __init__(self) -> None:
        self._datasets = [
            DataSetEntity(id="ds-1", product_id="odcs.dp.sales-001", name="Customers", tags=["pii"]),
            DataSetEntity(id="ds-2", product_id="odcs.dp.inventory-001", name="Orders", tags=["finance"]),
        ]
        self._products = [
            DataProductEntity(id="odcs.dp.sales-001", name="Sales"),
            DataProductEntity(id="odcs.dp.inventory-001", name="Inventory"),
        ]
        self._objects = [
            DataObjectCatalogEntity(
                id="do-1",
                dataset_id="ds-1",
                name="Customer",
                latest_version_id="dov-1",
                tags=["pii"],
            ),
            DataObjectCatalogEntity(
                id="do-2",
                dataset_id="ds-1",
                name="CustomerAddress",
                latest_version_id="dov-2",
                tags=["contact"],
            ),
            DataObjectCatalogEntity(
                id="do-3",
                dataset_id="ds-2",
                name="Order",
                latest_version_id="dov-3",
                tags=["finance"],
            ),
        ]
        self._versions = {
            "do-1": [DataObjectVersionEntity(id="dov-1", data_object_id="do-1", version=3, tags=["pii"])],
            "do-2": [DataObjectVersionEntity(id="dov-2", data_object_id="do-2", version=5, tags=["contact"])],
            "do-3": [DataObjectVersionEntity(id="dov-3", data_object_id="do-3", version=2, tags=["finance"])],
        }

    def list_data_sets(self, product_id: str | None = None, workspace: str | None = None):
        del workspace
        if product_id:
            return [dataset for dataset in self._datasets if dataset.product_id == product_id]
        return list(self._datasets)

    def list_data_objects_catalog(self, data_set_id: str | None = None):
        if data_set_id:
            return [row for row in self._objects if row.dataset_id == data_set_id]
        return list(self._objects)

    def list_data_object_versions(self, object_id: str | None = None):
        if object_id:
            return list(self._versions.get(object_id, []))
        rows = []
        for versions in self._versions.values():
            rows.extend(versions)
        return rows

    def list_data_products(self, workspace: str | None = None):
        del workspace
        return list(self._products)

    def list_data_objects(self):
        raise AssertionError("not used")

    def list_rule_attributes(self):
        raise AssertionError("not used")

    def add_rule_attributes(self, entries: list[dict]):
        raise AssertionError("not used")

    def get_attribute_rule_counts(self):
        raise AssertionError("not used")

    def list_attributes_catalog(self, version_id: str | None = None):
        del version_id
        raise AssertionError("not used")

    def list_data_deliveries(self, version_id: str | None = None):
        del version_id
        raise AssertionError("not used")


@pytest.fixture()
def catalog_repository() -> _StubCatalogRepository:
    return _StubCatalogRepository()


@pytest.fixture()
def resolver(catalog_repository: _StubCatalogRepository) -> SourceDataResolver:
    return SourceDataResolver(catalog_repository=catalog_repository)


def test_resolve_assignment_scope_by_data_object_id(resolver: SourceDataResolver) -> None:
    result = asyncio.run(
        resolver.resolve_assignment_scope(GxArtifactAssignmentScopeView(dataObjectId="do-1"))
    )

    assert result["assignmentScope"]["dataObjectId"] == "do-1"
    assert result["resolvedExecutionScope"]["dataObjectVersionIds"] == ["dov-1"]
    assert result["resolvedTargets"] == [
        {
            "dataObjectId": "do-1",
            "datasetId": "ds-1",
            "dataProductId": "odcs.dp.sales-001",
            "dataObjectVersionId": "dov-1",
            "dataObjectVersion": 3,
        }
    ]


def test_resolve_assignment_scope_by_dataset_id(resolver: SourceDataResolver) -> None:
    result = asyncio.run(resolver.resolve_assignment_scope({"datasetId": "ds-1"}))

    assert result["assignmentScope"]["datasetId"] == "ds-1"
    assert result["resolvedExecutionScope"]["dataObjectVersionIds"] == ["dov-1", "dov-2"]
    assert [target["dataObjectId"] for target in result["resolvedTargets"]] == ["do-1", "do-2"]


def test_resolve_assignment_scope_by_data_product_id(resolver: SourceDataResolver) -> None:
    result = asyncio.run(resolver.resolve_assignment_scope({"dataProductId": "odcs.dp.sales-001"}))

    assert result["assignmentScope"]["dataProductId"] == "odcs.dp.sales-001"
    assert result["resolvedExecutionScope"]["dataObjectVersionIds"] == ["dov-1", "dov-2"]
    assert [target["datasetId"] for target in result["resolvedTargets"]] == ["ds-1", "ds-1"]


def test_resolve_assignment_scope_validates_product_membership(resolver: SourceDataResolver) -> None:
    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(
            resolver.resolve_assignment_scope(
                {"datasetId": "ds-2", "dataProductId": "odcs.dp.sales-001"}
            )
        )

    assert "does not belong" in str(error.value)


def test_resolve_assignment_scope_fails_when_latest_version_is_missing() -> None:
    class _MissingVersionRepository(_StubCatalogRepository):
        def __init__(self) -> None:
            super().__init__()
            self._objects[0] = DataObjectCatalogEntity(
                id="do-1",
                dataset_id="ds-1",
                name="Customer",
                latest_version_id="dov-missing",
            )

    resolver = SourceDataResolver(catalog_repository=_MissingVersionRepository())

    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(resolver.resolve_assignment_scope({"dataObjectId": "do-1"}))

    assert "latest_version_id" in str(error.value)


def test_resolve_assignment_scope_requires_an_identifier(resolver: SourceDataResolver) -> None:
    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(resolver.resolve_assignment_scope({}))

    assert "invalid" in str(error.value).lower()


def test_resolve_assignment_scope_fails_when_product_has_no_datasets(resolver: SourceDataResolver) -> None:
    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(resolver.resolve_assignment_scope({"dataProductId": "odcs.dp.unknown"}))

    assert "does not map to any data sets" in str(error.value)


def test_resolve_assignment_scope_fails_when_dataset_is_missing_from_catalog(resolver: SourceDataResolver) -> None:
    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(resolver.resolve_assignment_scope({"datasetId": "ds-missing"}))

    assert "was not found in the catalog" in str(error.value)


def test_resolve_assignment_scope_fails_when_data_object_is_missing(resolver: SourceDataResolver) -> None:
    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(resolver.resolve_assignment_scope({"dataObjectId": "do-missing"}))

    assert "was not found in the selected scope" in str(error.value)


def test_resolve_assignment_scope_fails_when_data_object_is_ambiguous() -> None:
    class _AmbiguousRepository(_StubCatalogRepository):
        def __init__(self) -> None:
            super().__init__()
            self._objects.append(
                DataObjectCatalogEntity(
                    id="do-1",
                    dataset_id="ds-2",
                    name="CustomerDuplicate",
                    latest_version_id="dov-3",
                )
            )

    resolver = SourceDataResolver(catalog_repository=_AmbiguousRepository())

    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(resolver.resolve_assignment_scope({"dataObjectId": "do-1"}))

    assert "resolved to multiple catalog entries" in str(error.value)


def test_resolve_assignment_scope_fails_when_scope_matches_no_candidate_targets(resolver: SourceDataResolver) -> None:
    resolver._resolve_candidate_objects = lambda scope, allowed_dataset_ids, datasets_by_id, products_by_id: []

    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(resolver.resolve_assignment_scope({"datasetId": "ds-1"}))

    assert "does not resolve to any active dataObjectVersionId targets" in str(error.value)


def test_resolve_assignment_scope_fails_when_resolved_targets_have_no_execution_ids(resolver: SourceDataResolver) -> None:
    resolver._sort_candidate_rows = lambda candidate_rows, datasets_by_id: []

    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(resolver.resolve_assignment_scope({"datasetId": "ds-1"}))

    assert "does not resolve to any active dataObjectVersionId targets" in str(error.value)


def test_resolve_assignment_scope_fails_when_data_object_references_missing_dataset() -> None:
    class _MissingLookupDict(dict):
        def get(self, key, default=None):
            del key, default
            return None

    class _MissingDatasetRepository(_StubCatalogRepository):
        def __init__(self) -> None:
            super().__init__()
            self._objects = [
                DataObjectCatalogEntity(
                    id="do-9",
                    dataset_id="ds-missing",
                    name="OrphanObject",
                    latest_version_id="dov-9",
                )
            ]
            self._versions = {"do-9": [DataObjectVersionEntity(id="dov-9", data_object_id="do-9", version=1)]}

    resolver = SourceDataResolver(catalog_repository=_MissingDatasetRepository())
    resolver._load_datasets_by_id = lambda: _MissingLookupDict(
        {"ds-missing": DataSetEntity(id="ds-missing", product_id="odcs.dp.sales-001", name="Missing")}
    )

    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(resolver.resolve_assignment_scope({"dataObjectId": "do-9"}))

    assert "references missing datasetId" in str(error.value)


def test_resolve_assignment_scope_fails_when_latest_version_id_is_blank() -> None:
    class _BlankLatestVersionRepository(_StubCatalogRepository):
        def __init__(self) -> None:
            super().__init__()
            self._objects[0] = DataObjectCatalogEntity(
                id="do-1",
                dataset_id="ds-1",
                name="Customer",
                latest_version_id="   ",
            )

    resolver = SourceDataResolver(catalog_repository=_BlankLatestVersionRepository())

    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(resolver.resolve_assignment_scope({"dataObjectId": "do-1"}))

    assert "does not define an active latest version" in str(error.value)


def test_resolve_assignment_scope_filters_by_tags() -> None:
    resolver = SourceDataResolver(catalog_repository=_StubCatalogRepository())

    result = asyncio.run(resolver.resolve_assignment_scope({"tagIds": ["finance"]}))

    assert [target["dataObjectId"] for target in result["resolvedTargets"]] == ["do-3"]
    assert result["resolvedExecutionScope"]["dataObjectVersionIds"] == ["dov-3"]


def test_resolve_assignment_scope_fails_when_no_registered_versions_exist() -> None:
    class _NoVersionsRepository(_StubCatalogRepository):
        def __init__(self) -> None:
            super().__init__()
            self._versions["do-1"] = []

    resolver = SourceDataResolver(catalog_repository=_NoVersionsRepository())

    with pytest.raises(SourceDataResolutionError) as error:
        asyncio.run(resolver.resolve_assignment_scope({"dataObjectId": "do-1"}))

    assert "does not have any registered versions" in str(error.value)