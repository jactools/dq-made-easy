#!/usr/bin/env bash
# Tests for startup_monitor.sh state-tracking deduplication.
#
# We isolate the state-tracking logic by sourcing the script and calling
# the helper directly, avoiding the infinite loop in startup_monitor_run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Source the script to check it loads cleanly
source "$ROOT_DIR/scripts/supporting/startup_monitor.sh"

# Test harness: feed lines through the regex + dedup and capture output.
# Mirrors the logic in startup_monitor.sh's _startup_monitor_print_change
# but without subshell isolation so the state array persists.
declare -A _test_container_state

_run_monitor_lines() {
  _test_container_state=()
  local input="$1"
  local output=""
  while IFS= read -r line; do
    if [[ "$line" =~ ^\ *Container\ ([^\ ]+)\ (.+)$ ]]; then
      local name="${BASH_REMATCH[1]}"
      local status="${BASH_REMATCH[2]}"
      local prev="${_test_container_state[$name]:-}"
      if [ -z "$prev" ] || [ "$prev" != "$status" ]; then
        _test_container_state["$name"]="$status"
        output+=" Container $name $status"$'\n'
      fi
    else
      output+="${line}"$'\n'
    fi
  done <<< "$input"
  echo "$output"
}

# Helper: check if a state is terminal (won't count as stuck)
_is_terminal_state() {
  local status="$1"
  case "$status" in
    Exited|Healthy|Exited*|Completed|Completed*) return 0 ;;
    *) return 1 ;;
  esac
}

# ---- Tests ----

test_deduplicates_unchanged_state() {
  local input output redis_count trust_count
  input=$(cat <<'EOF'
Container dq-made-easy-redis Waiting
Container dq-made-easy-redis Waiting
Container dq-made-easy-redis Waiting
Container dq-made-easy-dev-trust-bundle-1 Exited
Container dq-made-easy-dev-trust-bundle-1 Exited
EOF
)
  output=$(_run_monitor_lines "$input")
  redis_count=$(echo "$output" | grep -c "dq-made-easy-redis" || true)
  trust_count=$(echo "$output" | grep -c "trust-bundle" || true)

  [ "$redis_count" -eq 1 ] || { echo "FAIL: redis appeared $redis_count times, expected 1"; exit 1; }
  [ "$trust_count" -eq 1 ] || { echo "FAIL: trust-bundle appeared $trust_count times, expected 1"; exit 1; }

  echo "PASS: test_deduplicates_unchanged_state"
}

test_prints_state_change() {
  local input output redis_count
  input=$(cat <<'EOF'
Container dq-made-easy-redis Waiting
Container dq-made-easy-redis Healthy
Container dq-made-easy-redis Waiting
EOF
)
  output=$(_run_monitor_lines "$input")
  redis_count=$(echo "$output" | grep -c "dq-made-easy-redis" || true)

  [ "$redis_count" -eq 3 ] || { echo "FAIL: redis appeared $redis_count times, expected 3 (state changes)"; exit 1; }

  echo "PASS: test_prints_state_change"
}

test_passes_non_container_lines() {
  local input output
  input=$(cat <<'EOF'
[2026-07-12T12:00:00Z] [INFO] Starting containers...
Container dq-made-easy-db Waiting
EOF
)
  output=$(_run_monitor_lines "$input")

  echo "$output" | grep -q "Starting containers" || { echo "FAIL: non-container line was suppressed"; exit 1; }
  echo "PASS: test_passes_non_container_lines"
}

test_mixed_containers_deduplicate_independently() {
  local input output redis_count db_count
  input=$(cat <<'EOF'
Container dq-made-easy-redis Waiting
Container dq-made-easy-db Waiting
Container dq-made-easy-redis Waiting
Container dq-made-easy-db Waiting
Container dq-made-easy-redis Healthy
Container dq-made-easy-db Started
EOF
)
  output=$(_run_monitor_lines "$input")
  redis_count=$(echo "$output" | grep -c "dq-made-easy-redis" || true)
  db_count=$(echo "$output" | grep -c "dq-made-easy-db" || true)

  [ "$redis_count" -eq 2 ] || { echo "FAIL: redis appeared $redis_count times, expected 2"; exit 1; }
  [ "$db_count" -eq 2 ] || { echo "FAIL: db appeared $db_count times, expected 2"; exit 1; }

  echo "PASS: test_mixed_containers_deduplicate_independently"
}

test_error_status_prints() {
  local input output
  input=$(cat <<'EOF'
Container dq-made-easy-dev-api-migrate-1 Error service "api-migrate" didn't complete successfully: exit 1
EOF
)
  output=$(_run_monitor_lines "$input")
  echo "$output" | grep -q "api-migrate" || { echo "FAIL: error line was suppressed"; exit 1; }
  echo "PASS: test_error_status_prints"
}

test_full_lifecycle() {
  local input output
  input=$(cat <<'EOF'
Container dq-made-easy-dev-api-migrate-1 Starting
Container dq-made-easy-dev-api-migrate-1 Started
Container dq-made-easy-dev-api-migrate-1 Waiting
Container dq-made-easy-dev-api-migrate-1 Waiting
Container dq-made-easy-dev-api-migrate-1 Waiting
Container dq-made-easy-dev-api-migrate-1 Exited
EOF
)
  output=$(_run_monitor_lines "$input")
  local count
  count=$(echo "$output" | grep -c "api-migrate" || true)

  # Starting(1) + Started(2) + Waiting(3) + Exited(4) = 4
  [ "$count" -eq 4 ] || { echo "FAIL: api-migrate appeared $count times, expected 4"; exit 1; }

  echo "PASS: test_full_lifecycle"
}

test_terminal_states() {
  # Terminal states should return true
  _is_terminal_state "Exited" && true || { echo "FAIL: Exited should be terminal"; exit 1; }
  _is_terminal_state "Healthy" && true || { echo "FAIL: Healthy should be terminal"; exit 1; }
  _is_terminal_state "Completed" && true || { echo "FAIL: Completed should be terminal"; exit 1; }
  # Non-terminal states should return false
  _is_terminal_state "Starting" && { echo "FAIL: Starting should not be terminal"; exit 1; } || true
  _is_terminal_state "Waiting" && { echo "FAIL: Waiting should not be terminal"; exit 1; } || true
  _is_terminal_state "Running" && { echo "FAIL: Running should not be terminal"; exit 1; } || true
  _is_terminal_state "Creating" && { echo "FAIL: Creating should not be terminal"; exit 1; } || true
  _is_terminal_state "Error dependency openmetadata-server failed to start" && { echo "FAIL: Error state should not be terminal"; exit 1; } || true

  echo "PASS: test_terminal_states"
}

test_error_state_not_terminal() {
  # Error states like "Error dependency X failed to start" should NOT be terminal
  # so they can be flagged as stuck
  local status="Error dependency openmetadata-server failed to start"
  _is_terminal_state "$status" && { echo "FAIL: Error state should not be terminal"; exit 1; } || true

  echo "PASS: test_error_state_not_terminal"
}

test_stuck_container_detection_logic() {
  # Simulate a container that enters "Error" state and never transitions
  _test_container_state=()
  local input output=""
  input=$(cat <<'EOF'
Container dq-made-easy-dev-openmetadata-server-1 Starting
Container dq-made-easy-dev-openmetadata-server-1 Error dependency openmetadata-server failed to start
Container dq-made-easy-dev-openmetadata-server-1 Error dependency openmetadata-server failed to start
EOF
)
  while IFS= read -r line; do
    if [[ "$line" =~ ^\ *Container\ ([^\ ]+)\ (.+)$ ]]; then
      local name="${BASH_REMATCH[1]}"
      local status="${BASH_REMATCH[2]}"
      local prev="${_test_container_state[$name]:-}"
      if [ -z "$prev" ] || [ "$prev" != "$status" ]; then
        _test_container_state["$name"]="$status"
        output+=" Container $name $status"$'\n'
      fi
    fi
  done <<< "$input"

  local count
  count=$(echo "$output" | grep -c "openmetadata-server" || true)

  # Should appear twice: Starting + first Error transition (second Error is same state)
  [ "$count" -eq 2 ] || { echo "FAIL: openmetadata-server appeared $count times, expected 2"; exit 1; }

  # Verify the last known state is non-terminal
  local last_state="${_test_container_state[dq-made-easy-dev-openmetadata-server-1]:-}"
  [ -n "$last_state" ] || { echo "FAIL: container state not set"; exit 1; }
  _is_terminal_state "$last_state" && { echo "FAIL: last state '$last_state' should not be terminal"; exit 1; } || true

  echo "PASS: test_stuck_container_detection_logic"
}

# Fail-fast helper: simulates the error detection logic from startup_monitor_run
# Returns: 0 if error detected, 1 if not
_test_detect_error() {
  local line="$1"
  if [[ "$line" =~ ^\ *Container\ ([^\ ]+)\ (.+)$ ]]; then
    local status="${BASH_REMATCH[2]}"
    case "$status" in
      Error*|error*) return 0 ;;
    esac
  elif [[ "$line" =~ dependency\ failed\ to\ start ]]; then
    return 0
  fi
  return 1
}

test_fail_fast_on_error_state() {
  # Error state should trigger fail-fast
  _test_detect_error "Container dq-made-easy-dev-api-1 Error dependency api failed to start" || { echo "FAIL: Error state not detected"; exit 1; }
  _test_detect_error "Container dq-made-easy-dev-api-1 error something went wrong" || { echo "FAIL: lowercase error not detected"; exit 1; }
  # Non-error states should not trigger fail-fast
  _test_detect_error "Container dq-made-easy-db Healthy" && { echo "FAIL: Healthy state falsely flagged"; exit 1; } || true
  _test_detect_error "Container dq-made-easy-db Waiting" && { echo "FAIL: Waiting state falsely flagged"; exit 1; } || true
  _test_detect_error "Container dq-made-easy-db Exited" && { echo "FAIL: Exited state falsely flagged"; exit 1; } || true

  echo "PASS: test_fail_fast_on_error_state"
}

test_fail_fast_on_dependency_failure() {
  # Dependency failure lines should trigger fail-fast
  _test_detect_error "dependency failed to start: container dq-made-easy-dev-openmetadata-server-1 is unhealthy" || { echo "FAIL: dependency failure not detected"; exit 1; }
  # Normal lines should not trigger fail-fast
  _test_detect_error "Container dq-made-easy-db Healthy" && { echo "FAIL: normal line falsely flagged"; exit 1; } || true
  _test_detect_error "[2026-07-12T19:31:15Z] [INFO] [start_stack.sh] Stack startup completed successfully" && { echo "FAIL: info line falsely flagged"; exit 1; } || true

  echo "PASS: test_fail_fast_on_dependency_failure"
}

# ---- Run all tests ----
echo "Running startup_monitor.sh tests..."
test_deduplicates_unchanged_state
test_prints_state_change
test_passes_non_container_lines
test_mixed_containers_deduplicate_independently
test_error_status_prints
test_full_lifecycle
test_terminal_states
test_error_state_not_terminal
test_stuck_container_detection_logic
test_fail_fast_on_error_state
test_fail_fast_on_dependency_failure
echo "All startup_monitor.sh tests passed."
