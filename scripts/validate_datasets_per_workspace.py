#!/usr/bin/env python3
"""
Purpose: Validate that dataset counts per workspace match between database and mock-data CSV.

What it does:
- Reads data-sets.csv mock-data file
- Connects to Postgres database and queries actual dataset counts by workspace
- Compares expected vs actual counts
- Reports mismatches with details
- Exits 0 if all counts match, 1 if any mismatch found

Usage:
  python3 validate_datasets_per_workspace.py [csv_file] [db_host] [db_port] [db_name] [db_user]

Environment variables (used as defaults):
  - DQ_DB_HOST (default: localhost)
  - DQ_DB_PORT (default: 5432)
  - DQ_DB_NAME (default: dq)
  - DB_NAME (alternate for dq db name)
  - DB_USER (default: postgres)
  - POSTGRES_PASSWORD (default: empty)

Version: 1.0
Last modified: 2026-05-31
Changelog:
- 1.0 (2026-05-31): Initial implementation
"""

import csv
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, Tuple

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed. Install with: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)


def load_expected_counts(csv_path: str) -> Dict[str, int]:
    """Read data-sets.csv and count datasets per workspace."""
    counts: Dict[str, int] = {}
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                workspace_id = (row.get('workspace_id') or '').strip()
                if workspace_id and workspace_id != '""':
                    # Handle both quoted and unquoted values
                    workspace_id = workspace_id.strip('"')
                    if workspace_id:
                        counts[workspace_id] = counts.get(workspace_id, 0) + 1
    except FileNotFoundError:
        print(f"ERROR: CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to read CSV file: {e}", file=sys.stderr)
        sys.exit(1)
    
    return counts


def get_actual_counts(
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_password: str = '',
) -> Dict[str, int]:
    """Query database for actual dataset counts per workspace."""
    counts: Dict[str, int] = {}
    
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password if db_password else None,
        )
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT workspace_id, COUNT(*) as count
                FROM data_sets
                WHERE workspace_id IS NOT NULL AND workspace_id != ''
                GROUP BY workspace_id
                ORDER BY workspace_id;
            """)
            
            for row in cur.fetchall():
                workspace_id, count = row
                if workspace_id:
                    counts[workspace_id] = count
        
        conn.close()
    except psycopg2.OperationalError as e:
        print(f"ERROR: Failed to connect to database: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Database query failed: {e}", file=sys.stderr)
        sys.exit(1)
    
    return counts


def validate_and_report(expected: Dict[str, int], actual: Dict[str, int]) -> Tuple[bool, int]:
    """
    Compare expected vs actual counts and report results.
    
    Returns:
        Tuple of (all_match: bool, mismatch_count: int)
    """
    mismatches = 0
    all_workspaces = sorted(set(expected.keys()) | set(actual.keys()))
    
    print("\nDataset Count Validation Results:")
    print("-" * 60)
    
    for ws in all_workspaces:
        exp = expected.get(ws, 0)
        act = actual.get(ws, 0)
        
        if exp != act:
            print(f"✗ MISMATCH workspace_id='{ws}': expected {exp}, got {act}")
            mismatches += 1
        else:
            print(f"✓ workspace_id='{ws}': {exp} datasets")
    
    print("-" * 60)
    
    return mismatches == 0, mismatches


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        'csv_file',
        nargs='?',
        default='dq-db/mock-data/data-sets.csv',
        help='Path to data-sets.csv mock-data file',
    )
    parser.add_argument(
        '--db-host',
        default=os.environ.get('DQ_DB_HOST', 'localhost'),
        help='Database host (default: localhost)',
    )
    parser.add_argument(
        '--db-port',
        type=int,
        default=int(os.environ.get('DQ_DB_PORT', '5432')),
        help='Database port (default: 5432)',
    )
    parser.add_argument(
        '--db-name',
        default=os.environ.get('DB_NAME', os.environ.get('DQ_DB_NAME', 'dq')),
        help='Database name (default: dq)',
    )
    parser.add_argument(
        '--db-user',
        default=os.environ.get('DB_USER', 'postgres'),
        help='Database user (default: postgres)',
    )
    parser.add_argument(
        '--db-password',
        default=os.environ.get('POSTGRES_PASSWORD', ''),
        help='Database password (default: from POSTGRES_PASSWORD env var)',
    )
    
    args = parser.parse_args()
    
    # Verify CSV file exists
    csv_path = Path(args.csv_file).resolve()
    if not csv_path.exists():
        print(f"ERROR: CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)
    
    print("=" * 60)
    print("Validating dataset counts per workspace")
    print("=" * 60)
    print(f"CSV file: {csv_path}")
    print(f"Database: {args.db_user}@{args.db_host}:{args.db_port}/{args.db_name}")
    print()
    
    # Load expected counts from CSV
    print("Reading expected counts from CSV...")
    expected = load_expected_counts(str(csv_path))
    
    print("Expected dataset counts by workspace:")
    for ws in sorted(expected.keys()):
        print(f"  {ws}: {expected[ws]}")
    
    # Query database for actual counts
    print("\nQuerying database for actual counts...")
    actual = get_actual_counts(
        args.db_host,
        args.db_port,
        args.db_name,
        args.db_user,
        args.db_password,
    )
    
    print("Actual dataset counts by workspace:")
    for ws in sorted(actual.keys()):
        print(f"  {ws}: {actual[ws]}")
    
    # Validate
    all_match, mismatch_count = validate_and_report(expected, actual)
    
    if all_match:
        print("\n✓ All workspace dataset counts match!")
        return 0
    else:
        print(f"\n✗ Found {mismatch_count} workspace(s) with mismatched dataset counts")
        return 1


if __name__ == '__main__':
    sys.exit(main())
