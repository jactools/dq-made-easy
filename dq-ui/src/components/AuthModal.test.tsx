/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SettingsContext } from '../contexts/SettingsContext'
import { LoginModal } from './AuthModal'

const mockUseAuth = vi.fn()

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('./app-primitives', async () => {
  const actual = await vi.importActual<typeof import('./app-primitives')>('./app-primitives')
  return {
    ...actual,
    AppModal: ({ children, title }: any) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
    ),
    AppButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
      <button type={props.type || 'button'} {...props}>{children}</button>
    ),
  }
})


afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('LoginModal workspace selection', () => {
  it('shows the workspace selector after login for multi-workspace users', () => {
    mockUseAuth.mockReturnValue({
      user: {
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'analyst' },
          { workspaceId: 'corporate-banking', role: 'viewer' },
        ],
      },
      currentWorkspaceId: null,
      isLoading: false,
      error: null,
      switchWorkspace: vi.fn(),
      login: vi.fn(),
      logout: vi.fn(),
    })

    render(
      <SettingsContext.Provider value={{ applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1', ssoEnabled: false } } as any}>
        <LoginModal isOpen onClose={vi.fn()} />
      </SettingsContext.Provider>
    )

    expect(screen.getByText('Select Workspace')).toBeTruthy()
    expect(screen.getByText('Retail Banking')).toBeTruthy()
    expect(screen.getByText('analyst')).toBeTruthy()
    expect(screen.getByText('Corporate Banking')).toBeTruthy()
    expect(screen.getByText('viewer')).toBeTruthy()
  })
})

describe('LoginModal login methods', () => {
  const baseAuth = {
    user: null,
    currentWorkspaceId: null,
    isLoading: false,
    error: null,
    switchWorkspace: vi.fn(),
    login: vi.fn(),
    loginWithSso: vi.fn(),
    logout: vi.fn(),
  }

  it('hides the Admin Login option when local authentication is disabled', () => {
    mockUseAuth.mockReturnValue(baseAuth)

    render(
      <SettingsContext.Provider value={{ applicationSettings: { ssoEnabled: true, ssoIssuerUrl: 'https://dq-made-easy.nl/iam/realms/jaccloud', allowLocalAuth: false } } as any}>
        <LoginModal isOpen onClose={vi.fn()} />
      </SettingsContext.Provider>
    )

    expect(screen.getByRole('button', { name: 'SSO Login' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Admin Login' })).toBeNull()
  })

  it('hides the Admin Login option when local authentication setting is absent', () => {
    mockUseAuth.mockReturnValue(baseAuth)

    render(
      <SettingsContext.Provider value={{ applicationSettings: { ssoEnabled: true, ssoIssuerUrl: 'https://dq-made-easy.nl/iam/realms/jaccloud' } } as any}>
        <LoginModal isOpen onClose={vi.fn()} />
      </SettingsContext.Provider>
    )

    expect(screen.getByRole('button', { name: 'SSO Login' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Admin Login' })).toBeNull()
  })

  it('shows the Admin Login form when local authentication is enabled', () => {
    mockUseAuth.mockReturnValue(baseAuth)

    render(
      <SettingsContext.Provider value={{ applicationSettings: { ssoEnabled: true, ssoIssuerUrl: 'https://dq-made-easy.nl/iam/realms/jaccloud', allowLocalAuth: true } } as any}>
        <LoginModal isOpen onClose={vi.fn()} />
      </SettingsContext.Provider>
    )

    fireEvent.click(screen.getByRole('button', { name: 'Admin Login' }))

    expect(screen.getByText('Admin Login')).toBeTruthy()
    expect(screen.getByLabelText('Email')).toBeTruthy()
    expect(screen.getByLabelText('Password')).toBeTruthy()
  })
})