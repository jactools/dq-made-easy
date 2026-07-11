#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate Zammad SSO login through the browser by driving the Keycloak button with Playwright.
# What it does:
# - Loads the selected environment and seeded Keycloak credentials.
# - Opens Zammad's login page, clicks "Keycloak", and signs in on the Keycloak-hosted form.
# - Verifies the browser returns to the Zammad dashboard.
# validate: groups=support,auth
# Version: 1.0.0
# Last modified: 2026-07-03

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_zammad_sso_login_playwright.sh"

if ! dq_source_seeded_user_credentials "$@" --quiet; then
  exit 1
fi

SUPPORT_URL="${ZAMMAD_PUBLIC_URL:?ZAMMAD_PUBLIC_URL must be set}"
SSO_ISSUER_URL="${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL must be set to the public Keycloak issuer URL}"
LOGIN_EMAIL="${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set}"
LOGIN_PASSWORD="${KEYCLOAK_JACCLOUD_PASSWORD:?KEYCLOAK_JACCLOUD_PASSWORD must be set}"

SUPPORT_ORIGIN="${SUPPORT_URL%/}"
SSO_ISSUER_ORIGIN="${SSO_ISSUER_URL%/}"
LOGIN_URL="${SUPPORT_ORIGIN}/#login"
AUTH_URL_PREFIX="${SSO_ISSUER_ORIGIN}/protocol/openid-connect/auth"

if [[ "$SUPPORT_ORIGIN" != https://* ]]; then
  error "$my_name" "Support origin must use https:// (got ${SUPPORT_ORIGIN})"
  exit 1
fi

if [[ "$SSO_ISSUER_URL" != https://* ]]; then
  error "$my_name" "SSO_PUBLIC_ISSUER_URL must use https:// (got ${SSO_ISSUER_URL})"
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  error "$my_name" "node is required"
  exit 127
fi

PLAYWRIGHT_MODULE_PATH="$ROOT_DIR/dq-ui/node_modules/playwright/index.mjs"
if [[ ! -f "$PLAYWRIGHT_MODULE_PATH" ]]; then
  error "$my_name" "Playwright module not found at ${PLAYWRIGHT_MODULE_PATH}"
  exit 1
fi

PLAYWRIGHT_BROWSER_EXECUTABLE_PATH="${PLAYWRIGHT_BROWSER_EXECUTABLE_PATH:-${GOOGLE_CHROME_PATH:-}}"
if [[ -z "$PLAYWRIGHT_BROWSER_EXECUTABLE_PATH" ]]; then
  if command -v google-chrome >/dev/null 2>&1; then
    PLAYWRIGHT_BROWSER_EXECUTABLE_PATH="$(command -v google-chrome)"
  elif command -v chromium >/dev/null 2>&1; then
    PLAYWRIGHT_BROWSER_EXECUTABLE_PATH="$(command -v chromium)"
  elif command -v chromium-browser >/dev/null 2>&1; then
    PLAYWRIGHT_BROWSER_EXECUTABLE_PATH="$(command -v chromium-browser)"
  fi
fi

if [[ -z "$PLAYWRIGHT_BROWSER_EXECUTABLE_PATH" ]]; then
  error "$my_name" "No Chromium or Google Chrome executable was found"
  exit 1
fi

PLAYWRIGHT_ARTIFACT_DIR="$(mktemp -d)"

info "$my_name" "=============================================="
info "$my_name" "Zammad SSO Browser Login Validation"
info "$my_name" "=============================================="
info "$my_name" "SUPPORT_ORIGIN=${SUPPORT_ORIGIN}"
info "$my_name" "SSO_PUBLIC_ISSUER_URL=${SSO_ISSUER_URL}"
info "$my_name" "LOGIN_EMAIL=${LOGIN_EMAIL}"
info "$my_name" "PLAYWRIGHT_BROWSER_EXECUTABLE_PATH=${PLAYWRIGHT_BROWSER_EXECUTABLE_PATH}"

export PLAYWRIGHT_MODULE_PATH
export PLAYWRIGHT_BROWSER_EXECUTABLE_PATH
export PLAYWRIGHT_ARTIFACT_DIR
export ZAMMAD_PUBLIC_URL="$SUPPORT_ORIGIN"
export SSO_PUBLIC_ISSUER_URL="$SSO_ISSUER_URL"
export KEYCLOAK_JACCLOUD_USERNAME="$LOGIN_EMAIL"
export KEYCLOAK_JACCLOUD_PASSWORD="$LOGIN_PASSWORD"

cleanup() {
  if [ "${1:-1}" -eq 0 ]; then
    rm -rf "$PLAYWRIGHT_ARTIFACT_DIR"
  else
    info "$my_name" "Playwright failure artifacts kept at ${PLAYWRIGHT_ARTIFACT_DIR}"
  fi
}

trap 'exit_status=$?; cleanup "$exit_status"' EXIT

run_status=0
if node --input-type=module <<'NODE'
import path from 'node:path';

const playwrightModulePath = process.env.PLAYWRIGHT_MODULE_PATH;
const browserExecutablePath = process.env.PLAYWRIGHT_BROWSER_EXECUTABLE_PATH;
const artifactDir = process.env.PLAYWRIGHT_ARTIFACT_DIR;
const supportOrigin = process.env.ZAMMAD_PUBLIC_URL.replace(/\/+$/, '');
const ssoIssuerOrigin = process.env.SSO_PUBLIC_ISSUER_URL.replace(/\/+$/, '');
const loginEmail = process.env.KEYCLOAK_JACCLOUD_USERNAME;
const loginPassword = process.env.KEYCLOAK_JACCLOUD_PASSWORD;

const { chromium } = await import(playwrightModulePath);

const loginUrl = `${supportOrigin}/#login`;
const authUrlPrefix = `${ssoIssuerOrigin}/protocol/openid-connect/auth`;
const supportOriginUrl = new URL(supportOrigin);

const browser = await chromium.launch({
  headless: true,
  executablePath: browserExecutablePath,
  args: ['--disable-dev-shm-usage'],
});

const context = await browser.newContext({
  ignoreHTTPSErrors: true,
});

const page = await context.newPage();

try {
  console.log(`Opening ${loginUrl}`);
  await page.goto(loginUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });

  await page.getByRole('button', { name: /^Keycloak$/i }).click();
  await page.waitForURL((url) => url.href.startsWith(authUrlPrefix), { timeout: 30000 });

  console.log(`Reached ${page.url()}`);
  await page.getByLabel('Username or email').fill(loginEmail);
  await page.locator('input#password').fill(loginPassword);
  await page.getByRole('button', { name: /^Sign In$/i }).click();

  await page.waitForURL(
    (url) => url.origin === supportOriginUrl.origin && (url.hash === '#clues' || url.hash === '#dashboard'),
    { timeout: 60000 },
  );

  const title = await page.title();
  if (!/Dashboard/i.test(title)) {
    throw new Error(`Expected dashboard title, got ${title}`);
  }

  console.log(`Completed login at ${page.url()}`);
  console.log(`Title: ${title}`);
} catch (error) {
  const screenshotPath = path.join(artifactDir, 'zammad-sso-login-failure.png');
  await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
  console.error(`ERROR: ${error instanceof Error ? error.message : String(error)}`);
  console.error(`Screenshot: ${screenshotPath}`);
  throw error;
} finally {
  await browser.close();
}
NODE
then
  run_status=0
else
  run_status=$?
fi

exit "$run_status"