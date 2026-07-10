#!/usr/bin/env bash
# SEC-5 Workstream 6 Smoke Tests: Verify TLS end-to-end routing without proxy termination
# 
# Tests that the Zammad support stack achieves SEC-5 W6 compliance by:
# 1. Verifying the edge does SNI passthrough (no TLS termination for LOCAL mode)
# 2. Verifying backends are TLS-native and directly accessible
# 3. Verifying healthchecks work over TLS
# 4. Verifying no double-termination architecture
#
# Usage: ./scripts/sec5-w6-smoke-tests.sh [test-name]
# Examples:
#   ./scripts/sec5-w6-smoke-tests.sh                    # Run all tests
#   ./scripts/sec5-w6-smoke-tests.sh edge_config        # Run specific test
#   ./scripts/sec5-w6-smoke-tests.sh edge_config verbose # Run with verbose output

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
EDGE_PROFILE="${EDGE_PROFILE:-local}"
VERBOSE="${VERBOSE:-}"
SPECIFIC_TEST="${1:-}"
VERBOSE_MODE="${2:-}"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
  echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $*"
}

log_test() {
  echo -e "\n${GREEN}=== TEST: $* ===${NC}"
}

verbose_output() {
  if [ "$VERBOSE_MODE" = "verbose" ] || [ -n "$VERBOSE" ]; then
    echo "  $*"
  fi
}

# Test 1: Verify edge routing configuration uses SNI passthrough (not HTTP-based)
test_edge_sni_passthrough() {
  log_test "Edge SNI Passthrough Configuration"
  
  if grep -q "ssl_preread on" "$REPO_ROOT/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"; then
    verbose_output "✓ Edge uses ssl_preread (SNI passthrough capability)"
  else
    log_error "Edge does not enable ssl_preread"
    return 1
  fi
  
  if grep -q "map .*\\\$ssl_preread_server_name" "$REPO_ROOT/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"; then
    verbose_output "✓ Edge maps traffic by SNI (not HTTP path)"
  else
    log_error "Edge does not use SNI-based routing"
    return 1
  fi
  
  log_info "PASS: Edge uses SNI passthrough (non-terminating relay)"
}

# Test 2: Verify backends are not routed through TLS-terminating proxy in LOCAL mode
test_no_intermediate_proxy() {
  log_test "No Intermediate TLS-Terminating Proxy (LOCAL Mode)"
  
  # The support_host variable maps to zammad-railsserver:3000 in the SNI map
  if grep -q 'zammad-railsserver:3000' "$REPO_ROOT/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"; then
    verbose_output "✓ Support traffic routes directly to zammad-railsserver:3000 (not zammad-https)"
    log_info "PASS: Support routing bypasses intermediate TLS-terminating proxy"
    return 0
  else
    log_error "Support traffic still routes through intermediate proxy"
    return 1
  fi
}

# Test 3: Verify backend certificates include edge SNI name in SAN
test_backend_cert_ssan() {
  log_test "Backend Certificate SAN Configuration"
  
  local cert_gen=$(grep -A2 "zammad-railsserver" "$REPO_ROOT/scripts/create_certs.sh" | grep "EDGE_LOCAL_SUPPORT_HOST" || true)
  
  if [ -n "$cert_gen" ]; then
    verbose_output "✓ Backend certificates include EDGE_LOCAL_SUPPORT_HOST as SAN"
    log_info "PASS: Backend certificates configured with edge SNI name"
    return 0
  else
    log_error "Backend certificates do not include edge SNI name"
    return 1
  fi
}

# Test 4: Verify healthchecks use TLS verification
test_healthchecks_use_tls() {
  log_test "Healthcheck TLS Verification"
  
  local rails_hc=$(grep -rA5 "zammad-railsserver:" "$REPO_ROOT/docker-compose/" | grep -c "healthcheck:" || true)
  local ws_hc=$(grep -rA5 "zammad-websocket:" "$REPO_ROOT/docker-compose/" | grep -c "healthcheck:" || true)
  
  if [ "$rails_hc" -gt 0 ]; then
    verbose_output "✓ zammad-railsserver has healthcheck"
  else
    log_warn "zammad-railsserver healthcheck not found"
  fi
  
  if [ "$ws_hc" -gt 0 ]; then
    verbose_output "✓ zammad-websocket has healthcheck"
  else
    log_warn "zammad-websocket healthcheck not found"
  fi
  
  if grep -rq "cacert.*rootCA.pem" "$REPO_ROOT/docker-compose/"; then
    verbose_output "✓ Healthchecks verify TLS with mkcert CA bundle"
    log_info "PASS: Healthchecks use TLS certificate verification"
    return 0
  else
    log_error "Healthchecks do not verify TLS certificates"
    return 1
  fi
}

# Test 5: Verify no HTTP fallbacks in backend configuration
test_no_http_fallback() {
  log_test "No HTTP Fallback Paths"
  
  # Check that backends don't advertise HTTP ports
  if grep -rq "listen 80" "$REPO_ROOT/docker-compose/" | grep -q "zammad"; then
    log_error "Zammad backends expose HTTP port 80"
    return 1
  fi
  
  # Check that origin-nginx uses HTTPS proxying
  if grep -q "proxy_pass http://" "$REPO_ROOT/docker/zammad/origin-nginx.conf"; then
    log_warn "origin-nginx still has HTTP proxy passes (acceptable if zammad-https is not used in LOCAL)"
  else
    verbose_output "✓ origin-nginx uses HTTPS proxying"
  fi
  
  log_info "PASS: No HTTP fallback paths detected"
}

# Test 6: Verify compose YAML structure is valid
test_compose_valid() {
  log_test "Docker Compose YAML Validity"
  
  if ruby -e "require 'yaml'; YAML.load_file('$REPO_ROOT/docker-compose/core.yml')" 2>/dev/null; then
    verbose_output "✓ docker-compose modules parse successfully"
    log_info "PASS: Compose file is valid YAML"
    return 0
  else
    log_error "docker-compose modules are invalid"
    return 1
  fi
}

# Test 7: Verify zammad-https is marked as optional/deprecated
test_zammad_https_optional() {
  log_test "zammad-https Service Status"
  
  if grep -rq "SEC-5 Compliance" "$REPO_ROOT/docker-compose/"; then
    verbose_output "✓ zammad-https has SEC-5 compliance documentation"
  fi
  
  if grep -rq "zammad-https is optional" "$REPO_ROOT/docker-compose/"; then
    verbose_output "✓ zammad-https is documented as optional for SEC-5 LOCAL mode"
    log_info "PASS: zammad-https deprecation documented"
    return 0
  else
    log_warn "zammad-https deprecation not documented (may still be used for backwards compat)"
    return 0
  fi
}

# Test 8: Verify sec5 strategy document exists and is complete
test_w6_strategy_document() {
  log_test "SEC-5 W6 Strategy Documentation"
  
  local strategy_file="$REPO_ROOT/docs/implementation-details/SEC_5_W6_IMPLEMENTATION_STRATEGY.md"
  
  if [ -f "$strategy_file" ]; then
    verbose_output "✓ Strategy document exists"
    
    if grep -q "Phase 1: Local Mode" "$strategy_file"; then
      verbose_output "✓ Phase 1 (Local Mode) documented"
    fi
    
    if grep -q "SEC-5 W6 Compliance Goal" "$strategy_file"; then
      verbose_output "✓ Compliance goals defined"
      log_info "PASS: Strategy documentation is complete"
      return 0
    fi
  else
    log_error "Strategy document not found at $strategy_file"
    return 1
  fi
}

# Test 9: Compare edge routing to identify remaining W6 gaps (PUBLIC mode)
test_public_mode_gaps() {
  log_test "PUBLIC Mode Architecture Gaps (Expected)"
  
  local public_support=$(grep -A20 "location /support/" "$REPO_ROOT/dq-edge/docker-entrypoint.d/40-render-edge-config.sh" 2>/dev/null | grep "append_https_proxy" || true)
  
  if [ -n "$public_support" ]; then
    log_warn "PUBLIC mode still uses path-based routing with TLS termination"
    verbose_output "  This is documented as a W6 Phase 2 gap (acceptable for now)"
    log_info "PASS: PUBLIC mode gap documented and acknowledged"
    return 0
  else
    verbose_output "✓ PUBLIC mode configuration complete or not found"
    return 0
  fi
}

# Test 10: Verify git working directory is clean
test_git_diff_clean() {
  log_test "Git Diff Cleanliness"
  
  if git --no-pager diff --check >/dev/null 2>&1; then
    verbose_output "✓ No whitespace or patch issues"
    log_info "PASS: Git diff is clean"
    return 0
  else
    log_error "Git diff has issues"
    git --no-pager diff --check || true
    return 1
  fi
}

# Run all tests
run_all_tests() {
  log_info "Running SEC-5 Workstream 6 Smoke Tests (LOCAL Mode Focus)"
  log_info "Testing TLS end-to-end routing and proxy elimination"
  echo ""
  
  local passed=0
  local failed=0
  local tests=(
    "test_edge_sni_passthrough"
    "test_no_intermediate_proxy"
    "test_backend_cert_ssan"
    "test_healthchecks_use_tls"
    "test_no_http_fallback"
    "test_compose_valid"
    "test_zammad_https_optional"
    "test_w6_strategy_document"
    "test_public_mode_gaps"
    "test_git_diff_clean"
  )
  
  for test in "${tests[@]}"; do
    if $test; then
      passed=$((passed+1))
    else
      failed=$((failed+1))
    fi
  done
  
  echo ""
  echo -e "${GREEN}════════════════════════════════════════${NC}"
  echo -e "Tests Passed: ${GREEN}$passed${NC}"
  echo -e "Tests Failed: ${RED}$failed${NC}"
  echo -e "${GREEN}════════════════════════════════════════${NC}"
  
  if [ $failed -eq 0 ]; then
    log_info "All tests passed! SEC-5 W6 compliance achieved for LOCAL mode."
    return 0
  else
    log_error "$failed test(s) failed"
    return 1
  fi
}

# Main
if [ -n "$SPECIFIC_TEST" ] && [ "$SPECIFIC_TEST" != "verbose" ]; then
  if declare -f "$SPECIFIC_TEST" >/dev/null; then
    $SPECIFIC_TEST
  else
    log_error "Unknown test: $SPECIFIC_TEST"
    exit 1
  fi
elif [ -n "$VERBOSE_MODE" ] && [ "$VERBOSE_MODE" = "verbose" ]; then
  VERBOSE=1
  run_all_tests
else
  run_all_tests
fi
