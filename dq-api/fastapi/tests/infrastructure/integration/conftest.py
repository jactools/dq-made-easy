"""Conftest for integration tests that require the live Postgres container.

All tests in this directory are skipped automatically when the container is
not reachable. Start the full stack first:

    ./scripts/start-all.sh --seed-all

Then run only integration tests with:

    pytest -m integration

The connection URL defaults to the local Postgres mapping unless
DQ_DB_LOCAL_URL is provided by the caller.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.infrastructure.orm.session import normalize_database_url

_LIVE_DB_URL = normalize_database_url(
    os.environ.get("DQ_DB_LOCAL_URL", "postgresql://postgres:postgres@localhost:5432/dq")
)


def _db_reachable() -> bool:
    try:
        engine = create_engine(_LIVE_DB_URL, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


_REACHABLE: bool = _db_reachable()

_FASTAPI_ROOT = Path(__file__).resolve().parents[3]


def _run_alembic_upgrade() -> None:
    environment = os.environ.copy()
    environment["DQ_DB_LOCAL_URL"] = _LIVE_DB_URL
    environment["REQUIRE_DATABASE"] = "true"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=_FASTAPI_ROOT,
        env=environment,
        check=True,
    )


@pytest.fixture(scope="session", autouse=True)
def apply_database_migrations() -> None:
    if not _REACHABLE:
        raise RuntimeError(f"Postgres container not reachable at {_LIVE_DB_URL}; integration tests cannot run")
    _run_alembic_upgrade()


@pytest.fixture(scope="module")
def live_db_url() -> str:
    if not _REACHABLE:
        raise RuntimeError(f"Postgres container not reachable at {_LIVE_DB_URL}; integration tests cannot run")
    return _LIVE_DB_URL


@pytest.fixture(scope="module")
def live_engine():
    if not _REACHABLE:
        raise RuntimeError(f"Postgres container not reachable at {_LIVE_DB_URL}; integration tests cannot run")
    engine = create_engine(_LIVE_DB_URL, future=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def live_redis_url() -> str:
    redis_url = os.environ.get("GX_EXECUTION_REDIS_URL") or os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
    try:
        import redis
    except Exception as exc:
        raise RuntimeError("redis package is required for GX integration tests") from exc

    client = redis.Redis.from_url(redis_url, decode_responses=True)
    try:
        if not client.ping():
            raise RuntimeError(f"Redis is unreachable at {redis_url}")
    except Exception as exc:
        raise RuntimeError(f"Redis is unreachable at {redis_url}") from exc
    finally:
        try:
            client.close()
        except Exception:
            pass
    return redis_url


@pytest.fixture(scope="module")
def live_redis_client(live_redis_url: str):
    try:
        import redis
    except Exception as exc:
        raise RuntimeError("redis package is required for GX integration tests") from exc

    client = redis.Redis.from_url(live_redis_url, decode_responses=True)
    try:
        if not client.ping():
            raise RuntimeError(f"Redis is unreachable at {live_redis_url}")
    except Exception as exc:
        client.close()
        raise RuntimeError(f"Redis is unreachable at {live_redis_url}") from exc

    yield client
    client.close()


@pytest.fixture(scope="session", autouse=True)
def force_database_backed_dependencies() -> None:
    previous_database_url = os.environ.get("DQ_DB_LOCAL_URL")
    previous_require_database = os.environ.get("REQUIRE_DATABASE")
    previous_redis_url = os.environ.get("REDIS_URL")
    previous_gx_execution_redis_url = os.environ.get("GX_EXECUTION_REDIS_URL")

    os.environ["DQ_DB_LOCAL_URL"] = _LIVE_DB_URL
    os.environ["REQUIRE_DATABASE"] = "true"
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("GX_EXECUTION_REDIS_URL", os.environ["REDIS_URL"])
    get_settings.cache_clear()
    yield

    if previous_database_url is None:
        os.environ.pop("DQ_DB_LOCAL_URL", None)
    else:
        os.environ["DQ_DB_LOCAL_URL"] = previous_database_url

    if previous_require_database is None:
        os.environ.pop("REQUIRE_DATABASE", None)
    else:
        os.environ["REQUIRE_DATABASE"] = previous_require_database

    if previous_redis_url is None:
        os.environ.pop("REDIS_URL", None)
    else:
        os.environ["REDIS_URL"] = previous_redis_url

    if previous_gx_execution_redis_url is None:
        os.environ.pop("GX_EXECUTION_REDIS_URL", None)
    else:
        os.environ["GX_EXECUTION_REDIS_URL"] = previous_gx_execution_redis_url

    get_settings.cache_clear()
