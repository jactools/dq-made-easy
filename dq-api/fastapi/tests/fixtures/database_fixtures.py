import os

import pytest


@pytest.fixture
def postgres_dsn() -> str:
    return "postgresql://example"


@pytest.fixture
def postgres_dependency_url() -> str:
    return os.environ.get("DQ_DB_LOCAL_URL", "postgresql://postgres:postgres@localhost:5432/dq")
