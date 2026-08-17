#!/usr/bin/env bash
# scripts/supporting/cluster_helpers.sh
# Shared helpers for Kind/K8s validation scripts.
#
# Usage:
#   source scripts/supporting/cluster_helpers.sh
#   port_forward_svc dq-api 8080  # forwards svc/dq-api:80 -> localhost:8080
#   cleanup_port_forwards        # kills all background port-forwards

set -euo pipefail

# Track port-forward PIDs for cleanup
declare -a _PF_PIDS=() 2>/dev/null || true

_cleanup_one() {
  local pid="$1"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
}

cleanup_port_forwards() {
  local pid
  for pid in "${_PF_PIDS[@]+"${_PF_PIDS[@]}"}"; do
    _cleanup_one "$pid"
  done
  _PF_PIDS=()
}

# Ensure cleanup on exit
_trap_set=false
_setup_trap() {
  if ! $_trap_set; then
    trap cleanup_port_forwards EXIT
    _trap_set=true
  fi
}

# port_forward_svc <service> <port> [<namespace>] [<local_port>]
# Starts kubectl port-forward in background. Returns nothing on success.
# Example: port_forward_svc dq-api 8080 dq-dev
port_forward_svc() {
  local service="$1"
  local port="$2"
  local namespace="${3:-dq-dev}"
  local local_port="${4:-$port}"

  _setup_trap

  if ! command -v kubectl >/dev/null 2>&1; then
    echo "[cluster_helpers] ERROR: kubectl not found" >&2
    return 1
  fi

  # Check service exists
  if ! kubectl get svc "$service" -n "$namespace" >/dev/null 2>&1; then
    echo "[cluster_helpers] ERROR: service $service not found in $namespace" >&2
    return 1
  fi

  kubectl port-forward "svc/$service" "$local_port:$port" -n "$namespace" >/dev/null 2>&1 &
  local pid=$!
  _PF_PIDS+=("$pid")

  # Wait for tunnel (up to 10s)
  local attempts=0
  while [ $attempts -lt 20 ]; do
    if bash -c "echo >/dev/tcp/127.0.0.1/$local_port" 2>/dev/null; then
      return 0
    fi
    sleep 0.5
    attempts=$((attempts + 1))
  done

  echo "[cluster_helpers] WARNING: port-forward $service:$port -> localhost:$local_port may not be ready" >&2
  return 0
}

# port_forward_pod <label_selector> <port> [<namespace>] [<local_port>]
# Starts kubectl port-forward to a pod matching the label.
port_forward_pod() {
  local label="$1"
  local port="$2"
  local namespace="${3:-dq-dev}"
  local local_port="${4:-$port}"

  _setup_trap

  local pod
  pod="$(kubectl get pods -n "$namespace" -l "$label" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)"
  if [ -z "$pod" ]; then
    echo "[cluster_helpers] ERROR: no pod found with label $label in $namespace" >&2
    return 1
  fi

  kubectl port-forward "$pod" "$local_port:$port" -n "$namespace" >/dev/null 2>&1 &
  local pid=$!
  _PF_PIDS+=("$pid")

  local attempts=0
  while [ $attempts -lt 20 ]; do
    if bash -c "echo >/dev/tcp/127.0.0.1/$local_port" 2>/dev/null; then
      return 0
    fi
    sleep 0.5
    attempts=$((attempts + 1))
  done

  echo "[cluster_helpers] WARNING: port-forward $pod:$port -> localhost:$local_port may not be ready" >&2
  return 0
}

# wait_for_svc_ready <service> <namespace> [<timeout>]
# Waits for a deployment to have ready replicas.
wait_for_svc_ready() {
  local service="$1"
  local namespace="${2:-dq-dev}"
  local timeout="${3:-120}"

  if ! command -v kubectl >/dev/null 2>&1; then
    echo "[cluster_helpers] ERROR: kubectl not found" >&2
    return 1
  fi

  kubectl wait --for=condition=available "deploy/$service" -n "$namespace" --timeout="${timeout}s" 2>/dev/null
  return $?
}

# get_svc_url <service> [<namespace>]
# Returns the localhost URL for a service (requires port-forward).
get_svc_url() {
  local service="$1"
  local namespace="${2:-dq-dev}"

  # Get the service port
  local port
  port="$(kubectl get svc "$service" -n "$namespace" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null)"
  if [ -z "$port" ]; then
    echo ""
    return 1
  fi

  echo "http://127.0.0.1:$port"
}
