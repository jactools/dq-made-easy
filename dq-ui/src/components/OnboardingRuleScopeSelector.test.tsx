/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OnboardingRuleScopeSelector } from './OnboardingRuleScopeSelector'
import { DataProductContext } from '../contexts/DataProductContext'
import { SettingsContext } from '../contexts/SettingsContext'
import type { DataProduct, DataSet, DataObject } from '../types/dataProducts'

const mockAddNotification = vi.fn()

vi.mock('../hooks/useContexts', () => ({
  useNotifications: () => ({
    addNotification: mockAddNotification,
  }),
}))

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => ({
    user: { sub: 'user-123' },
    isAuthenticated: true,
  }),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'mock-token-123',
}))

vi.mock('../config/api', () => ({
  toApiGroupV1Base: (group: string, baseUrl: string) => `http://localhost:8000/api/${group}/v1`,
}))

vi.mock('./ModalShell', () => ({
  ModalShell: ({ children, title, footer, isOpen, onClose }: any) =>
    isOpen ? (
      <div role="dialog" aria-label={title}>
        <h2>{title}</h2>
        {children}
        {footer && <div data-testid="modal-footer">{footer}</div>}
      </div>
    ) : null,
}))

vi.mock('./app-primitives', async () => {
  const actual = await vi.importActual<typeof import('./app-primitives')>('./app-primitives')
  return {
    ...actual,
    AppSelect: ({ value, onChange, options, id, disabled }: any) => (
      <select
        data-testid={`select-${id}`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        id={id}
      >
        {options.map((opt: any) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    ),
    AppButton: ({ children, onClick, disabled, isLoading, variant }: any) => (
      <button
        onClick={onClick}
        disabled={disabled || isLoading}
        data-testid={`button-${children?.toLowerCase().replace(/\s+/g, '-')}`}
      >
        {children}
      </button>
    ),
    AppStack: ({ children }: any) => <div>{children}</div>,
    AppBanner: ({ title, description }: any) => (
      <div data-testid="banner" role="alert">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
    ),
    AppIcon: () => null,
  }
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const createMockProduct = (id: string, name: string): DataProduct => ({
  id,
  name,
  tags: [],
  description: '',
  owner: '',
  createdAt: '',
  icon: 'table',
  workspaceId: 'ws-1',
  datasets: [],
})

const createMockDataset = (id: string, name: string, productId: string): DataSet => ({
  id,
  productId,
  name,
  tags: [],
  description: '',
  owner: '',
  createdAt: '',
  workspaceId: 'ws-1',
  dataContractDownloadUrl: '',
  dataObjects: [],
})

const createMockObject = (id: string, name: string, datasetId: string): DataObject => ({
  id,
  datasetId,
  name,
  tags: [],
  description: '',
  owner: '',
  createdAt: '',
  workspaceId: 'ws-1',
  versions: [],
})

const mockContextValue = {
  state: {
    selectedProduct: null,
    selectedDataset: null,
    selectedDataObject: null,
    selectedVersion: null,
    selectedDelivery: null,
    searchQuery: '',
  },
  selectProduct: vi.fn(),
  selectDataset: vi.fn(),
  selectDataObject: vi.fn(),
  selectVersion: vi.fn(),
  selectDelivery: vi.fn(),
  setSearchQuery: vi.fn(),
  reset: vi.fn(),
  filteredProducts: [
    createMockProduct('prod-1', 'Customer Data'),
    createMockProduct('prod-2', 'Order Data'),
  ],
  allProducts: [
    createMockProduct('prod-1', 'Customer Data'),
    createMockProduct('prod-2', 'Order Data'),
  ],
  standaloneDatasets: [],
  searchResults: vi.fn(),
  loadDatasets: vi.fn(),
  loadDataObjects: vi.fn(),
  loadVersions: vi.fn(),
  loadAttributes: vi.fn(),
  isLoadingDatasets: vi.fn(() => false),
  isLoadingObjects: vi.fn(() => false),
  isLoadingVersions: vi.fn(() => false),
  isLoadingAttributes: vi.fn(() => false),
}

const mockScopeSummaryResponse = {
  scope_type: 'workspace',
  scope_id: 'ws-1',
  workspace_id: 'ws-1',
  object_count: 5,
  attribute_count: 100,
  generated_at: '2026-05-31T12:00:00Z',
}

describe('OnboardingRuleScopeSelector', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    workspaceId: 'ws-1',
    onProposalsGenerated: vi.fn(),
  }

  const renderComponent = (overrides = {}) => {
    const props = { ...defaultProps, ...overrides }
    return render(
      <DataProductContext.Provider value={mockContextValue as any}>
        <SettingsContext.Provider value={{ applicationSettings: { apiBaseUrl: 'http://localhost:8000' } } as any}>
          <OnboardingRuleScopeSelector {...props} />
        </SettingsContext.Provider>
      </DataProductContext.Provider>
    )
  }

  it('renders modal when isOpen is true', () => {
    renderComponent()
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByText('Generate Standard Rules')).toBeTruthy()
  })

  it('does not render when isOpen is false', () => {
    renderComponent({ isOpen: false })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('shows workspace scope by default', () => {
    renderComponent()
    const scopeSelect = screen.getByTestId('select-scope-type') as HTMLSelectElement
    expect(scopeSelect.value).toBe('workspace')
  })

  it('allows changing scope type', async () => {
    renderComponent()
    const scopeSelect = screen.getByTestId('select-scope-type') as HTMLSelectElement
    fireEvent.change(scopeSelect, { target: { value: 'product' } })
    await waitFor(() => {
      expect(scopeSelect.value).toBe('product')
    })
  })

  it('shows product dropdown when product scope is selected', async () => {
    renderComponent()
    const scopeSelect = screen.getByTestId('select-scope-type')
    fireEvent.change(scopeSelect, { target: { value: 'product' } })
    await waitFor(() => {
      const productSelect = screen.getByTestId('select-product-select')
      expect(productSelect).toBeTruthy()
    })
  })

  it('displays summary with object and attribute counts', () => {
    renderComponent()
    expect(screen.getByText('Objects:')).toBeTruthy()
    expect(screen.getByText('Attributes:')).toBeTruthy()
  })

  it('shows warning banner when attribute count exceeds threshold', () => {
    const contextWithManyAttributes = {
      ...mockContextValue,
      filteredProducts: [
        {
          ...createMockProduct('prod-1', 'Customer Data'),
          datasets: [
            {
              ...createMockDataset('ds-1', 'Customers', 'prod-1'),
              dataObjects: [
                {
                  ...createMockObject('obj-1', 'Customer', 'ds-1'),
                  versions: [
                    {
                      id: 'v-1',
                      version: 1,
                      attributes: Array(600)
                        .fill(null)
                        .map((_, i) => ({ id: `attr-${i}`, name: `col_${i}` })),
                    } as any,
                  ],
                },
              ],
            } as any,
          ],
        } as any,
      ],
      allProducts: [
        {
          ...createMockProduct('prod-1', 'Customer Data'),
          datasets: [
            {
              ...createMockDataset('ds-1', 'Customers', 'prod-1'),
              dataObjects: [
                {
                  ...createMockObject('obj-1', 'Customer', 'ds-1'),
                  versions: [
                    {
                      id: 'v-1',
                      version: 1,
                      attributes: Array(600)
                        .fill(null)
                        .map((_, i) => ({ id: `attr-${i}`, name: `col_${i}` })),
                    } as any,
                  ],
                },
              ],
            } as any,
          ],
        } as any,
      ],
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({}),
    } as any)

    render(
      <DataProductContext.Provider value={contextWithManyAttributes as any}>
        <SettingsContext.Provider value={{ applicationSettings: { apiBaseUrl: 'http://localhost:8000' } } as any}>
          <OnboardingRuleScopeSelector {...defaultProps} />
        </SettingsContext.Provider>
      </DataProductContext.Provider>
    )

    expect(screen.getByTestId('banner')).toBeTruthy()
    expect(screen.getByText(/Large scope detected/)).toBeTruthy()
  })

  it('disables proceed button when no valid scope selected', () => {
    renderComponent()
    const scopeSelect = screen.getByTestId('select-scope-type')
    fireEvent.change(scopeSelect, { target: { value: 'product' } })
    
    const proceedButton = screen.getByTestId('button-generate-proposals') as HTMLButtonElement
    expect(proceedButton.disabled).toBe(true)
  })

  it('enables proceed button for workspace scope', () => {
    renderComponent()
    const proceedButton = screen.getByTestId('button-generate-proposals') as HTMLButtonElement
    expect(proceedButton.disabled).toBe(false)
  })

  it('calls onProposalsGenerated when proposal generation succeeds', async () => {
    const onProposalsGenerated = vi.fn()
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockScopeSummaryResponse,
      } as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          scope_type: 'workspace',
          scope_id: 'ws-1',
          total_attributes: 100,
          total_proposals: 250,
          proposals: [],
          generated_at: '2026-05-31T12:00:00Z',
        }),
      } as any)

    renderComponent({ onProposalsGenerated })
    const proceedButton = screen.getByTestId('button-generate-proposals')
    fireEvent.click(proceedButton)

    await waitFor(() => {
      expect(onProposalsGenerated).toHaveBeenCalledWith(
        expect.objectContaining({
          scope_type: 'workspace',
          total_attributes: 100,
        })
      )
    })
  })

  it('shows error message when proposal generation fails', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockScopeSummaryResponse,
      } as any)
      .mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          detail: {
            message: 'Metadata service unavailable',
          },
        }),
      } as any)

    renderComponent()
    const proceedButton = screen.getByTestId('button-generate-proposals')
    fireEvent.click(proceedButton)

    await waitFor(() => {
      expect(mockAddNotification).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'error',
        })
      )
    })
  })

  it('closes modal after successful proposal generation', async () => {
    const onClose = vi.fn()
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockScopeSummaryResponse,
      } as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          scope_type: 'workspace',
          scope_id: 'ws-1',
          total_attributes: 100,
          total_proposals: 250,
          proposals: [],
          generated_at: '2026-05-31T12:00:00Z',
        }),
      } as any)

    renderComponent({ onClose })
    const proceedButton = screen.getByTestId('button-generate-proposals')
    fireEvent.click(proceedButton)

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled()
    })
  })

  it('sends correct scope_type in API request', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockScopeSummaryResponse,
      } as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          scope_type: 'workspace',
          scope_id: 'ws-1',
          total_attributes: 100,
          total_proposals: 250,
          proposals: [],
          generated_at: '2026-05-31T12:00:00Z',
        }),
      } as any)

    renderComponent()
    const proceedButton = screen.getByTestId('button-generate-proposals')
    fireEvent.click(proceedButton)

    await waitFor(() => {
      const call = (global.fetch as any).mock.calls[0]
      const body = JSON.parse(call[1].body)
      expect(body.scope_type).toBe('workspace')
      expect(body.workspace_id).toBe('ws-1')
    })
  })

  it('calls loadDatasets when product is selected', async () => {
    const loadDatasets = vi.fn()
    const contextWithLoadDatasets = {
      ...mockContextValue,
      loadDatasets,
    }

    render(
      <DataProductContext.Provider value={contextWithLoadDatasets as any}>
        <SettingsContext.Provider value={{ applicationSettings: { apiBaseUrl: 'http://localhost:8000' } } as any}>
          <OnboardingRuleScopeSelector {...defaultProps} />
        </SettingsContext.Provider>
      </DataProductContext.Provider>
    )

    const scopeSelect = screen.getByTestId('select-scope-type')
    fireEvent.change(scopeSelect, { target: { value: 'product' } })

    await waitFor(() => {
      const productSelect = screen.getByTestId('select-product-select')
      fireEvent.change(productSelect, { target: { value: 'prod-1' } })
    })

    await waitFor(() => {
      expect(loadDatasets).toHaveBeenCalledWith('prod-1')
    })
  })
})
