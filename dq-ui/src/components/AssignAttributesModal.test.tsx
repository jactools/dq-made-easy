/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { AssignAttributesModal } from './AssignAttributesModal'

const mockUseSettings = vi.fn()
const mockUseAuth = vi.fn()
const mockUseUnsavedChangesConfirmation = vi.fn()
const mockEnrichValidation = vi.fn()

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
  useSettingsOptional: () => mockUseSettings(),
  useAuth: () => mockUseAuth(),
}))

vi.mock('../hooks/useUnsavedChangesConfirmation', () => ({
  useUnsavedChangesConfirmation: () => mockUseUnsavedChangesConfirmation(),
}))

vi.mock('../hooks/useEnrichedValidation', () => ({
  useEnrichedValidation: () => ({
    enrichValidation: (...args: any[]) => mockEnrichValidation(...args),
  }),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))

vi.mock('./UnsavedChangesDialog', () => ({
  UnsavedChangesDialog: () => null,
}))

vi.mock('./AliasDiagnosticsDisplay', () => ({
  AliasDiagnosticsDisplay: () => null,
}))

vi.mock('./Button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  PrimaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  SecondaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  TertiaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
}))

vi.mock('./rules/AttributeCard', () => ({
  AttributeCard: ({ attribute }: any) => <span>{attribute.name} {attribute.workspaceId || ''}</span>,
}))


const buildResponse = (body: any, ok = true, status = ok ? 200 : 500) => ({
  ok,
  status,
  json: async () => body,
  text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
})

const setupCommonMocks = () => {
  mockUseSettings.mockReturnValue({
    applicationSettings: {
      apiBaseUrl: 'http://api.local/v1',
    },
  })

  mockUseAuth.mockReturnValue({
    currentWorkspaceId: 'ws-a',
    user: {
      id: 'alice-id',
      email: 'alice@example.com',
      name: 'Alice',
      workspaceRoles: [
        { workspaceId: 'ws-a', role: 'editor', joinedAt: new Date('2026-01-01T00:00:00Z') },
      ],
    },
  })

  mockUseUnsavedChangesConfirmation.mockReturnValue({
    showConfirmation: false,
    handleCloseWithConfirmation: vi.fn(),
    handleConfirmClose: vi.fn(),
    handleCancelConfirmation: vi.fn(),
  })

  mockEnrichValidation.mockResolvedValue({ diagnostics: {} })
}

describe('AssignAttributesModal scope browsing', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('filters catalog attributes by my, team, all, and all across scopes', async () => {
    setupCommonMocks()

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/data-catalog/v1/attributes-catalog')) {
        return buildResponse({
          data: [
            { id: 'attr-my', name: 'my_attr', type: 'string', data_object_id: 'obj-my', version_id: 'ver-my' },
            { id: 'attr-team', name: 'team_attr', type: 'string', data_object_id: 'obj-team', version_id: 'ver-team' },
            { id: 'attr-global', name: 'global_attr', type: 'string', data_object_id: 'obj-global', version_id: 'ver-global' },
          ],
          total: 3,
        })
      }

      if (url.includes('/data-catalog/v1/data-objects-catalog')) {
        return buildResponse({
          data: [
            { id: 'obj-my', dataset_id: 'ds-my', name: 'orders', latest_version_id: 'ver-my' },
            { id: 'obj-team', dataset_id: 'ds-team', name: 'customers', latest_version_id: 'ver-team' },
            { id: 'obj-global', dataset_id: 'ds-global', name: 'events', latest_version_id: 'ver-global' },
          ],
          total: 3,
        })
      }

      if (url.includes('/data-catalog/v1/data-sets')) {
        return buildResponse({
          data: [
            { id: 'ds-my', product_id: 'prod-my', name: 'My Dataset', owner: 'alice@example.com', workspace_id: 'ws-a' },
            { id: 'ds-team', product_id: 'prod-team', name: 'Team Dataset', owner: 'bob@example.com', workspace_id: 'ws-a' },
            { id: 'ds-global', product_id: 'prod-global', name: 'Global Dataset', owner: 'charlie@example.com', workspace_id: 'ws-b' },
          ],
          total: 3,
        })
      }

      if (url.includes('/data-catalog/v1/data-products')) {
        return buildResponse({
          data: [
            { id: 'prod-my', name: 'My Product', owner: 'alice@example.com', workspace_id: 'ws-a' },
            { id: 'prod-team', name: 'Team Product', owner: 'bob@example.com', workspace_id: 'ws-a' },
            { id: 'prod-global', name: 'Global Product', owner: 'charlie@example.com', workspace_id: 'ws-b' },
          ],
          total: 3,
        })
      }

      return buildResponse({ detail: 'Unexpected request' }, false, 404)
    }) as any)

    const user = userEvent.setup()

    render(
      <AssignAttributesModal
        isOpen={true}
        onClose={vi.fn()}
        ruleName="Scope browsing test"
        currentAttributeIds={[]}
        onSave={vi.fn(async () => undefined)}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText(/Showing 1 of 1 technical attributes/)).toBeTruthy()
      expect(screen.getByText(/my_attr/)).toBeTruthy()
    })

    await user.click(screen.getByRole('tab', { name: /my team's/i }))

    await waitFor(() => {
      expect(screen.getByText(/Showing 1 of 1 technical attributes/)).toBeTruthy()
      expect(screen.getByText(/team_attr/)).toBeTruthy()
      expect(screen.queryByText(/my_attr/)).toBeNull()
      expect(screen.queryByText(/global_attr/)).toBeNull()
    })

    await user.click(screen.getByRole('tab', { name: /^all$/i }))

    await waitFor(() => {
      expect(screen.getByText(/Showing 2 of 2 technical attributes/)).toBeTruthy()
      expect(screen.getByText(/my_attr/)).toBeTruthy()
      expect(screen.getByText(/team_attr/)).toBeTruthy()
      expect(screen.queryByText(/global_attr/)).toBeNull()
    })

    await user.click(screen.getByRole('tab', { name: /all across/i }))

    await waitFor(() => {
      expect(screen.getByText(/Showing 3 of 3 technical attributes/)).toBeTruthy()
      expect(screen.getByText(/global_attr/)).toBeTruthy()
    })

    const searchInput = screen.getByPlaceholderText('Search technical attributes...')
    await user.type(searchInput, 'te')

    await waitFor(() => {
      expect(screen.getByText(/Showing 3 of 3 technical attributes/)).toBeTruthy()
    })

    await user.clear(searchInput)
    await user.type(searchInput, 'team dataset')

    await waitFor(() => {
      expect(screen.getByText(/Showing 1 of 3 technical attributes/)).toBeTruthy()
      expect(screen.getByText(/team_attr/)).toBeTruthy()
      expect(screen.queryByText(/my_attr/)).toBeNull()
    })
  })
})