import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearPersistedAuthSession, extractWorkspaceRoles, getAuthToken, refreshAuthTokenBackend } from './AuthContext'

class StorageMock {
  private map = new Map<string, string>()

  getItem(key: string): string | null {
    return this.map.has(key) ? this.map.get(key)! : null
  }

  setItem(key: string, value: string): void {
    this.map.set(key, String(value))
  }

  removeItem(key: string): void {
    this.map.delete(key)
  }

  clear(): void {
    this.map.clear()
  }
}

describe('clearPersistedAuthSession', () => {
  beforeEach(() => {
    const localStorageMock = new StorageMock()
    const sessionStorageMock = new StorageMock()

    Object.defineProperty(globalThis, 'localStorage', {
      value: localStorageMock,
      configurable: true,
      writable: true,
    })

    Object.defineProperty(globalThis, 'sessionStorage', {
      value: sessionStorageMock,
      configurable: true,
      writable: true,
    })

    Object.defineProperty(globalThis, 'window', {
      value: {
        dispatchEvent: vi.fn(),
      },
      configurable: true,
      writable: true,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('clears dq-open-new-rule from sessionStorage so a stale flag cannot auto-open the rule wizard after login', () => {
    sessionStorage.setItem('dq-open-new-rule', '1')
    clearPersistedAuthSession()
    expect(sessionStorage.getItem('dq-open-new-rule')).toBeNull()
  })

  it('clears auth tokens from localStorage', () => {
    localStorage.setItem('authToken', 'tok')
    localStorage.setItem('authState', '{}')
    localStorage.setItem('oidcIdToken', 'id-tok')
    localStorage.setItem('dq-admin-mode-enabled', 'false')
    sessionStorage.setItem('dq-workspace-selection-pending', '1')
    sessionStorage.setItem('dq-browser-auth-bootstrap-pending', '1')
    clearPersistedAuthSession()
    expect(localStorage.getItem('authToken')).toBeNull()
    expect(localStorage.getItem('authState')).toBeNull()
    expect(localStorage.getItem('oidcIdToken')).toBeNull()
    expect(localStorage.getItem('dq-admin-mode-enabled')).toBeNull()
    expect(sessionStorage.getItem('dq-workspace-selection-pending')).toBeNull()
    expect(sessionStorage.getItem('dq-browser-auth-bootstrap-pending')).toBeNull()
  })

  it('sets session flag and dispatches expired event when expired=true', () => {
    const dispatched: any[] = []
    Object.defineProperty(globalThis, 'window', {
      value: {
        dispatchEvent: (ev: any) => dispatched.push(ev),
      },
      configurable: true,
      writable: true,
    })

    clearPersistedAuthSession(true)
    expect(sessionStorage.getItem('dq-session-expired')).toBe('1')
    expect(localStorage.getItem('dq-session-last-activity-at')).toBeNull()
    expect(dispatched.length).toBeGreaterThan(0)
    // clean up
    sessionStorage.removeItem('dq-session-expired')
  })
})

describe('getAuthToken', () => {
  beforeEach(() => {
    const localStorageMock = new StorageMock()
    const sessionStorageMock = new StorageMock()

    Object.defineProperty(globalThis, 'localStorage', {
      value: localStorageMock,
      configurable: true,
      writable: true,
    })

    Object.defineProperty(globalThis, 'sessionStorage', {
      value: sessionStorageMock,
      configurable: true,
      writable: true,
    })

    Object.defineProperty(globalThis, 'window', {
      value: {
        dispatchEvent: vi.fn(),
      },
      configurable: true,
      writable: true,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('clears a stale token when no authenticated authState exists', () => {
    localStorage.setItem('authToken', 'stale-token')

    expect(getAuthToken()).toBeNull()
    expect(localStorage.getItem('authToken')).toBeNull()
    expect(localStorage.getItem('authState')).toBeNull()
  })

  it('clears a token when authState is explicitly unauthenticated', () => {
    localStorage.setItem('authToken', 'stale-token')
    localStorage.setItem('authState', JSON.stringify({ isAuthenticated: false, user: null }))

    expect(getAuthToken()).toBeNull()
    expect(localStorage.getItem('authToken')).toBeNull()
  })
})

describe('extractWorkspaceRoles', () => {
  it('preserves structured workspace-role assignments from the backend payload', () => {
    const workspaceRoles = extractWorkspaceRoles({
      workspace_roles: [
        { workspace_id: 'retail-banking', role: 'analyst' },
        { workspaceId: 'corporate-banking', role: 'data-steward' },
      ],
    })

    expect(workspaceRoles).toHaveLength(2)
    expect(workspaceRoles[0].workspaceId).toBe('retail-banking')
    expect(workspaceRoles[0].role).toBe('analyst')
    expect(workspaceRoles[1].workspaceId).toBe('corporate-banking')
    expect(workspaceRoles[1].role).toBe('data-steward')
  })

  it('preserves auditor and regulator workspace roles from the backend payload', () => {
    const workspaceRoles = extractWorkspaceRoles({
      workspace_roles: [
        { workspace_id: 'global', role: 'auditor' },
        { workspace_id: 'global', role: 'regulator' },
      ],
    })

    expect(workspaceRoles).toHaveLength(2)
    expect(workspaceRoles[0].role).toBe('auditor')
    expect(workspaceRoles[1].role).toBe('regulator')
  })

  it('preserves governance workspace roles from the backend payload', () => {
    const workspaceRoles = extractWorkspaceRoles({
      workspace_roles: [
        { workspace_id: 'governance', role: 'governance-admin' },
        { workspace_id: 'governance', role: 'governance-editor' },
      ],
    })

    expect(workspaceRoles).toHaveLength(2)
    expect(workspaceRoles[0].role).toBe('governance-admin')
    expect(workspaceRoles[1].role).toBe('governance-editor')
  })
})

describe('refreshAuthTokenBackend', () => {
  beforeEach(() => {
    // stub global fetch
    Object.defineProperty(globalThis, 'fetch', {
      value: vi.fn(),
      configurable: true,
      writable: true,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns parsed body on success', async () => {
    const mockBody = { token: 'newtok', refreshToken: 'newrefresh' }
    ;(globalThis.fetch as any).mockResolvedValueOnce({ ok: true, json: async () => mockBody })
    const result = await refreshAuthTokenBackend('http://api', 'rtok')
    expect(result).toEqual(mockBody)
  })

  it('returns null on non-OK response', async () => {
    ;(globalThis.fetch as any).mockResolvedValueOnce({ ok: false })
    const result = await refreshAuthTokenBackend('http://api', 'rtok')
    expect(result).toBeNull()
  })
})
