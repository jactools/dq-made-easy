/** @vitest-environment jsdom */
import React, { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { RuleProvider, useRule } from './RuleContext'
import { AuthContext } from './AuthContext'
import { SettingsContext } from './SettingsContext'

const approvalsPage = {
  data: [
    {
      id: 'approval-1',
      rule_id: 'rule-1',
      requester_id: 'alice-id',
      requested_at: '2026-04-12T00:00:00Z',
      status: 'pending',
      workspace_id: 'ws-a',
      request_type: 'deactivation',
      effective_status: 'deactivated',
    },
  ],
  pagination: {
    total: 1,
    page: 1,
    limit: 20,
    total_pages: 1,
    has_next: false,
    has_previous: false,
  },
}

const rulesPage = {
  data: [
    {
      id: 'rule-1',
      workspace: 'ws-a',
      name: 'Rule Alpha',
      description: 'desc',
      active: true,
      last_approval_status: 'pending',
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
      pending_deactivation_requested: true,
    },
  ],
  pagination: {
    total: 1,
    page: 1,
    limit: 20,
    total_pages: 1,
    has_next: false,
    has_previous: false,
  },
}

const emptyPage = {
  data: [],
  pagination: {
    total: 0,
    page: 1,
    limit: 20,
    total_pages: 0,
    has_next: false,
    has_previous: false,
  },
}

const Probe = () => {
  const { approvals, rules, loadRulesPage } = useRule()

  return (
    <div>
      <div data-testid="approval-count">{approvals.length}</div>
      <div data-testid="approval-request-type">{approvals[0]?.requestType || 'none'}</div>
      <div data-testid="approval-effective-status">{approvals[0]?.effectiveStatus || 'none'}</div>
      <div data-testid="rule-count">{rules.length}</div>
      <div data-testid="rule-status">{rules[0]?.status || 'none'}</div>
      <div data-testid="rule-pending-deactivation">{rules[0]?.pendingDeactivationRequested ? 'true' : 'false'}</div>
      <button
        type="button"
        data-testid="load-filtered-rules"
        onClick={() => loadRulesPage({
          page: 2,
          limit: 50,
          workspace: 'ws-a',
          status: 'activated',
          q: 'customer id',
          owner: 'alice@example.com',
          updatedSince: '2026-05-01',
          updatedBefore: '2026-05-31',
        })}
      >
        load filtered
      </button>
    </div>
  )
}

const buildPersistedAuthState = (isAuthenticated: boolean) => ({
  user: isAuthenticated
    ? {
        id: 'alice-id',
        email: 'alice@example.com',
        name: 'Alice Admin',
        workspaceRoles: [{ workspaceId: 'ws-a', role: 'admin' }],
        createdAt: '2026-04-01T00:00:00.000Z',
        isActive: true,
      }
    : null,
  currentWorkspaceId: isAuthenticated ? 'ws-a' : null,
  isAuthenticated,
  isLoading: false,
  error: null,
})

const persistAuthenticatedSession = () => {
  localStorage.setItem('authToken', 'fresh-token')
  localStorage.setItem('authState', JSON.stringify(buildPersistedAuthState(true)))
}

const StatefulAuthHarness = () => {
  const [authValue, setAuthValue] = useState({
    isAuthenticated: true,
    currentWorkspaceId: 'ws-a',
    user: {
      id: 'alice-id',
      name: 'Alice Admin',
      email: 'alice@example.com',
      roles: ['admin'],
      workspaceRoles: [{ workspaceId: 'ws-a', role: 'admin' }],
    },
    isLoading: false,
    error: null,
  } as any)

  const loginWithToken = () => {
    persistAuthenticatedSession()
    window.dispatchEvent(new Event('dq-auth-token-changed'))
    setAuthValue((current: any) => ({ ...current, isAuthenticated: true }))
  }

  const logoutWithoutToken = () => {
    localStorage.removeItem('authToken')
    localStorage.setItem('authState', JSON.stringify(buildPersistedAuthState(false)))
    window.dispatchEvent(new Event('dq-auth-token-changed'))
    setAuthValue((current: any) => ({ ...current, isAuthenticated: false, currentWorkspaceId: null, user: null }))
  }

  return (
    <SettingsContext.Provider value={{ applicationSettings: { apiBaseUrl: 'http://api.example' } } as any}>
      <AuthContext.Provider value={authValue as any}>
        <RuleProvider>
          <Probe />
        </RuleProvider>
      </AuthContext.Provider>
      <button type="button" data-testid="logout-button" onClick={logoutWithoutToken}>logout</button>
      <button type="button" data-testid="login-button" onClick={loginWithToken}>login</button>
    </SettingsContext.Provider>
  )
}

describe('RuleContext approvals reload', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)

      if (url.includes('/approvals/audit')) {
        return new Response(JSON.stringify([]), { status: 200 })
      }

      if (url.includes('/approvals')) {
        const headers = new Headers(init?.headers)
        if (headers.get('Authorization')) {
          return new Response(JSON.stringify(approvalsPage), { status: 200 })
        }
        return new Response('Unauthorized', { status: 401 })
      }

      if (url.includes('/rules?')) {
        const headers = new Headers(init?.headers)
        if (headers.get('Authorization')) {
          return new Response(JSON.stringify(rulesPage), { status: 200 })
        }
        return new Response('Unauthorized', { status: 401 })
      }

      if (url.includes('/rule-attributes')) {
        return new Response(JSON.stringify([]), { status: 200 })
      }

      return new Response(JSON.stringify(emptyPage), { status: 200 })
    }) as typeof fetch)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('refetches approvals after the auth token becomes available again', async () => {
    const authValue = {
      isAuthenticated: true,
      currentWorkspaceId: 'ws-a',
      user: {
        id: 'alice-id',
        name: 'Alice Admin',
        email: 'alice@example.com',
        roles: ['admin'],
        workspaceRoles: [{ workspaceId: 'ws-a', role: 'admin' }],
      },
      isLoading: false,
      error: null,
    } as any

    const settingsValue = {
      applicationSettings: {
        apiBaseUrl: 'http://api.example',
      },
    } as any

    render(
      <SettingsContext.Provider value={settingsValue}>
        <AuthContext.Provider value={authValue}>
          <RuleProvider>
            <Probe />
          </RuleProvider>
        </AuthContext.Provider>
      </SettingsContext.Provider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('approval-count').textContent).toBe('0')
      expect(screen.getByTestId('rule-count').textContent).toBe('0')
    })

  persistAuthenticatedSession()
    window.dispatchEvent(new Event('dq-auth-token-changed'))

    await waitFor(() => {
      expect(screen.getByTestId('approval-count').textContent).toBe('1')
      expect(screen.getByTestId('approval-request-type').textContent).toBe('deactivation')
      expect(screen.getByTestId('approval-effective-status').textContent).toBe('deactivated')
      expect(screen.getByTestId('rule-count').textContent).toBe('1')
      expect(screen.getByTestId('rule-status').textContent).toBe('activated')
    })
  })

  it('keeps the pending deactivation flag visible through logout and login', async () => {
    persistAuthenticatedSession()

    render(<StatefulAuthHarness />)

    await waitFor(() => {
      expect(screen.getAllByTestId('rule-count').some((node) => node.textContent === '1')).toBe(true)
      expect(screen.getAllByTestId('rule-pending-deactivation').some((node) => node.textContent === 'true')).toBe(true)
    })

    screen.getByTestId('logout-button').click()

    await waitFor(() => {
      expect(screen.getAllByTestId('rule-count').some((node) => node.textContent === '1')).toBe(true)
      expect(screen.getAllByTestId('rule-pending-deactivation').some((node) => node.textContent === 'true')).toBe(true)
    })

    screen.getByTestId('login-button').click()

    await waitFor(() => {
      expect(screen.getAllByTestId('rule-count').some((node) => node.textContent === '1')).toBe(true)
      expect(screen.getAllByTestId('rule-pending-deactivation').some((node) => node.textContent === 'true')).toBe(true)
    })
  })

  it('sends canonical API query params for filtered rules loading', async () => {
    persistAuthenticatedSession()

    const authValue = {
      isAuthenticated: true,
      currentWorkspaceId: 'ws-a',
      user: {
        id: 'alice-id',
        name: 'Alice Admin',
        email: 'alice@example.com',
        roles: ['admin'],
        workspaceRoles: [{ workspaceId: 'ws-a', role: 'admin' }],
      },
      isLoading: false,
      error: null,
    } as any

    render(
      <SettingsContext.Provider value={{ applicationSettings: { apiBaseUrl: 'http://api.example' } } as any}>
        <AuthContext.Provider value={authValue}>
          <RuleProvider>
            <Probe />
          </RuleProvider>
        </AuthContext.Provider>
      </SettingsContext.Provider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('rule-count').textContent).toBe('1')
    })

    screen.getByTestId('load-filtered-rules').click()

    await waitFor(() => {
      const ruleRequest = (fetch as any).mock.calls
        .map(([input]: [RequestInfo | URL]) => String(input))
        .find((url: string) => url.includes('/rules?') && url.includes('status=activated'))
      expect(ruleRequest).toContain('workspace=ws-a')
      expect(ruleRequest).toContain('q=customer+id')
      expect(ruleRequest).toContain('owner=alice%40example.com')
      expect(ruleRequest).toContain('updated_since=2026-05-01')
      expect(ruleRequest).toContain('updated_before=2026-05-31')
    })
  })
})