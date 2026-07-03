/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import App from './App'

const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()

function PassthroughProvider({ children }: { children?: React.ReactNode }) {
  return <>{children}</>
}

if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as any
}

window.requestAnimationFrame = window.requestAnimationFrame || ((callback: FrameRequestCallback) => window.setTimeout(() => callback(Date.now()), 0) as unknown as number)
window.cancelAnimationFrame = window.cancelAnimationFrame || ((handle: number) => window.clearTimeout(handle))

vi.mock('./contexts/AuthContext', () => ({
  AuthProvider: PassthroughProvider,
  getAuthToken: () => null,
}))

vi.mock('./contexts/RuleContext', () => ({
  RuleProvider: PassthroughProvider,
}))

vi.mock('./contexts/SettingsContext', () => ({
  SettingsProvider: PassthroughProvider,
  SettingsContext: React.createContext(null),
}))

vi.mock('./contexts/NotificationContext', () => ({
  NotificationProvider: PassthroughProvider,
}))

vi.mock('./contexts/AsyncRequestTrackerContext', () => ({
  AsyncRequestTrackerProvider: PassthroughProvider,
}))

vi.mock('./contexts/VersionCatalogContext', () => ({
  VersionCatalogProvider: PassthroughProvider,
}))

vi.mock('./contexts/DataProductContext', () => ({
  DataProductProvider: PassthroughProvider,
}))

vi.mock('./hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('./hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
}))

vi.mock('./components/Header', () => ({
  Header: () => <div data-testid="header" />,
}))

vi.mock('./components/Sidebar', () => ({
  Sidebar: ({ onItemClick }: { onItemClick: (id: string) => void }) => (
    <div data-testid="sidebar">
      <button type="button" onClick={() => onItemClick('data-browser-all')}>Open data catalog all</button>
      <button type="button" onClick={() => onItemClick('approvals-all')}>Open governance all</button>
      <button type="button" onClick={() => onItemClick('rules-all')}>Open all rules</button>
      <button type="button" onClick={() => onItemClick('approvals-exceptions')}>Open exception records</button>
      <button type="button" onClick={() => onItemClick('reports-incidents')}>Open incidents</button>
      <button type="button" onClick={() => onItemClick('reports-agent-access')}>Open agent access</button>
      <button type="button" onClick={() => onItemClick('reports-service-levels')}>Open service levels</button>
      <button type="button" onClick={() => onItemClick('discussions')}>Open discussions</button>
      <button type="button" onClick={() => onItemClick('administration-ui-registry')}>Open UI registry</button>
    </div>
  ),
}))

vi.mock('./components/DataBrowser', () => ({
  DataBrowser: ({ viewScope }: { viewScope: string }) => <div data-testid="data-browser-page" data-view-scope={viewScope} />,
}))

vi.mock('./components/Approvals', () => ({
  Approvals: ({ viewScope }: { viewScope: string }) => <div data-testid="approvals-page" data-view-scope={viewScope} />,
}))

vi.mock('./components/Rules', () => ({
  Rules: ({ viewScope }: { viewScope: string }) => <div data-testid="rules-page" data-view-scope={viewScope} />,
}))

vi.mock('./components/SupportRequestFooter', () => ({
  SupportRequestFooter: () => <div data-testid="support-request-footer" />,
}))

vi.mock('./components/Toolbar', () => ({
  Toolbar: () => <div data-testid="toolbar" />,
}))

vi.mock('./components/Welcome', () => ({
  Welcome: () => <div data-testid="welcome" />,
}))

vi.mock('./components/Dashboard', () => ({
  Dashboard: () => <div data-testid="dashboard" />,
}))

vi.mock('./components/DefinitionMappingsPage', () => ({
  DefinitionMappingsPage: () => <div data-testid="definition-mappings-page" />,
}))

vi.mock('./components/UIRegistryAdmin', () => ({
  UIRegistryAdmin: () => <div data-testid="ui-registry-admin" />,
}))

vi.mock('./components/Documentation', () => ({
  Documentation: () => <div data-testid="documentation-page" />,
}))

vi.mock('./components/Reports', () => ({
  Reports: ({ initialTab }: { initialTab: string }) => <div data-testid="reports-page" data-initial-tab={initialTab} />,
}))

vi.mock('./components/ServiceLevelsPage', () => ({
  ServiceLevelsPage: () => <div data-testid="service-levels-page" />,
}))

vi.mock('./components/DiscussionHub', () => ({
  DiscussionHub: () => <div data-testid="discussion-hub" />,
}))

vi.mock('./components/AuthModal', () => ({
  LoginModal: ({ isOpen }: { isOpen: boolean }) => (
    <div data-testid="login-modal" data-open={String(isOpen)}>
      {isOpen ? 'open' : 'closed'}
    </div>
  ),
}))

vi.mock('./components/SessionTimeoutWarning', () => ({
  SessionTimeoutWarning: () => <div data-testid="session-timeout-warning" />,
}))

vi.mock('./components/RuntimeModeIndicator', () => ({
  RuntimeModeIndicator: () => <div data-testid="runtime-mode-indicator" />,
}))

vi.mock('./components/features', () => ({
  RuleValidation: () => <div data-testid="rule-validation" />,
  RuleLifecycleManagement: () => <div data-testid="rule-lifecycle" />,
  RuleResultAggregation: () => <div data-testid="rule-result-aggregation" />,
  ExceptionRecordHandling: () => <div data-testid="exception-records-page" />,
  RuleExecutionMonitoring: () => <div data-testid="rule-execution-monitoring" />,
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  sessionStorage.clear()
  window.history.pushState({}, '', '/')
})

describe('App workspace selection bootstrap', () => {
  it('renders public documentation without requiring login', () => {
    window.history.pushState({}, '', '/docs/')

    mockUseSettings.mockReturnValue({
      displaySettings: { theme: 'auto' },
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
    })
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      currentWorkspaceId: null,
      user: null,
      getCurrentUserRole: () => null,
      hasAnyScope: () => false,
      hasScope: () => false,
      canManageUsers: () => false,
    })

    render(<App />)

    expect(screen.getByText('Public documentation')).toBeTruthy()
    expect(screen.getByText('Redirecting to the static docs portal…')).toBeTruthy()
    expect(screen.queryByText('Please log in to access the full application')).toBeNull()
  })

  it('reopens the login modal for corporate admins with multiple workspaces and no active selection', async () => {
    mockUseSettings.mockReturnValue({
      displaySettings: { theme: 'auto' },
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
    })
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: null,
      user: {
        name: 'Corporate Admin',
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'admin' },
          { workspaceId: 'corporate-banking', role: 'admin' },
        ],
      },
      getCurrentUserRole: () => 'admin',
      hasAnyScope: () => true,
      hasScope: () => true,
      canManageUsers: () => true,
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('login-modal').getAttribute('data-open')).toBe('true')
    })

    expect(screen.getByTestId('support-request-footer')).toBeTruthy()
  })

  it('allows Governance exception records navigation for active JIT scopes', async () => {
    mockUseSettings.mockReturnValue({
      displaySettings: { theme: 'auto' },
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
    })
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      user: {
        name: 'Exception Reader',
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'exception-fact-reader' },
        ],
      },
      getCurrentUserRole: () => 'exception-fact-reader',
      hasAnyScope: (scopes: string[]) => scopes.includes('dq:exceptions:read'),
      hasScope: (scope: string) => scope === 'dq:exceptions:read',
      canManageUsers: () => false,
    })

    render(<App />)

    fireEvent.click(screen.getByText('Open exception records'))

    await waitFor(() => {
      expect(screen.getByTestId('exception-records-page')).toBeTruthy()
    })
  })

    it('opens the Rules all-items view from the sidebar entry', async () => {
      mockUseSettings.mockReturnValue({
        displaySettings: { theme: 'auto' },
        applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
      })
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        currentWorkspaceId: 'retail-banking',
        user: {
          name: 'Rules User',
          workspaceRoles: [
            { workspaceId: 'retail-banking', role: 'analyst' },
          ],
        },
        getCurrentUserRole: () => 'analyst',
        hasAnyScope: () => true,
        hasScope: () => true,
        canManageUsers: () => false,
      })

      render(<App />)

      fireEvent.click(screen.getByText('Open all rules'))

      await waitFor(() => {
        expect(screen.getByTestId('rules-page')).toBeTruthy()
      })

      expect(screen.getByTestId('rules-page').getAttribute('data-view-scope')).toBe('all')
    })

    it('opens the Governance all-items view from the sidebar entry', async () => {
      mockUseSettings.mockReturnValue({
        displaySettings: { theme: 'auto' },
        applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
      })
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        currentWorkspaceId: 'retail-banking',
        user: {
          name: 'Governance User',
          workspaceRoles: [
            { workspaceId: 'retail-banking', role: 'data-steward' },
          ],
        },
        getCurrentUserRole: () => 'data-steward',
        hasAnyScope: () => true,
        hasScope: () => true,
        canManageUsers: () => false,
      })

      render(<App />)

      fireEvent.click(screen.getByText('Open governance all'))

      await waitFor(() => {
        expect(screen.getByTestId('approvals-page')).toBeTruthy()
      })

      expect(screen.getByTestId('approvals-page').getAttribute('data-view-scope')).toBe('all')
    })

    it('opens the Data Catalog all-items view from the sidebar entry', async () => {
      mockUseSettings.mockReturnValue({
        displaySettings: { theme: 'auto' },
        applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
      })
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        currentWorkspaceId: 'retail-banking',
        user: {
          name: 'Catalog User',
          workspaceRoles: [
            { workspaceId: 'retail-banking', role: 'analyst' },
          ],
        },
        getCurrentUserRole: () => 'analyst',
        hasAnyScope: () => true,
        hasScope: () => true,
        canManageUsers: () => false,
      })

      render(<App />)

      fireEvent.click(screen.getByText('Open data catalog all'))

      await waitFor(() => {
        expect(screen.getByTestId('data-browser-page')).toBeTruthy()
      })

      expect(screen.getByTestId('data-browser-page').getAttribute('data-view-scope')).toBe('all')
    })

  it('opens workspace incidents from the Operations sidebar entry', async () => {
    mockUseSettings.mockReturnValue({
      displaySettings: { theme: 'auto' },
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
    })
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      user: {
        name: 'Operations User',
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'analyst' },
        ],
      },
      getCurrentUserRole: () => 'analyst',
      hasAnyScope: () => true,
      hasScope: () => true,
      canManageUsers: () => false,
    })

    render(<App />)

    fireEvent.click(screen.getByText('Open incidents'))

    await waitFor(() => {
      expect(screen.getByTestId('reports-page')).toBeTruthy()
    })

    expect(screen.getByTestId('reports-page').getAttribute('data-initial-tab')).toBe('incidents')
  })

  it('opens agent access from the Operations sidebar entry', async () => {
    mockUseSettings.mockReturnValue({
      displaySettings: { theme: 'auto' },
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
    })
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      user: {
        name: 'Operations Admin',
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'admin' },
        ],
      },
      getCurrentUserRole: () => 'admin',
      hasAnyScope: () => true,
      hasScope: () => true,
      canManageUsers: () => false,
    })

    render(<App />)

    fireEvent.click(screen.getByText('Open agent access'))

    await waitFor(() => {
      expect(screen.getByTestId('reports-page')).toBeTruthy()
    })

    expect(screen.getByTestId('reports-page').getAttribute('data-initial-tab')).toBe('agent-access')
  })

  it('opens service levels from the Operations sidebar entry', async () => {
    mockUseSettings.mockReturnValue({
      displaySettings: { theme: 'auto' },
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
    })
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      user: {
        name: 'Operations User',
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'analyst' },
        ],
      },
      getCurrentUserRole: () => 'analyst',
      hasAnyScope: () => true,
      hasScope: () => true,
      canManageUsers: () => false,
    })

    render(<App />)

    fireEvent.click(screen.getByText('Open service levels'))

    await waitFor(() => {
      expect(screen.getByTestId('service-levels-page')).toBeTruthy()
    })
  })

    it('opens the discussion hub from the sidebar entry', async () => {
      mockUseSettings.mockReturnValue({
        displaySettings: { theme: 'auto' },
        applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
      })
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        currentWorkspaceId: 'retail-banking',
        user: {
          name: 'Discussion User',
          workspaceRoles: [
            { workspaceId: 'retail-banking', role: 'analyst' },
          ],
        },
        getCurrentUserRole: () => 'analyst',
        hasAnyScope: () => true,
        hasScope: () => true,
        canManageUsers: () => false,
      })

      render(<App />)

      fireEvent.click(screen.getByText('Open discussions'))

      await waitFor(() => {
        expect(screen.getByTestId('discussion-hub')).toBeTruthy()
      })
    })

  it('opens the discussion hub from the sidebar entry', async () => {
    mockUseSettings.mockReturnValue({
      displaySettings: { theme: 'auto' },
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
    })
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      user: {
        name: 'Discussion User',
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'analyst' },
        ],
      },
      getCurrentUserRole: () => 'analyst',
      hasAnyScope: () => true,
      hasScope: () => true,
      canManageUsers: () => false,
    })

    render(<App />)

    fireEvent.click(screen.getByText('Open discussions'))

    await waitFor(() => {
      expect(screen.getByTestId('discussion-hub')).toBeTruthy()
    })
  })

  it('opens the UI registry admin page for workspace admins', async () => {
    mockUseSettings.mockReturnValue({
      displaySettings: { theme: 'auto' },
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', sessionTimeoutMinutes: 0 },
    })
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      user: {
        name: 'Admin User',
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'admin' },
        ],
      },
      getCurrentUserRole: () => 'admin',
      hasAnyScope: () => true,
      hasScope: () => true,
      canManageUsers: () => true,
    })

    render(<App />)

    fireEvent.click(screen.getByText('Open UI registry'))

    await waitFor(() => {
      expect(screen.getByTestId('ui-registry-admin')).toBeTruthy()
    })
  })
})