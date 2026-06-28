# Fix: SSO Token Premature Broadcast Causing Cascade of 401s

**Date:** 2026-03-23  
**Area:** `dq-ui` — Authentication / SSO callback  
**Files changed:**
- `dq-ui/src/contexts/AuthContext.tsx`
- `dq-ui/src/contexts/SettingsContext.tsx`
- `dq-ui/src/components/ReusableFiltersModal.tsx`
- `dq-ui/src/components/ReusableJoinsModal.tsx`
- `dq-ui/src/components/JoinConditionsModal.tsx`
- `dq-ui/src/components/AssignAttributesModal.tsx`
- `dq-ui/src/hooks/useSuggestions.ts`

---

## Symptom

After a hard refresh (or on first load with a stale stored token), the browser console showed:

```
[Settings] Loading settings, token: eyJhbGciOiJSUzI1NiIs...
[Auth] Failed to initialize SSO session: Error: Failed to resolve SSO user (401)
[Settings] /me failed: 401 {"message":"Invalid signature"}
Failed to load resource: 401 (me)
Failed to load resource: 401 (app-config)
Failed to load resource: 401 (data-products)
Failed to load resource: 401 (attribute-rule-counts)
Failed to load resource: 401 (rules)
Failed to load resource: 401 (approvals)
... (cascade)
```

The app remained stuck in a broken pseudo-authenticated state — it looked logged in but no data loaded.

---

## Root Causes

### 1. SSO callback stored token before verifying it

In `AuthContext.tsx`, the SSO callback handler was:

```ts
// BEFORE — token stored BEFORE /me succeeded
localStorage.setItem('authToken', callbackToken)
window.dispatchEvent(new Event('dq-auth-token-changed'))

try {
  const meResponse = await fetch(`${apiBase}/me`, { ... })
  // ...
} catch (e) {
  console.error('[Auth] Failed to initialize SSO session:', e)
  // token left in storage even on error
}
```

Every context subscribed to `dq-auth-token-changed` (RuleContext, DataProductContext, useFeatureLifecycleConfig, etc.) immediately woke up and started fetching API endpoints using a token that turned out to be invalid.

### 2. Stale persisted token not cleared on invalid-signature 401

`SettingsContext.tsx` treated all `401` responses from `/me` the same way — it logged the error but left `authToken` and `authState` in localStorage intact. On the next render cycle, the contexts tried again with the same bad token.

### 3. Auth in-memory state not collapsed when token removed externally

`AuthContext.tsx` had no listener to reset its in-memory `authState` when `authToken` was removed from localStorage (e.g. by SettingsContext after detecting an invalid token).

### 4. Modal and hook data loads not gated on auth

Several components and hooks called fetch without first checking for a valid token:
- `ReusableFiltersModal.tsx` — `loadFilters()`
- `ReusableJoinsModal.tsx` — `loadJoins()`
- `JoinConditionsModal.tsx` — `loadCatalog()`
- `AssignAttributesModal.tsx` — `loadAttributes()`
- `useSuggestions.ts` — `fetchSuggestions()`, `fetchDataSources()`

---

## Fixes Applied

### `AuthContext.tsx`

1. **Deferred token storage to after `/me` succeeds:**

   ```ts
   // AFTER — token stored only on success
   try {
     const meResponse = await fetch(`${apiBase}/me`, { ... })
     if (!meResponse.ok) throw new Error(...)
     // ... resolve user ...
     localStorage.setItem('authToken', callbackToken)       // ← moved here
     window.dispatchEvent(new Event('dq-auth-token-changed')) // ← moved here
     setAuthState(newState)
     persistAuthState(newState)
   } catch (e) {
     clearPersistedAuthSession()  // evict any stale token on failure
   }
   ```

2. **Added `clearPersistedAuthSession()` export** — removes `authState`, `authToken`, and broadcasts `dq-auth-token-changed`.

3. **Added storage event listener** — resets in-memory `authState` to the empty/logged-out value whenever `authToken` disappears from localStorage.

4. **Extracted `EMPTY_AUTH_STATE` constant** shared by the initial state, `logout()`, and the storage listener.

### `SettingsContext.tsx`

5. **Added `isInvalidPersistedSession()` helper** — detects stale-token 401 responses by matching the response body against `Invalid signature`, `token expired`, etc.

6. **On stale-token 401, calls `clearPersistedAuthSession()`** and resets all settings state, then surfaces `Session expired. Please sign in again.` instead of silently retrying.

7. **Extracted `resetSettingsState()` helper** to keep the settings reset logic in one place.

### Modal components and `useSuggestions`

8. **Added early-return auth guards** to all data-loading functions that were missing them:

   | File | Function | Guard added |
   |------|----------|-------------|
   | `ReusableFiltersModal.tsx` | `loadFilters` | `if (!getAuthToken()) return` |
   | `ReusableJoinsModal.tsx` | `loadJoins` | `if (!getAuthToken()) return` |
   | `JoinConditionsModal.tsx` | `loadCatalog` | `if (!token) return` |
   | `AssignAttributesModal.tsx` | `loadAttributes` | `if (!token) return` |
   | `useSuggestions.ts` | `fetchSuggestions` | `if (!auth.isAuthenticated) return` |
   | `useSuggestions.ts` | `fetchDataSources` | `if (!auth.isAuthenticated) return` |

---

## Outcome

| Scenario | Before | After |
|----------|--------|-------|
| Stale token in localStorage | 401 cascade on every context | SettingsContext detects invalid signature → clears token → all contexts stop loading → UI shows login |
| Invalid SSO callback token (hard refresh) | 401 cascade from premature broadcast | SSO handler verifies first → on failure, clears storage → no broadcast → no cascade → UI shows login |
| Valid SSO callback | Worked (token valid by luck) | Token only stored after `/me` succeeds → one clean load cycle |
| No token at all | Worked | Still works |
