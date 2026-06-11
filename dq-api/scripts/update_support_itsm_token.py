#!/usr/bin/env python3
"""Persist the generated Zammad support token in app-config."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _add_fastapi_path() -> None:
    candidates = []

    dq_api_root = os.getenv("DQ_API_ROOT", "").strip()
    if dq_api_root:
        candidates.append(Path(dq_api_root))

    script_dir = Path(__file__).resolve().parent
    candidates.append(script_dir.parent / "fastapi")
    candidates.append(Path("/app"))

    for fastapi_dir in candidates:
        if fastapi_dir.is_dir():
            fastapi_path = str(fastapi_dir)
            if fastapi_path not in sys.path:
                sys.path.insert(0, fastapi_path)
            return

    raise SystemExit("Unable to locate the FastAPI application directory for support token persistence")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-file", required=True, type=Path, help="Path to the generated Zammad token")
    args = parser.parse_args()

    database_url = os.getenv("DQ_DB_INTERNAL_URL", "").strip()
    if not database_url:
        raise SystemExit("DQ_DB_INTERNAL_URL is required to persist the support ITSM token")

    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit(f"Token file is empty: {args.token_file}")

    _add_fastapi_path()

    from app.infrastructure.repositories.postgres_app_config_repository import PostgresAppConfigRepository

    repository = PostgresAppConfigRepository(database_url)
    config = repository.get_app_config().model_dump()
    config["assistanceRequestItsmAuthToken"] = token
    repository.set_app_config(config)

    print("Persisted the Zammad support token in app-config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())