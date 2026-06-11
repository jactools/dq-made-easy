#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Local Postgres + Seeds setup (macOS) =="

if ! command -v psql >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Please install Homebrew first: https://brew.sh/"
    exit 1
  fi
  echo "Installing postgresql via Homebrew..."
  brew install postgresql
fi

SEED=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED=true; shift ;;
    -h|--help) echo "Usage: $0 [--seed]"; exit 0 ;;
    *) echo "Unknown arg: $1"; echo "Usage: $0 [--seed]"; exit 1 ;;
  esac
done

echo "Starting Postgres service (brew services)..."
brew services start postgresql || true

echo "Waiting for Postgres to become available..."
for i in {1..60}; do
  if psql -c '\l' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "Ensuring 'postgres' user has password 'postgres' (local dev only)..."
# best-effort: this may fail under certain local auth setups but it's fine for dev
psql -v ON_ERROR_STOP=1 -U postgres -c "ALTER USER postgres WITH PASSWORD 'postgres';" || true

# Ensure the 'dq' database exists before optional seeding
if command -v psql >/dev/null 2>&1; then
  if ! psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='dq'" | grep -q 1; then
    echo "Creating database 'dq'..."
    createdb -U postgres dq || psql -U postgres -c "CREATE DATABASE dq;" || true
  else
    echo "Database 'dq' exists"
  fi
else
  echo "psql not found; skipping database existence check"
fi

if [ "$SEED" = true ]; then
  SEED_SCRIPT="$ROOT/../scripts/seed_local_postgres.sh"
  if [ -f "$SEED_SCRIPT" ]; then
    echo "Invoking seed script: $SEED_SCRIPT"
    bash "$SEED_SCRIPT" || { echo "Seed script failed"; exit 1; }
  else
    echo "Seed script not found: $SEED_SCRIPT"
    exit 1
  fi
else
  echo
  echo "Setup complete. To seed the DB run: ./scripts/seed_local_postgres.sh"
  echo "To use this DB for the app, export:" 
  echo "  export DQ_DB_LOCAL_URL='postgresql://postgres:postgres@localhost:5432/dq'"
  echo "Then start the stack locally with: ./scripts/start_local.sh"
fi

exit 0
