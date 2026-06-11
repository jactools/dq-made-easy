import pytest
from tests.fixtures.user_fixtures import profiling_user_row
from tests.fixtures.suggestions_mock_fixtures import mock_data_source_row
from app.infrastructure.orm.session import session_scope
from app.infrastructure.orm.models import DataSourceMetadataRow, DataSourceProfilingRequestRow, UserRow
from sqlalchemy import delete, select
from app.core.config import get_settings
from datetime import UTC, datetime

@pytest.fixture
def setup_profiling_user_and_mock_data(profiling_user_row, mock_data_source_row):
    database_url = get_settings().database_url
    with session_scope(database_url) as session:
        session.execute(
            delete(DataSourceProfilingRequestRow).where(
                DataSourceProfilingRequestRow.data_source_id == mock_data_source_row["data_source_id"]
            )
        )
        # Ensure user exists
        user = session.execute(select(UserRow).where(UserRow.id == profiling_user_row["id"])).scalar_one_or_none()
        if not user:
            session.add(
                UserRow(
                    id=profiling_user_row["id"],
                    first_name="Test",
                    last_name="User",
                    email=profiling_user_row.get("email"),
                    external_id=profiling_user_row.get("external_id"),
                )
            )
        # Add mock-data source
        ds = session.execute(select(DataSourceMetadataRow).where(DataSourceMetadataRow.data_source_id == mock_data_source_row["data_source_id"])).scalar_one_or_none()
        if not ds:
            session.add(
                DataSourceMetadataRow(
                    id=mock_data_source_row["id"],
                    data_source_id=mock_data_source_row["data_source_id"],
                    name=mock_data_source_row["name"],
                    source_type=mock_data_source_row["source_type"],
                    record_count=mock_data_source_row.get("record_count"),
                )
            )
        session.commit()


def test_profiling_request_and_status(setup_profiling_user_and_mock_data, client, auth_headers):
    # Submit profiling request
    resp = client.post(
        "/api/data-catalog/v1/profiling/requests?data_source_id=mock-data&workspace_id=retail-banking",
        headers=auth_headers("dq:profiling:request", sub="user-profiling", preferred_username="profiling-user"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"]
    profiling_request_id = data["profiling_request_id"]
    assert data["events_url"] == f"/data-catalog/v1/profiling/requests/{profiling_request_id}/events"

    database_url = get_settings().database_url
    with session_scope(database_url) as session:
        request_row = session.execute(
            select(DataSourceProfilingRequestRow).where(DataSourceProfilingRequestRow.id == profiling_request_id)
        ).scalar_one()
        request_row.status = "completed"
        request_row.started_at = datetime.now(UTC)
        request_row.completed_at = datetime.now(UTC)
        request_row.result_metadata_id = "result-meta-1"
        session.commit()

    # Poll status until completed or failed
    status_resp = client.get(
        f"/api/data-catalog/v1/profiling/requests/{profiling_request_id}/status",
        headers=auth_headers("dq:rules:read", sub="user-profiling", preferred_username="profiling-user"),
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    status = status_data["request"]["status"]

    assert status == "completed"
    assert status_data["request"]["result_metadata_id"] is not None
    assert status_data["request"]["started_at"] is not None
    assert status_data["request"]["completed_at"] is not None

    events_resp = client.get(
        f"/api/data-catalog/v1/profiling/requests/{profiling_request_id}/events",
        headers=auth_headers("dq:rules:read", sub="user-profiling", preferred_username="profiling-user"),
    )
    assert events_resp.status_code == 200
    assert events_resp.headers["content-type"].startswith("text/event-stream")
    assert "event: snapshot" in events_resp.text
    assert f'"request_id":"{profiling_request_id}"' in events_resp.text
    assert '"status":"completed"' in events_resp.text
