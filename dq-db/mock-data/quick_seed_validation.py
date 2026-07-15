#!/usr/bin/env python3
"""Quick seed for validation run plans without Keycloak dependency."""

import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Try to import SQLAlchemy
try:
    from sqlalchemy import create_engine, text
except ImportError:
    print("Installing SQLAlchemy...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "sqlalchemy", "psycopg2-binary"])
    from sqlalchemy import create_engine, text

# Configuration
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dq")
MOCK_DIR = Path(__file__).parent


def load_csv_data(csv_path: str) -> list[dict[str, Any]]:
    """Load CSV data into list of dicts."""
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_json_file(json_path: str) -> dict | list | None:
    """Load JSON from file if it exists."""
    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"  Warning: Could not load {json_path}: {e}")
    return None


async def seed_validation_run_plans(engine) -> None:
    """Seed validation run plans from CSV."""
    csv_path = MOCK_DIR / "validation-run-plans.csv"
    print(f"\n=== Seeding Validation Run Plans ===")
    print(f"Loading {csv_path}...")
    
    data = load_csv_data(str(csv_path))
    print(f"Found {len(data)} validation run plans")
    
    with engine.begin() as conn:
        inserted = 0
        for row_data in data:
            plan_id = row_data.get("id")
            if not plan_id:
                continue
            
            # Check if already exists
            result = conn.execute(
                text("SELECT id FROM validation_run_plans WHERE id = :id"),
                {"id": plan_id}
            )
            if result.fetchone():
                continue
            
            # Load scope selector JSON if path exists
            scope_selector_path = row_data.get("scope_selector_json", "")
            scope_selector_json = load_json_file(scope_selector_path)
            
            # Parse dates
            created_at = row_data.get("created_at", "")
            updated_at = row_data.get("updated_at", "")
            
            try:
                created_at_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else datetime.now()
                updated_at_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00")) if updated_at else datetime.now()
            except:
                created_at_dt = datetime.now()
                updated_at_dt = datetime.now()
            
            # Insert
            conn.execute(text("""
                INSERT INTO validation_run_plans (
                    id, business_key, workspace_id, scope_selector_json, planning_mode,
                    current_active_version_id, status, created_by, created_at, updated_at,
                    activated_by, activated_at, last_dispatched_run_id
                ) VALUES (
                    :id, :business_key, :workspace_id, :scope_selector_json, :planning_mode,
                    :current_active_version_id, :status, :created_by, :created_at, :updated_at,
                    :activated_by, :activated_at, :last_dispatched_run_id
                )
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": plan_id,
                "business_key": row_data.get("business_key", ""),
                "workspace_id": row_data.get("workspace_id", ""),
                "scope_selector_json": json.dumps(scope_selector_json) if scope_selector_json else None,
                "planning_mode": row_data.get("planning_mode", "single_suite"),
                "current_active_version_id": row_data.get("current_active_version_id"),
                "status": row_data.get("status", "draft"),
                "created_by": row_data.get("created_by", "system"),
                "created_at": created_at_dt,
                "updated_at": updated_at_dt,
                "activated_by": row_data.get("activated_by"),
                "activated_at": datetime.fromisoformat(row_data.get("activated_at", "").replace("Z", "+00:00")) if row_data.get("activated_at") else None,
                "last_dispatched_run_id": row_data.get("last_dispatched_run_id"),
            })
            inserted += 1
        
        print(f"Inserted {inserted} new validation run plans")


async def seed_validation_run_plan_versions(engine) -> None:
    """Seed validation run plan versions from CSV."""
    csv_path = MOCK_DIR / "validation-run-plan-versions.csv"
    print(f"\n=== Seeding Validation Run Plan Versions ===")
    print(f"Loading {csv_path}...")
    
    data = load_csv_data(str(csv_path))
    print(f"Found {len(data)} validation run plan versions")
    
    with engine.begin() as conn:
        inserted = 0
        for row_data in data:
            version_id = row_data.get("id")
            if not version_id:
                continue
            
            # Check if already exists
            result = conn.execute(
                text("SELECT id FROM validation_run_plan_versions WHERE id = :id"),
                {"id": version_id}
            )
            if result.fetchone():
                continue
            
            # Parse dates
            effective_from = row_data.get("effective_from", "")
            created_at = row_data.get("created_at", "")
            
            try:
                effective_from_dt = datetime.fromisoformat(effective_from.replace("Z", "+00:00")) if effective_from else None
                created_at_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else datetime.now()
            except:
                effective_from_dt = None
                created_at_dt = datetime.now()
            
            # Insert
            conn.execute(text("""
                INSERT INTO validation_run_plan_versions (
                    id, run_plan_id, validation_artifact_selection_json, artifact_id, artifact_version,
                    governance_state, validation_status, review_status, effective_from,
                    supersedes_version_id, created_by, created_at
                ) VALUES (
                    :id, :run_plan_id, :validation_artifact_selection_json, :artifact_id, :artifact_version,
                    :governance_state, :validation_status, :review_status, :effective_from,
                    :supersedes_version_id, :created_by, :created_at
                )
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": version_id,
                "run_plan_id": row_data.get("run_plan_id", ""),
                "validation_artifact_selection_json": "{}",  # Would load from file
                "artifact_id": row_data.get("artifact_id"),
                "artifact_version": int(row_data.get("artifact_version", 1)),
                "governance_state": row_data.get("governance_state", "draft"),
                "validation_status": row_data.get("validation_status", "not_requested"),
                "review_status": row_data.get("review_status", "pending"),
                "effective_from": effective_from_dt,
                "supersedes_version_id": row_data.get("supersedes_version_id"),
                "created_by": row_data.get("created_by", "system"),
                "created_at": created_at_dt,
            })
            inserted += 1
        
        print(f"Inserted {inserted} new validation run plan versions")


async def seed_validation_run_items(engine) -> None:
    """Seed validation run items (failure records) from CSV."""
    csv_path = MOCK_DIR / "validation-run-items.csv"
    print(f"\n=== Seeding Validation Run Items (Failure Records) ===")
    print(f"Loading {csv_path}...")
    
    data = load_csv_data(str(csv_path))
    print(f"Found {len(data)} validation run items")
    
    failed_count = sum(1 for item in data if item.get("valid") == "false")
    print(f"  - {failed_count} have failures (valid=false)")
    
    with engine.begin() as conn:
        inserted = 0
        for row_data in data:
            item_id = row_data.get("id")
            if not item_id:
                continue
            
            # Check if already exists
            result = conn.execute(
                text("SELECT id FROM validation_run_items WHERE id = :id"),
                {"id": item_id}
            )
            if result.fetchone():
                continue
            
            # Load JSON files if they exist
            diagnostics_path = row_data.get("diagnostics", "")
            diagnostics_json = load_json_file(diagnostics_path)
            
            conflicts_path = row_data.get("conflicts", "")
            conflicts_json = load_json_file(conflicts_path)
            
            # Insert
            conn.execute(text("""
                INSERT INTO validation_run_items (
                    id, run_id, rule_id, rule_name, version_number, valid,
                    errors, warnings, diagnostics, conflicts
                ) VALUES (
                    :id, :run_id, :rule_id, :rule_name, :version_number, :valid,
                    :errors, :warnings, :diagnostics, :conflicts
                )
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": item_id,
                "run_id": row_data.get("run_id", ""),
                "rule_id": row_data.get("rule_id", ""),
                "rule_name": row_data.get("rule_name", ""),
                "version_number": int(row_data.get("version_number", 1)),
                "valid": row_data.get("valid") == "true",
                "errors": int(row_data.get("errors", 0)),
                "warnings": int(row_data.get("warnings", 0)),
                "diagnostics": json.dumps(diagnostics_json) if diagnostics_json else None,
                "conflicts": json.dumps(conflicts_json) if conflicts_json else None,
            })
            inserted += 1
        
        print(f"Inserted {inserted} validation run items")


async def query_failed_items(engine) -> None:
    """Query and display failed validation run items."""
    print(f"\n=== Querying Failed Items ===")
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, run_id, rule_id, rule_name, valid, errors, warnings, diagnostics
            FROM validation_run_items
            WHERE valid = false
            ORDER BY id
        """))
        
        failed_items = result.fetchall()
        
        if not failed_items:
            print("No failed validation items found!")
            return
        
        print(f"\nFound {len(failed_items)} failed validation run items:")
        print("-" * 80)
        
        for item in failed_items:
            print(f"\n  Item ID: {item.id}")
            print(f"  Rule: {item.rule_name} ({item.rule_id})")
            print(f"  Errors: {item.errors}, Warnings: {item.warnings}")
            print(f"  Run ID: {item.run_id}")
            if item.diagnostics:
                print(f"  Diagnostics: {item.diagnostics[:200]}..." if len(str(item.diagnostics)) > 200 else f"  Diagnostics: {item.diagnostics}")


async def main():
    """Main entry point."""
    print("=" * 80)
    print("Quick Seed Script for DQ Plan Validation Data")
    print("=" * 80)
    print(f"Database URL: {DB_URL}")
    print("-" * 80)
    
    # Create engine
    engine = create_engine(DB_URL, echo=False)
    
    try:
        # Seed data
        await seed_validation_run_plans(engine)
        await seed_validation_run_plan_versions(engine)
        await seed_validation_run_items(engine)
        
        # Query failures
        await query_failed_items(engine)
        
        # Summary
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM validation_run_plans"))
            plan_count = result.scalar()
            
            result = conn.execute(text("SELECT COUNT(*) FROM validation_run_plan_versions"))
            version_count = result.scalar()
            
            result = conn.execute(text("SELECT COUNT(*) FROM validation_run_items"))
            item_count = result.scalar()
            
            result = conn.execute(text("SELECT COUNT(*) FROM validation_run_items WHERE valid = false"))
            failed_count = result.scalar()
        
        print(f"\n{'=' * 80}")
        print("SEEDING COMPLETE - Summary:")
        print(f"  - Validation Run Plans: {plan_count}")
        print(f"  - Validation Run Plan Versions: {version_count}")
        print(f"  - Validation Run Items: {item_count}")
        print(f"  - Failed Items: {failed_count}")
        print(f"{'=' * 80}")
        
    except Exception as e:
        print(f"\nError: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
