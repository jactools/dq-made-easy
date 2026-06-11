/** @vitest-environment jsdom */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

import { DataAssetsBuilder, buildProtectionReviewRows, summarizeProtectionReview, toAssetFormState, toAssetPayload } from './DataAssetsBuilder'
import type { DataAttribute, DataObjectVersion, DataProduct } from '../types/dataProducts'

const makeAttribute = (overrides: Partial<DataAttribute> & Pick<DataAttribute, 'id' | 'name' | 'type' | 'nullable'>): DataAttribute => ({
  ...overrides,
  id: overrides.id,
  name: overrides.name,
  type: overrides.type,
  nullable: overrides.nullable,
})

const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()
const mockUseDataProduct = vi.fn()

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
}))

vi.mock('../contexts/DataProductContext', () => ({
  useDataProduct: () => mockUseDataProduct(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
}))

vi.mock('../hooks/useAgentHarness', () => ({
  useAgentHarness: () => ({
    agents: [],
    loadingAgents: false,
    error: null,
    runAgent: vi.fn(),
  }),
}))

const makeProduct = (): DataProduct => ({
  id: 'prod-1',
  name: 'Customer Product',
  description: 'Customer data product',
  owner: 'data.steward@example.com',
  createdAt: '2026-04-18T00:00:00Z',
  icon: 'database',
  workspaceId: 'retail-banking',
  datasets: [
    {
      id: 'ds-1',
      productId: 'prod-1',
      name: 'Customer Dataset',
      description: 'Customer dataset',
      owner: 'data.steward@example.com',
      createdAt: '2026-04-18T00:00:00Z',
      workspaceId: 'retail-banking',
      dataObjects: [
        {
          id: 'obj-1',
          dataSetId: 'ds-1',
          name: 'Customer Object',
          description: 'Customer object',
          icon: 'table',
          createdAt: '2026-04-18T00:00:00Z',
          latestVersionId: 'ver-1',
          versions: [
            {
              id: 'ver-1',
              dataObjectId: 'obj-1',
              version: 1,
              createdAt: '2026-04-18T00:00:00Z',
              attributes: [],
              schemaHash: 'schema-hash',
            } as DataObjectVersion,
          ],
        },
      ],
    },
  ],
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('DataAssetsBuilder', () => {
  it('renders a metadata browser AI assistant entry point in the studio', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'workspace-1',
      user: { workspaceRoles: [{ workspaceId: 'workspace-1' }] },
    })
    mockUseSettings.mockReturnValue({
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1' },
    })
    mockUseDataProduct.mockReturnValue({
      filteredProducts: [],
      standaloneDatasets: [],
      loadDatasets: vi.fn(),
      loadDataObjects: vi.fn(),
      loadVersions: vi.fn(),
      loadAttributes: vi.fn(),
      isLoadingDatasets: () => false,
      isLoadingObjects: () => false,
      isLoadingVersions: () => false,
      isLoadingAttributes: () => false,
    })

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    }))

    render(<DataAssetsBuilder />)

    expect(await screen.findByRole('heading', { name: /metadata browser assistant/i })).toBeTruthy()
    expect(screen.getByDisplayValue(/help me inspect metadata/i)).toBeTruthy()
  })
})

describe('DataAssetsBuilder protection review helpers', () => {
  it('flags unprotected sensitive attributes and resolves the mapping target', () => {
    const selectedVersion = {
      id: 'asset-version-1',
      dataAssetId: 'asset-1',
      version: 3,
      createdAt: '2026-04-20T00:00:00Z',
      sourceBindings: [
        {
          sourceDataObjectVersionId: 'ver-1',
          sourceFieldId: 'attr-1',
          sourceFieldName: 'customer_email',
          sourceFieldType: 'string',
          nullable: false,
        },
      ],
      filters: [],
      derivedFields: [],
      uploadPreview: null,
      dataContractDownloadUrl: '/download',
    }

    const rows = buildProtectionReviewRows(
      selectedVersion as never,
      {
        'ver-1': [
          makeAttribute({
            id: 'attr-1',
            name: 'customer_email',
            type: 'string',
            nullable: false,
            isCde: true,
            ruleCount: 2,
          }),
        ],
      },
      'restricted',
      'high',
      [makeProduct()],
      [],
    )

    expect(rows).toHaveLength(1)
    expect(rows[0].status).toBe('unprotected')
    expect(rows[0].recommendation).toContain('Protect through masking or encryption')
    expect(rows[0].target).toEqual({
      productId: 'prod-1',
      datasetId: 'ds-1',
      objectId: 'obj-1',
      versionId: 'ver-1',
      attributeId: 'attr-1',
    })

    const summary = summarizeProtectionReview(rows)
    expect(summary.sensitiveCount).toBe(1)
    expect(summary.protectedCount).toBe(0)
    expect(summary.unprotectedCount).toBe(1)
    expect(summary.advice).toContain('should be protected')
  })

  it('recognizes masking and encryption as protected states', () => {
    const selectedVersion = {
      id: 'asset-version-2',
      dataAssetId: 'asset-2',
      version: 1,
      createdAt: '2026-04-20T00:00:00Z',
      sourceBindings: [
        {
          sourceDataObjectVersionId: 'ver-1',
          sourceFieldId: 'attr-2',
          sourceFieldName: 'customer_phone',
          sourceFieldType: 'string',
          nullable: false,
        },
        {
          sourceDataObjectVersionId: 'ver-1',
          sourceFieldId: 'attr-3',
          sourceFieldName: 'customer_id',
          sourceFieldType: 'string',
          nullable: false,
        },
      ],
      filters: [],
      derivedFields: [],
      uploadPreview: null,
      dataContractDownloadUrl: '/download',
    }

    const rows = buildProtectionReviewRows(
      selectedVersion as never,
      {
        'ver-1': [
          makeAttribute({
            id: 'attr-2',
            name: 'customer_phone',
            type: 'string',
            nullable: false,
            maskingMethod: 'redact',
          }),
          makeAttribute({
            id: 'attr-3',
            name: 'customer_id',
            type: 'string',
            nullable: false,
            encryptionRequired: true,
            encryptionKeyId: 'key-123',
          }),
        ],
      },
      'restricted',
      'high',
      [makeProduct()],
      [],
    )

    expect(rows.map((row) => row.status)).toEqual(['masked', 'encrypted'])
    expect(summarizeProtectionReview(rows).advice).toContain('already protected')
  })
})

describe('DataAssetsBuilder asset metadata helpers', () => {
  it('maps the extended business context into the API payload', () => {
    const payload = toAssetPayload({
      id: 'asset-1',
      name: 'Customer health',
      description: 'Customer health asset',
      workspaceId: 'ws-1',
      status: 'draft',
      currentVersionId: 'asset-1-v1',
      sourceObjectVersionIdsText: 'dov-1, dov-2',
      businessContextDatasetId: 'dataset-1',
      businessContextDataProductId: 'product-1',
      businessContextDomain: 'Customer',
      businessContextOwner: 'data-owner@example.com',
      businessContextPurpose: 'Track customer health for reporting',
      businessContextSteward: 'data-steward@example.com',
      businessContextCriticality: 'high',
      businessContextTagsText: 'customer, regulated',
      businessContextBusinessDefinitionsText: 'Customer health metric, Support priority metric',
      businessContextLineageReferencesText: 'dov-1, upstream-job-7',
      businessContextConsumersText: 'Support, Analytics',
    })

    expect(payload.business_context).toEqual({
      dataset_id: 'dataset-1',
      data_product_id: 'product-1',
      domain: 'Customer',
      owner: 'data-owner@example.com',
      purpose: 'Track customer health for reporting',
      steward: 'data-steward@example.com',
      criticality: 'high',
      tags: ['customer', 'regulated'],
      business_definitions: ['Customer health metric', 'Support priority metric'],
      lineage_references: ['dov-1', 'upstream-job-7'],
      consumers: ['Support', 'Analytics'],
    })
  })

  it('restores the extended business context into the form state', () => {
    const formState = toAssetFormState({
      id: 'asset-1',
      name: 'Customer health',
      description: 'Customer health asset',
      workspaceId: 'ws-1',
      status: 'draft',
      createdAt: '2026-05-31T00:00:00Z',
      currentVersionId: 'asset-1-v1',
      sourceObjectVersionIds: ['dov-1'],
      businessContext: {
        datasetId: 'dataset-1',
        dataProductId: 'product-1',
        domain: 'Customer',
        owner: 'data-owner@example.com',
        purpose: 'Track customer health for reporting',
        steward: 'data-steward@example.com',
        criticality: 'high',
        tags: ['customer', 'regulated'],
        businessDefinitions: ['Customer health metric', 'Support priority metric'],
        lineageReferences: ['dov-1', 'upstream-job-7'],
        consumers: ['Support', 'Analytics'],
      },
      dataContractDownloadUrl: '/data-assets/asset-1/contract',
    })

    expect(formState.businessContextDatasetId).toBe('dataset-1')
    expect(formState.businessContextDataProductId).toBe('product-1')
    expect(formState.businessContextOwner).toBe('data-owner@example.com')
    expect(formState.businessContextTagsText).toBe('customer, regulated')
    expect(formState.businessContextBusinessDefinitionsText).toBe('Customer health metric, Support priority metric')
    expect(formState.businessContextLineageReferencesText).toBe('dov-1, upstream-job-7')
  })
})