# JWT End-to-End Test Results

Status: Done

## Current State

Browser authentication now uses Kong directly as the browser entrypoint.

## Validated Flow

- `dq-ui -> Kong -> dq-api`
- Kong validates JWTs and handles OAuth2/browser auth routing.
- Direct Kong access remains valid for gateway and troubleshooting tests.

## Key Checks

- Keycloak token issuance works for the configured `SSO_CLIENT_ID`.
- Protected API routes succeed through Kong with JWT credentials.
- Logout redirects return the browser to the frontend origin through the backend auth endpoint.

## Notes

- The browser API base URL is `http://localhost:9111` in local development.
- `TRUST_PROXY_AUTH=true` remains required when Kong is the trusted gateway in front of the API.
- Historical proxy-specific test notes have been retired.
