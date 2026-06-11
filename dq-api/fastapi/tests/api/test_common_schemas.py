import pytest


pytestmark = pytest.mark.asyncio


async def test_health_endpoint_snake_case(async_client):
    response = await async_client.get("/api/system/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "timestamp" in body


async def test_system_info_snake_case(async_client):
    response = await async_client.get("/api/system/v1/system-info")
    assert response.status_code == 200
    body = response.json()
    # database keys should be snake_case due to SnakeModel aliasing
    assert "database" in body
    assert "schema_version" in body["database"]
