#!/usr/bin/env python3
"""Ingest the approved playground source bundle catalog into AIStor.

What it does:
- Loads the approved bundle manifest from the FastAPI application package.
- Uploads each bundle record to AIStor once and skips bundles already present.
- Fails fast if the S3-compatible storage configuration is missing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
FASTAPI_DIR = ROOT_DIR / "dq-api" / "fastapi"
if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

from app.application.services.playground_source_bundles import (  # noqa: E402
    PLAYGROUND_SOURCE_BUNDLES,
    build_playground_source_bundle_ingestion_service,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle-id",
        action="append",
        dest="bundle_ids",
        help="Restrict ingestion to the selected bundle id(s). May be provided multiple times.",
    )
    parser.add_argument("--bucket", help="Override the AIStor bucket name.")
    parser.add_argument("--prefix", help="Override the AIStor object prefix.")
    parser.add_argument("--dry-run", action="store_true", help="Print the bundles that would be ingested without writing to AIStor.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected_bundle_ids = set(args.bundle_ids or [])
    selected_bundles = [spec for spec in PLAYGROUND_SOURCE_BUNDLES if not selected_bundle_ids or spec.bundle_id in selected_bundle_ids]
    if not selected_bundles:
        raise SystemExit("No matching playground source bundles were selected")

    if args.dry_run:
        print(json.dumps([spec.__dict__ for spec in selected_bundles], indent=2, sort_keys=True))
        return 0

    service = build_playground_source_bundle_ingestion_service(bucket=args.bucket, prefix=args.prefix)
    results = service.ingest_bundles(selected_bundles)

    print(json.dumps([result.__dict__ for result in results], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
