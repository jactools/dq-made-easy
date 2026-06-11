/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

import { DataBrowser } from './DataBrowser'

const mockUseDataProduct = vi.fn()
const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()
const mockGetAuthToken = vi.fn()
const mockStartTestDataGeneration = vi.fn()

vi.mock('./app-primitives', async () => {
  const actual = await vi.importActual<typeof import('./app-primitives')>('./app-primitives')
  return {
    ...actual,
    AppIcon: ({ name }: { name: string }) => <span data-testid={`icon-${name}`} />,
  }
})

vi.mock('./Button', async () => {
  const React = await import('react')
  const Button = ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  )
  return { Button, PrimaryButton: Button, SecondaryButton: Button, TertiaryButton: Button }
})

vi.mock('./HierarchyTree', () => ({
  HierarchyTreePanel: ({ title, countLabel, headerBadge, children }: any) => (
    <section aria-label={String(title)}>
      <h2>{title}</h2>
      <div>{countLabel}</div>
      <div>{headerBadge}</div>
      <div>{children}</div>
    </section>
  ),
  HierarchyTreeRow: ({ label, badge }: any) => (
    <div>
      <span>{label}</span>
      {badge}
    </div>
  ),
  HierarchyTreeStatus: ({ children }: any) => <span>{children}</span>,
}))

vi.mock('./AdhocRuleExecutionModal', () => ({
  AdhocRuleExecutionModal: () => null,
}))

vi.mock('../contexts/DataProductContext', () => ({
  useDataProduct: () => mockUseDataProduct(),
}))

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => mockGetAuthToken(),
}))

vi.mock('../hooks/useAsyncRequests', () => ({
  useAsyncRequests: () => ({
    startTestDataGeneration: mockStartTestDataGeneration,
  }),
  useTrackedAsyncRequest: () => null,
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  mockUseSettings.mockReturnValue({
    applicationSettings: {
      apiBaseUrl: 'http://localhost:8080',
    },
  })
  mockGetAuthToken.mockReturnValue('test-token')
  mockUseAuth.mockReturnValue({
    currentWorkspaceId: 'retail-banking',
    user: {
      workspaceRoles: [
        {
          workspaceId: 'retail-banking',
        },
      ],
    },
  })

  mockUseDataProduct.mockReturnValue({
    state: {
      selectedProduct: null,
      selectedDataset: null,
      selectedDataObject: null,
      selectedVersion: null,
      selectedDelivery: null,
    },
    selectProduct: vi.fn(),
    selectDataset: vi.fn(),
    selectDataObject: vi.fn(),
    selectVersion: vi.fn(),
    selectDelivery: vi.fn(),
    setSearchQuery: vi.fn(),
    filteredProducts: [
      {
        id: 'prod-1',
        name: 'Customer & Order Management',
        description: 'Complete customer lifecycle and order processing data',
        owner: 'alice@example.com',
        createdAt: '2025-01-15T10:00:00Z',
        icon: 'app-icon-users',
        workspaceId: 'retail-banking',
        datasets: [],
      },
    ],
    standaloneDatasets: [],
    loadDatasets: vi.fn(),
    loadDataObjects: vi.fn(),
    loadVersions: vi.fn(),
    loadAttributes: vi.fn(),
    isLoadingDatasets: false,
    isLoadingObjects: false,
    isLoadingVersions: false,
    isLoadingAttributes: false,
  })
})

describe('DataBrowser', () => {
  it('renders the shared page shell and catalog header', () => {
    render(<DataBrowser />)

    expect(screen.getByRole('heading', { name: 'Browse Datasets & Schemas' })).toBeTruthy()
    expect(screen.getByText('Explore data products, datasets, versions, and attributes')).toBeTruthy()
    expect(screen.getByPlaceholderText('Search datasets, objects, attributes...')).toBeTruthy()
    expect(screen.getByText(/Retail Banking/)).toBeTruthy()
  })
})
