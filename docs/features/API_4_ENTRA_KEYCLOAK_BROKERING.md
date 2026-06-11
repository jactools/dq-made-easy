# API-4 Entra ID + Keycloak Brokering Architecture

**Status**: Proposed  
**Date**: 2026-04-21  
**Feature Track**: [API-4 Advanced Authentication Options](./API_4_AUTHENTICATION_OPTIONS.md)

## Goal

Define the preferred enterprise SSO architecture when Microsoft Entra ID must be integrated into dq-made-easy without breaking the current Keycloak, Kong, and backend trust model.

## Recommendation

Use **Microsoft Entra ID as the identity source** and **Keycloak as the application-facing broker and issuer**.

This means:

- Entra ID owns employee identities, MFA, conditional access, and enterprise group/app-role assignment.
- Keycloak delegates login to Entra ID using OIDC identity brokering.
- Keycloak issues the final JWTs consumed by dq-made-easy.
- Kong and the backend continue to trust **only Keycloak-issued tokens**.

## Why This Is the Best Fit for This Repository

The current stack is already centered on Keycloak:

- The browser auth client is wired to Keycloak.
- Kong validates Keycloak-issued JWTs and is seeded from Keycloak realm/JWKS state.
- The FastAPI backend is configured for a single SSO issuer and validates bearer tokens against that issuer.

Because of that, introducing Entra as a second directly trusted issuer would widen the auth surface and require a broader redesign of Kong bootstrap, issuer validation, and callback handling.

Keeping Keycloak as the contract boundary preserves the existing runtime model while still allowing enterprise login through Entra.

## Target Architecture

```text
Browser / dq-ui
  -> Keycloak login
    -> Microsoft Entra ID
      -> Keycloak broker callback
        -> Keycloak issues final JWT
          -> Kong validates Keycloak issuer + JWKS
            -> dq-api resolves user and enforces scopes
```

## Source of Truth

### Entra ID should own

- workforce identities
- MFA and conditional access policies
- account disablement and lifecycle events
- enterprise group or app-role assignment

### Keycloak should own

- application-facing OIDC issuer surface
- token format consumed by dq-made-easy
- brokered identity mapping into realm/client roles
- break-glass local admin access if required

## Role and Claim Strategy

Prefer **Entra app roles** over raw group claims when possible.

Recommended flow:

1. Assign Entra app roles to users or Entra groups.
2. Expose those app roles in the Entra-issued token.
3. Map those roles in Keycloak identity-provider mappers.
4. Emit Keycloak realm roles or client roles in the final Keycloak token.

This is preferred over direct large-group claim usage because group claims become harder to manage and can hit token-size or overage edge cases.

## Provisioning Strategy

### Default recommendation

Start with **just-in-time provisioning** through Keycloak brokering.

That is sufficient when the requirement is:

- users authenticate with Entra accounts
- dq-made-easy assigns application access at login time
- no pre-created Keycloak user inventory is required

### Add one-way provisioning only if needed

If the organization requires pre-provisioned users, stronger lifecycle sync, or administrative visibility in Keycloak before first login, add **one-way provisioning from Entra to Keycloak**.

Recommended direction:

- Entra / Microsoft Graph -> Keycloak Admin API

Do **not** implement bidirectional sync.

## What to Avoid

### Avoid direct dual-issuer trust

Do not make dq-made-easy accept both Entra-issued tokens and Keycloak-issued tokens directly unless the authentication model is intentionally redesigned.

### Avoid bidirectional directory sync

Do not treat Keycloak and Entra as equal peers for identity ownership. Conflict resolution, disablement order, and role drift become harder than the value gained.

## Configuration Direction

### Keep these application assumptions

- `SSO_PROVIDER` remains effectively `keycloak`
- frontend Keycloak configuration remains the browser-facing auth entrypoint
- Kong remains configured against Keycloak issuer and JWKS
- backend `SSO_ISSUER` remains the Keycloak issuer

### Add this Keycloak capability

- configure Microsoft Entra ID as an external OIDC identity provider in the active Keycloak realm
- add claim mappers for username, email, display name, stable external id, and authorization roles

## Migration Approach

1. Configure Entra enterprise app for dq-made-easy login through Keycloak.
2. Add Entra as an OIDC identity provider in Keycloak.
3. Map Entra roles/claims into Keycloak roles.
4. Test brokered login while keeping current local Keycloak login available.
5. Move standard users to Entra-backed login.
6. Retain one break-glass Keycloak admin account outside Entra.

## Decision Summary

For this repository, the preferred enterprise integration pattern is:

- **Entra ID = source of identity**
- **Keycloak = broker and issuer**
- **dq-made-easy = trusts Keycloak only**

This keeps the existing auth surface stable while allowing enterprise federation and future lifecycle automation.