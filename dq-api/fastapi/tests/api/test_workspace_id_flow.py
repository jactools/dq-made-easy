"""
Test to trace workspace_id through the complete data flow.
"""

import pytest
from app.domain.entities.data_catalog import DataProductEntity
from app.infrastructure.repositories.postgres_data_catalog_repository import PostgresDataCatalogRepository
from app.api.presenters.data_catalog import build_data_catalog_page_payload
from app.application.resolvers.data_catalog_resolver import resolve_data_products_page_view
from app.infrastructure.orm.models import DataProductRow
from sqlalchemy import select
from app.infrastructure.orm.session import session_scope


def test_database_has_workspace_id():
    """Verify database actually contains workspace_id values."""
    database_url = "postgresql://postgres:postgres@localhost:5432/dq"
    with session_scope(database_url) as session:
        rows = session.execute(select(DataProductRow)).scalars().all()
        assert len(rows) > 0, "No products in database"
        
        for row in rows[:3]:
            print(f"\nDatabase row for '{row.name}':")
            print(f"  workspace_id value: {repr(row.workspace_id)}")
            print(f"  workspace_id type: {type(row.workspace_id)}")
            print(f"  workspace_id is None: {row.workspace_id is None}")
            print(f"  workspace_id == '': {row.workspace_id == ''}")
            assert row.workspace_id is not None or row.workspace_id == "", \
                f"workspace_id should not be missing for {row.name}"


def test_repository_returns_workspace_id():
    """Verify repository correctly retrieves workspace_id from database."""
    database_url = "postgresql://postgres:postgres@localhost:5432/dq"
    repo = PostgresDataCatalogRepository(database_url)
    
    products = repo.list_data_products()
    assert len(products) > 0, "Repository returned no products"
    
    for product in products[:3]:
        print(f"\nRepository entity for '{product.name}':")
        print(f"  workspace_id value: {repr(product.workspace_id)}")
        print(f"  workspace_id type: {type(product.workspace_id)}")
        print(f"  workspace_id is empty: {product.workspace_id == ''}")
        assert isinstance(product.workspace_id, str), \
            f"workspace_id should be str, got {type(product.workspace_id)}"


def test_entity_model_dump_includes_workspace_id():
    """Verify model_dump() includes workspace_id."""
    product = DataProductEntity(
        id="test-id",
        name="Test Product",
        workspace_id="test-workspace",
    )
    
    dumped = product.model_dump()
    print(f"\nModel dump of entity:")
    print(f"  Has workspace_id key: {'workspace_id' in dumped}")
    print(f"  workspace_id value: {repr(dumped.get('workspace_id'))}")
    
    assert "workspace_id" in dumped, "workspace_id missing from model_dump()"
    assert dumped["workspace_id"] == "test-workspace"


def test_pagination_wrapper_preserves_workspace_id():
    """Verify build_data_catalog_page_payload preserves workspace_id."""
    data = [
        {"id": "1", "name": "Product 1", "workspace_id": "ws-1"},
        {"id": "2", "name": "Product 2", "workspace_id": "ws-2"},
    ]
    
    payload = build_data_catalog_page_payload(data, page=1, limit=10)
    
    print(f"\nPagination payload:")
    print(f"  First item workspace_id: {repr(payload['data'][0].get('workspace_id'))}")
    
    assert payload["data"][0]["workspace_id"] == "ws-1"
    assert payload["data"][1]["workspace_id"] == "ws-2"


def test_response_model_validation_preserves_workspace_id():
    """Verify DataProductsPageView validation preserves workspace_id."""
    payload = {
        "data": [
            {
                "id": "1",
                "name": "Product 1",
                "workspace_id": "test-workspace",
                "description": "",
                "owner": "",
                "created_at": "",
                "icon": "",
            }
        ],
        "pagination": {
            "total": 1,
            "page": 1,
            "limit": 10,
            "total_pages": 1,
            "has_next": False,
            "has_previous": False,
        }
    }
    
    view = resolve_data_products_page_view(payload)
    print(f"\nResponse model validation:")
    print(f"  First product workspace_id: {repr(view.data[0].workspace_id)}")
    
    assert view.data[0].workspace_id == "test-workspace"


def test_full_repository_to_response_flow():
    """Test the complete flow from repository to response model."""
    database_url = "postgresql://postgres:postgres@localhost:5432/dq"
    repo = PostgresDataCatalogRepository(database_url)
    
    # Get entities from repository
    products = repo.list_data_products()
    assert len(products) > 0
    
    # Dump to dicts (like in the endpoint)
    product_dicts = [p.model_dump() for p in products[:1]]
    
    # Build pagination wrapper
    payload = build_data_catalog_page_payload(product_dicts, page=1, limit=10)
    
    # Validate through response model
    view = resolve_data_products_page_view(payload)
    
    print(f"\nFull flow result:")
    print(f"  Product name: {view.data[0].name}")
    print(f"  Product workspace_id: {repr(view.data[0].workspace_id)}")
    print(f"  workspace_id is empty: {view.data[0].workspace_id == ''}")
    
    # The issue: if workspace_id ends up as "", that's the problem
    if view.data[0].workspace_id == "":
        print("  ⚠️ workspace_id is EMPTY STRING - this is the issue!")
    else:
        print(f"  ✓ workspace_id is correctly set to {repr(view.data[0].workspace_id)}")


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])
