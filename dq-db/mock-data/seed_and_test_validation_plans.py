#!/usr/bin/env python3
"""
Seed mock validation run plans into PostgreSQL and execute them to check failure records.
"""

import asyncio
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "dq-api" / "fastapi"))

from app.core.config import Settings
from app.infrastructure.orm.session import session_scope
from app.infrastructure.orm.models import (
    ValidationRunPlanRow,
    ValidationRunPlanVersionRow,
    ValidationRunRow,
    ValidationRunItemRow,
)


def load_csv_data(csv_path: str) -> list[dict[str, Any]]:
    """Load CSV data into list of dicts."""
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def get_database_url() -> str:
    """Get database URL from environment or default."""
    db_url = os.getenv("DATABASE_URL", os.getenv("POSTGRES_URL"))
    if not db_url:
        # Default for local dev
        db_url = "postgresql://postgres:postgres@localhost:5432/dq_made_easy"
    return db_url


async def seed_validation_run_plans(database_url: str, csv_path: str) -> None:
    """Seed validation run plans from CSV into PostgreSQL."""
    print(f"Loading CSV from {csv_path}...")
    data = load_csv_data(csv_path)
    
    print(f"Found {len(data)} validation run plans to seed...")
    
    with session_scope(database_url) as session:
        inserted = 0
        for row_data in data:
            plan_id = row_data.get("id")
            if not plan_id:
                continue
            
            # Check if already exists
            existing = session.get(ValidationRunPlanRow, plan_id)
            if existing:
                print(f"  Skipping existing plan: {plan_id}")
                continue
            
            # Create new row
            now = datetime.now()
            created_at = row_data.get("created_at", now.isoformat())
            updated_at = row_data.get("updated_at", now.isoformat())
            
            scope_selector_path = row_data.get("scope_selector_json", "")
            
            # Try to load JSON from file if it's a path
            scope_selector_json = None
            if scope_selector_path and scope_selector_path.endswith("/scope_selector.json"):
                full_path = os.path.join(os.path.dirname(csv_path), scope_selector_path)
                if os.path.exists(full_path):
                    import json
                    with open(full_path, "r") as f:
                        scope_selector_json = json.load(f)
            
            row = ValidationRunPlanRow(
                id=plan_id,
                business_key=row_data.get("business_key", ""),
                workspace_id=row_data.get("workspace_id", ""),
                scope_selector_json=scope_selector_json,
                planning_mode=row_data.get("planning_mode", "single_suite"),
                current_active_version_id=row_data.get("current_active_version_id"),
                status=row_data.get("status", "draft"),
                created_by=row_data.get("created_by", "system"),
                created_at=datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else now,
                updated_at=datetime.fromisoformat(updated_at.replace("Z", "+00:00")) if updated_at else now,
                activated_by=row_data.get("activated_by"),
                activated_at=datetime.fromisoformat(row_data.get("activated_at", "").replace("Z", "+00:00")) if row_data.get("activated_at") else None,
                last_dispatched_run_id=row_data.get("last_dispatched_run_id"),
            )
            
            session.add(row)
            inserted += 1
        
        session.commit()
        print(f"Seeded {inserted} validation run plans")


async def seed_validation_run_plan_versions(database_url: str, csv_path: str) -> None:
    """Seed validation run plan versions from CSV into PostgreSQL."""
    print(f"\nLoading CSV from {csv_path}...")
    data = load_csv_data(csv_path)
    
    print(f"Found {len(data)} validation run plan versions to seed...")
    
    with session_scope(database_url) as session:
        inserted = 0
        for row_data in data:
            version_id = row_data.get("id")
            if not version_id:
                continue
            
            # Check if already exists
            existing = session.get(ValidationRunPlanVersionRow, version_id)
            if existing:
                print(f"  Skipping existing version: {version_id}")
                continue
            
            # Create new row
            now = datetime.now()
            created_at = row_data.get("created_at", now.isoformat())
            effective_from = row_data.get("effective_from")
            
            row = ValidationRunPlanVersionRow(
                id=version_id,
                run_plan_id=row_data.get("run_plan_id", ""),
                validation_artifact_selection_json={},  # Would load from file
                artifact_id=row_data.get("artifact_id"),
                artifact_version=int(row_data.get("artifact_version", 1)),
                governance_state=row_data.get("governance_state", "draft"),
                validation_status=row_data.get("validation_status", "not_requested"),
                review_status=row_data.get("review_status", "pending"),
                effective_from=datetime.fromisoformat(effective_from.replace("Z", "+00:00")) if effective_from else None,
                supersedes_version_id=row_data.get("supersedes_version_id"),
                created_by=row_data.get("created_by", "system"),
                created_at=datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else now,
            )
            
            session.add(row)
            inserted += 1
        
        session.commit()
        print(f"Seeded {inserted} validation run plan versions")


async def seed_validation_run_items(database_url: str, csv_path: str) -> None:
    """Seed validation run items (failure records) from CSV into PostgreSQL."""
    print(f"\nLoading CSV from {csv_path}...")
    data = load_csv_data(csv_path)
    
    print(f"Found {len(data)} validation run items to seed...")
    
    failed_items = [item for item in data if item.get("valid") == "false"]
    print(f"  - {len(failed_items)} have failures (valid=false)")
    
    with session_scope(database_url) as session:
        inserted = 0
        for row_data in data:
            item_id = row_data.get("id")
            if not item_id:
                continue
            
            # Check if already exists
            existing = session.get(ValidationRunItemRow, item_id)
            if existing:
                continue
            
            # Create new row
            now = datetime.now()
            
            # Load diagnostics JSON if path exists
            diagnostics_path = row_data.get("diagnostics", "")
            diagnostics_json = {}
            if diagnostics_path and os.path.exists(diagnostics_path):
                import json
                with open(diagnostics_path, "r") as f:
                    diagnostics_json = json.load(f)
            
            conflicts_path = row_data.get("conflicts", "")
            conflicts_json = {}
            if conflicts_path and os.path.exists(conflicts_path):
                import json
                with open(conflicts_path, "r") as f:
                    conflicts_json = json.load(f)
            
            row = ValidationRunItemRow(
                id=item_id,
                run_id=row_data.get("run_id", ""),
                rule_id=row_data.get("rule_id", ""),
                rule_name=row_data.get("rule_name", ""),
                version_number=int(row_data.get("version_number", 1)),
                valid=row_data.get("valid") == "true",
                errors=int(row_data.get("errors", 0)),
                warnings=int(row_data.get("warnings", 0)),
                diagnostics_json=diagnostics_json,
                conflicts_json=conflicts_json,
                created_at=now,
                updated_at=now,
            )
            
            session.add(row)
            inserted += 1
        
        session.commit()
        print(f"Seeded {inserted} validation run items")


async def query_failed_items(database_url: str, rule_id: str | None = None) -> list[dict[str, Any]]:
    """Query failed validation run items from PostgreSQL."""
    with session_scope(database_url) as session:
        stmt = ValidationRunItemRow.__table__.select().where(
            ValidationRunItemRow.valid == False
        )
        
        if rule_id:
            stmt = stmt.where(ValidationRunItemRow.rule_id == rule_id)
        
        rows = session.execute(stmt).fetchall()
        
        failed_items = []
        for row in rows:
            item = dict(row._mapping)
            failed_items.append({
                "id": item["id"],
                "run_id": item["run_id"],
                "rule_id": item["rule_id"],
                "rule_name": item["rule_name"],
                "errors": item["errors"],
                "warnings": item["warnings"],
                "diagnostics": item["diagnostics_json"],
                "conflicts": item["conflicts_json"],
            })
        
        return failed_items


async def main():
    """Main entry point."""
    database_url = get_database_url()
    print(f"Database URL: {database_url}")
    print("-" * 60)
    
    # Change to mock-data directory
    mock_data_dir = Path(__file__).parent
    os.chdir(mock_data_dir)
    
    # Step 1: Seed validation run plans
    print("\n=== Step 1: Seeding Validation Run Plans ===")
    await seed_validation_run_plans(database_url, "validation-run-plans.csv")
    
    # Step 2: Seed validation run plan versions
    print("\n=== Step 2: Seeding Validation Run Plan Versions ===")
    await seed_validation_run_plan_versions(database_url, "validation-run-plan-versions.csv")
    
    # Step 3: Seed validation run items (failure records)
    print("\n=== Step 3: Seeding Validation Run Items (Failure Records) ===")
    await seed_validation_run_items(database_url, "validation-run-items.csv")
    
    # Step 4: Query failed items
    print("\n=== Step 4: Querying Failed Items ===")
    failed_items = await query_failed_items(database_url)
    
    print(f"\nFound {len(failed_items)} failed validation run items:")
    print("-" * 60)
    
    for item in failed_items:
        print(f"\n  Item ID: {item['id']}")
        print(f"  Rule: {item['rule_name']} ({item['rule_id']})")
        print(f"  Errors: {item['errors']}, Warnings: {item['warnings']}")
        print(f"  Run ID: {item['run_id']}")
        if item["diagnostics"]:
            print(f"  Diagnostics: {item['diagnostics']}")
    
    # Step 5: Query by specific rules that had failures
    print("\n=== Step 5: Detailed Analysis ===")
    
    # Find unique rule IDs with failures
    rule_ids = set(item["rule_id"] for item in failed_items)
    print(f"\nRules with failures ({len(rule_ids)} unique rules):")
    
    for rule_id in rule_ids:
        rule_failed = await query_failed_items(database_url, rule_id)
        rule = next((r for r in failed_items if r["rule_id"] == rule_id), None)
        if rule:
            print(f"\n  Rule: {rule['rule_name']}")
            print(f"    - {len(rule_failed)} failed validations")
            print(f"    - Total errors: {sum(item['errors'] for item in rule_failed)}")


if __name__ == "__main__":
    asyncio.run(main())
