/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Header } from './Header'

const mockUseAuth = vi.fn()
const mockUseRules = vi.fn()
const mockUseSettings = vi.fn()
const mockUseVersionCatalog = vi.fn()

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('../hooks/useContexts', () => ({
  useRules: () => mockUseRules(),
  useSettings: () => mockUseSettings(),
}))

vi.mock('../hooks/useVersionCatalog', () => ({
  useVersionCatalog: () => mockUseVersionCatalog(),
}))

vi.mock('./NotificationCenter', () => ({
  NotificationCenter: () => null,
}))

vi.mock('./VersionInfoModal', () => ({
  VersionInfoModal: () => null,
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('Header workspace display', () => {
  it('shows the current workspace in the header when authenticated', () => {
    vi.stubGlobal('__BUILD_DATE__', '2026-04-06')

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      getCurrentUserRole: () => 'analyst',
      user: {
        name: 'Multi Workspace User',
        avatarUrl: null,
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'analyst' },
          { workspaceId: 'corporate-banking', role: 'viewer' },
        ],
      },
      isAdminModeEnabled: true,
      setAdminModeEnabled: vi.fn(),
      logout: vi.fn(),
    })
    mockUseRules.mockReturnValue({ approvals: [], rules: [] })
    mockUseSettings.mockReturnValue({ notificationSettings: null })
    mockUseVersionCatalog.mockReturnValue({ versionCatalog: { apps: { ui: '0.0.0' } } })

    render(<Header onLoginClick={vi.fn()} />)

    expect(screen.getByText('Current workspace')).toBeTruthy()
    expect(screen.getByText('Retail Banking')).toBeTruthy()
  })

  it('starts admin mode disabled for admin users and still allows toggling it', () => {
    vi.stubGlobal('__BUILD_DATE__', '2026-04-06')

    const setAdminModeEnabled = vi.fn()

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      isAdminModeEnabled: false,
      getCurrentUserRole: () => null,
      user: {
        name: 'Admin User',
        avatarUrl: null,
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'admin' },
        ],
      },
      setAdminModeEnabled,
      logout: vi.fn(),
    })
    mockUseRules.mockReturnValue({ approvals: [], rules: [] })
    mockUseSettings.mockReturnValue({ notificationSettings: null })
    mockUseVersionCatalog.mockReturnValue({ versionCatalog: { apps: { ui: '0.0.0' } } })

    render(<Header onLoginClick={vi.fn()} />)

    expect(screen.queryByText('Admin Mode')).toBeNull()
    expect(screen.queryByTitle('Current role: Admin')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Admin User' }))
    expect(screen.getByRole('button', { name: /enable admin mode/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /logout/i })).toBeTruthy()

    fireEvent.click(screen.getByText(/Enable admin mode/i))

    expect(setAdminModeEnabled).toHaveBeenCalledWith(true)

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      isAdminModeEnabled: true,
      getCurrentUserRole: () => 'admin',
      user: {
        name: 'Admin User',
        avatarUrl: null,
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'admin' },
        ],
      },
      setAdminModeEnabled,
      logout: vi.fn(),
    })

    fireEvent.click(screen.getByRole('button', { name: 'Admin User' }))
    expect(screen.getByText('Admin Mode')).toBeTruthy()
    fireEvent.click(screen.getByText(/Disable admin mode/i))

    expect(setAdminModeEnabled).toHaveBeenCalledWith(false)
  })

  it('shows a role badge for auditor and regulator users', () => {
    vi.stubGlobal('__BUILD_DATE__', '2026-04-06')

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'global',
      getCurrentUserRole: () => 'auditor',
      user: {
        name: 'Auditor User',
        avatarUrl: null,
        workspaceRoles: [
          { workspaceId: 'global', role: 'auditor' },
        ],
      },
      isAdminModeEnabled: false,
      setAdminModeEnabled: vi.fn(),
      logout: vi.fn(),
    })
    mockUseRules.mockReturnValue({ approvals: [], rules: [] })
    mockUseSettings.mockReturnValue({ notificationSettings: null })
    mockUseVersionCatalog.mockReturnValue({ versionCatalog: { apps: { ui: '0.0.0' } } })

    render(<Header onLoginClick={vi.fn()} />)

    expect(screen.getByText('Auditor')).toBeTruthy()
  })

  it('shows a JIT badge when exception fact access is active', () => {
    vi.stubGlobal('__BUILD_DATE__', '2026-04-06')

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      getCurrentUserRole: () => 'exception-fact-reader',
      user: {
        name: 'JIT User',
        avatarUrl: null,
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'exception-fact-reader' },
        ],
      },
      isAdminModeEnabled: false,
      setAdminModeEnabled: vi.fn(),
      logout: vi.fn(),
    })
    mockUseRules.mockReturnValue({ approvals: [], rules: [] })
    mockUseSettings.mockReturnValue({ notificationSettings: null })
    mockUseVersionCatalog.mockReturnValue({ versionCatalog: { apps: { ui: '0.0.0' } } })

    render(<Header onLoginClick={vi.fn()} />)

    expect(screen.getByText('Exception Fact Reader')).toBeTruthy()
  })
})