/** @vitest-environment jsdom */

import React, { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { DataBrowser } from './DataBrowser'
import { DefinitionMappingsPage } from './DefinitionMappingsPage'

const mockUseDataProduct = vi.fn()
const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()
const mockStartTestDataGeneration = vi.fn()
const mockLoadDatasets = vi.fn()
const mockLoadDataObjects = vi.fn()
const mockLoadVersions = vi.fn()
const mockSelectProduct = vi.fn()
const mockSelectDataset = vi.fn()
const mockSelectDataObject = vi.fn()
const mockSelectVersion = vi.fn()

vi.mock('../contexts/DataProductContext', () => ({
  useDataProduct: () => mockUseDataProduct(),
}))

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
  useSettingsOptional: () => mockUseSettings(),
}))

vi.mock('../hooks/useAsyncRequests', () => ({
  useAsyncRequests: () => ({
    startTestDataGeneration: mockStartTestDataGeneration,
  }),
  useTrackedAsyncRequest: () => null,
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
}))

vi.mock('./Button', () => ({
  Button: ({ children, destructive: _destructive, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { destructive?: boolean }) => (
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

vi.mock('./StatusBanner', () => ({
  StatusBanner: ({ message }: any) => <div role="status">{message}</div>,
}))


vi.mock('./AdhocRuleExecutionModal', () => ({
  AdhocRuleExecutionModal: () => null,
}))

type MockFetchResponse = {
  ok: boolean
  status?: number
  statusText?: string
  json: () => Promise<unknown>
  text: () => Promise<string>
}

const jsonResponse = (payload: unknown): MockFetchResponse => ({
  ok: true,
  status: 200,
  statusText: 'OK',
  json: async () => payload,
  text: async () => JSON.stringify(payload),
})

function DefinitionMappingsHarness() {
  const [showMappings, setShowMappings] = useState(false)

  if (showMappings) {
    return <DefinitionMappingsPage />
  }

  return (
    <DataBrowser
      viewScope="my"
      onOpenDefinitionMappings={(target) => {
        sessionStorage.setItem('dq-definition-mapping-target', JSON.stringify(target))
        setShowMappings(true)
      }}
    />
  )
}

describe('Definition Mappings navigation', () => {
  beforeEach(() => {
    const versionOne = {
      id: 'ver-1',
      dataObjectId: 'obj-1',
      version: 1,
      createdAt: '2026-04-18T00:00:00Z',
      schemaHash: 'hash-v1',
      attributes: [],
      deliveries: [],
    }

    const versionTwo = {
      id: 'ver-2',
      dataObjectId: 'obj-1',
      version: 2,
      createdAt: '2026-04-19T00:00:00Z',
      schemaHash: 'hash-v2',
      attributes: [
        {
          id: 'attr-1',
          name: 'customer_id',
          type: 'string',
          nullable: false,
          definitionId: 'def.attribute.customer_id',
          definitionMappingStatus: 'inherited',
          definitionMappingVersionId: 'ver-1',
          isCde: true,
          ruleCount: 2,
        },
      ],
      deliveries: [],
    }

    const dataObject = {
      id: 'obj-1',
      dataSetId: 'ds-1',
      name: 'Customer',
      description: 'Customer master data',
      icon: 'table',
      createdAt: '2026-04-18T00:00:00Z',
      latestVersionId: 'ver-2',
      versions: [versionOne, versionTwo],
    }

    const dataSet = {
      id: 'ds-1',
      productId: 'prod-1',
      name: 'Customer Dataset',
      description: 'Dataset',
      owner: 'data.steward@example.com',
      createdAt: '2026-04-18T00:00:00Z',
      workspaceId: 'retail-banking',
      dataObjects: [dataObject],
    }

    const product = {
      id: 'prod-1',
      name: 'Customer Product',
      description: 'Product',
      owner: 'data.steward@example.com',
      createdAt: '2026-04-18T00:00:00Z',
      icon: 'table',
      workspaceId: 'retail-banking',
      datasets: [dataSet],
    }

    mockLoadDatasets.mockResolvedValue(undefined)
    mockLoadDataObjects.mockResolvedValue(undefined)
    mockLoadVersions.mockResolvedValue([versionOne, versionTwo])

    mockUseDataProduct.mockReturnValue({
      state: {
        selectedProduct: product,
        selectedDataset: dataSet,
        selectedDataObject: dataObject,
        selectedVersion: versionTwo,
        selectedDelivery: null,
        searchQuery: '',
      },
      selectProduct: mockSelectProduct,
      selectDataset: mockSelectDataset,
      selectDataObject: mockSelectDataObject,
      selectVersion: mockSelectVersion,
      selectDelivery: vi.fn(),
      setSearchQuery: vi.fn(),
      reset: vi.fn(),
      filteredProducts: [product],
      standaloneDatasets: [],
      searchResults: vi.fn(),
      loadDatasets: mockLoadDatasets,
      loadDataObjects: mockLoadDataObjects,
      loadVersions: mockLoadVersions,
      loadAttributes: vi.fn().mockResolvedValue(versionTwo.attributes),
      isLoadingDatasets: vi.fn().mockReturnValue(false),
      isLoadingObjects: vi.fn().mockReturnValue(false),
      isLoadingVersions: vi.fn().mockReturnValue(false),
      isLoadingAttributes: vi.fn().mockReturnValue(false),
    })

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      user: {
        id: 'user-1',
        email: 'data.steward@example.com',
        name: 'Data Steward',
        workspaceRoles: [{ workspaceId: 'retail-banking', role: 'data-steward' }],
      },
      hasAnyScope: () => true,
      hasScope: () => true,
      canManageUsers: () => true,
      canReadAcrossWorkspaces: () => true,
      getCurrentUserRole: () => 'data-steward',
    })

    mockUseSettings.mockReturnValue({
      applicationSettings: { apiBaseUrl: 'http://localhost:4010' },
      displaySettings: { theme: 'auto' },
    })

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/attributes-catalog?versionId=ver-2')) {
        return jsonResponse({
          data: [
            {
              id: 'attr-1',
              name: 'customer_id',
              type: 'string',
              nullable: false,
              definition_id: 'def.attribute.customer_id',
              definition_mapping_status: 'inherited',
              definition_mapping_version_id: 'ver-1',
            },
          ],
        })
      }

      if (url.includes('/registry/definitions/def.attribute.customer_id')) {
        return jsonResponse({
          definition_id: 'def.attribute.customer_id',
          definition_name: 'Customer Identifier',
          business_definition: 'Stable customer identifier used across deliveries.',
          glossary_id: 'glossary.retail',
          glossary_name: 'Retail Banking Glossary',
          owner: 'Data Steward',
          synonyms: ['Customer Key', 'Party Identifier'],
          parent_definition_id: 'def.attribute.customer',
          parent_definition_name: 'Customer',
          child_definition_ids: ['def.attribute.customer_number'],
          child_definition_names: ['Customer Number'],
          child_definition_count: 1,
          applies_to: ['data_object:customer'],
        })
      }

      if (url.includes('/registry/definitions?')) {
        return jsonResponse([
          {
            definition_id: 'def.attribute.customer_id',
            definition_name: 'Customer Identifier',
            business_definition: 'Stable customer identifier used across deliveries.',
            glossary_id: 'glossary.retail',
            glossary_name: 'Retail Banking Glossary',
            owner: 'Data Steward',
            synonyms: ['Customer Key', 'Party Identifier'],
            parent_definition_id: 'def.attribute.customer',
            parent_definition_name: 'Customer',
            child_definition_ids: ['def.attribute.customer_number'],
            child_definition_names: ['Customer Number'],
            child_definition_count: 1,
            applies_to: ['data_object:customer'],
          },
        ])
      }

      if (url.includes('/registry/reference-domains?')) {
        return jsonResponse([
          {
            definition_id: 'def.attribute.customer_status',
            definition_name: 'Customer Status',
            business_definition: 'Lifecycle state describing whether a retail banking customer is prospect, active, dormant, or closed.',
            owner: 'Customer Steward',
            value_domain: {
              type: 'string',
              allowed_values: ['prospect', 'active', 'dormant', 'closed'],
              constraints: { nullable: false },
            },
            applies_to: ['data_object:customer'],
          },
          {
            definition_id: 'def.attribute.country_code',
            definition_name: 'Country Code',
            business_definition: 'ISO 3166 alpha-2 country code used for customer residence and servicing rules.',
            owner: 'Customer Steward',
            value_domain: {
              type: 'string',
              allowed_values: ['US', 'GB', 'NL', 'DE'],
              constraints: { nullable: false },
            },
            applies_to: ['data_object:customer'],
          },
        ])
      }

      throw new Error(`Unexpected fetch call: ${url}`)
    }))
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    sessionStorage.clear()
  })

  it('opens Definition Mappings with the current version and attribute preselected from the Data Browser', async () => {
    render(<DefinitionMappingsHarness />)

    const definitionCellButton = screen.getByText('def.attribute.customer_id').closest('button')
    expect(definitionCellButton).not.toBeNull()

    fireEvent.click(definitionCellButton as HTMLButtonElement)

    await screen.findByRole('heading', { name: 'Definition Mappings' })

    await waitFor(() => {
      expect(screen.getByText('Customer v2')).toBeTruthy()
    })

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 3, name: 'customer_id' })).toBeTruthy()
    })

    await waitFor(() => {
      expect((screen.getByLabelText('Version') as HTMLSelectElement).value).toBe('ver-2')
    })

    await screen.findByText('Retail Banking Glossary')
    expect(screen.getByText('Customer Key, Party Identifier')).toBeTruthy()
    expect(screen.getByText('Customer • Customer Number')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Reference Data' }))

    await screen.findByText('Customer Status')
    expect(screen.getByText('prospect')).toBeTruthy()
    expect(screen.getByText('US')).toBeTruthy()

    expect(mockLoadDatasets).toHaveBeenCalledWith('prod-1')
    expect(mockLoadDataObjects).toHaveBeenCalledWith('ds-1')
    expect(mockLoadVersions).toHaveBeenCalledWith('obj-1')
  })
})