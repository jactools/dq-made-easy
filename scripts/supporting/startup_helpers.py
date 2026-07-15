# Purpose: Python helpers extracted from startup shell scripts.
# What it does:
# - Checks compose container health from JSON ps output and exits non-zero on failures.
# - Probes a PostgreSQL database URL for connectivity.
# Version: 1.0
# Last modified: 2026-07-13

from __future__ import annotations

import json
import os
import sys


def check_compose_containers_health(compose_json: str) -> None:
    """Parse docker compose ps --format json output and exit on failures.

    Exit codes:
      0 — all containers OK or no exited containers found
      1 — container exited with non-zero exit code
      2 — container reported unhealthy
    """
    if not compose_json.strip():
        return

    try:
        items = json.loads(compose_json)
    except json.JSONDecodeError:
        return

    if isinstance(items, dict):
        items = [items]

    for item in items:
        service = item.get("Service") or item.get("Name") or "unknown"
        exit_code = item.get("ExitCode")
        health = str(item.get("Health") or "").lower()
        status = str(item.get("Status") or "").lower()

        if exit_code is None:
            continue

        try:
            exit_code_int = int(exit_code)
        except (TypeError, ValueError):
            continue

        if exit_code_int != 0:
            print(
                f"startup_monitor: container '{service}' failed with exit code {exit_code_int}",
                file=sys.stderr,
            )
            sys.exit(1)

        if health == "unhealthy" or ("unhealthy" in status and "healthy" not in status):
            print(
                f"startup_monitor: container '{service}' reported unhealthy status",
                file=sys.stderr,
            )
            sys.exit(2)


def check_database_ready(database_url: str) -> None:
    """Probe a PostgreSQL database URL for connectivity.

    Exits 1 if the connection fails, 0 on success.
    """
    import psycopg  # type: ignore

    conn = psycopg.connect(database_url)
    conn.close()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: startup_helpers.py <command> [args...]", file=sys.stderr)
        sys.exit(2)

    command = sys.argv[1]

    if command == "check-containers":
        if len(sys.argv) >= 3:
            compose_json = sys.argv[2]
        else:
            compose_json = sys.stdin.read()
        check_compose_containers_health(compose_json)

    elif command == "check-database":
        database_url = os.environ.get("DQ_DB_INTERNAL_URL")
        if not database_url:
            print("Error: DQ_DB_INTERNAL_URL is required", file=sys.stderr)
            sys.exit(1)
        try:
            check_database_ready(database_url)
        except Exception:
            sys.exit(1)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
